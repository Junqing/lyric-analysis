"""
Validates and ingests a collaborator's edited copies of lexicons/*.txt back
into the project's lexicons/ directory.

Collaborators may add or remove terms within existing sections. Section
headers/comments and the set of lexicon file names must stay unchanged —
renaming a file or a section (or adding/removing one) breaks
analyze_keywords.py's expectations and is refused unless --force.

Usage:
    python src/ingest_lexicons.py path/to/returned/lexicons/
    python src/ingest_lexicons.py path/to/returned/lexicons/ --force
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CURRENT_LEXICONS_DIR = BASE_DIR / "lexicons"


def parse_lexicon_file(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").split("\n")
    header_lines = []
    i = 0
    while i < len(lines) and lines[i].strip().startswith("#"):
        header_lines.append(lines[i].strip())
        i += 1

    sections = []
    current = None
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == "":
            i += 1
            continue
        if stripped.startswith("#"):
            current = {"header": stripped, "terms": []}
            sections.append(current)
        elif current is not None:
            current["terms"].append(stripped)
        i += 1

    return {"header_lines": header_lines, "sections": sections}


def load_utf8_text(path: Path) -> None:
    """Raises ValueError if path is not valid UTF-8."""
    raw = path.read_bytes()
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"{path} is not valid UTF-8: {e}") from e


def diff_lexicon(name: str, current: dict, incoming: dict) -> dict:
    flags = []
    info = []

    if current["header_lines"] != incoming["header_lines"]:
        flags.append(f"{name}: file header/citation comments changed (should stay fixed)")

    cur_headers = [s["header"] for s in current["sections"]]
    inc_headers = [s["header"] for s in incoming["sections"]]
    if cur_headers != inc_headers:
        flags.append(
            f"{name}: section headers changed — expected {cur_headers}, got {inc_headers}"
        )
        return {"flags": flags, "info": info, "added": 0, "removed": 0}

    added = removed = 0
    for cur_sec, inc_sec in zip(current["sections"], incoming["sections"]):
        cur_terms, inc_terms = set(cur_sec["terms"]), set(inc_sec["terms"])
        sec_added = inc_terms - cur_terms
        sec_removed = cur_terms - inc_terms
        added += len(sec_added)
        removed += len(sec_removed)
        if sec_added or sec_removed:
            info.append(
                f"{name} / {cur_sec['header'].lstrip('#').strip()}: "
                f"+{len(sec_added)} -{len(sec_removed)} terms"
            )
        dupes = [t for t in inc_sec["terms"] if inc_sec["terms"].count(t) > 1]
        if dupes:
            info.append(f"{name} / {cur_sec['header'].lstrip('#').strip()}: duplicate term(s) {sorted(set(dupes))}")

    return {"flags": flags, "info": info, "added": added, "removed": removed}


def run(incoming_dir: Path, current_dir: Path, force: bool) -> int:
    if not current_dir.exists():
        print(f"Current lexicons directory not found: {current_dir}")
        return 1
    if not incoming_dir.exists() or not incoming_dir.is_dir():
        print(f"Incoming directory not found: {incoming_dir}")
        return 1

    current_files = {p.name for p in current_dir.glob("*.txt")}
    incoming_files = {p.name for p in incoming_dir.glob("*.txt")}

    if current_files != incoming_files:
        missing = current_files - incoming_files
        extra = incoming_files - current_files
        print("REFUSING to ingest: lexicon file set mismatch")
        if missing:
            print(f"  Missing files: {sorted(missing)}")
        if extra:
            print(f"  Unexpected files: {sorted(extra)}")
        return 1

    all_flags, all_info = [], []
    parsed_incoming = {}
    for name in sorted(current_files):
        try:
            load_utf8_text(incoming_dir / name)
        except ValueError as e:
            print(f"REFUSING to ingest: {e}")
            return 1

        current_parsed = parse_lexicon_file(current_dir / name)
        incoming_parsed = parse_lexicon_file(incoming_dir / name)
        parsed_incoming[name] = incoming_parsed

        result = diff_lexicon(name, current_parsed, incoming_parsed)
        all_flags.extend(result["flags"])
        all_info.extend(result["info"])
        print(f"{name}: +{result['added']} -{result['removed']} terms")

    if all_info:
        print()
        for line in all_info:
            print(f"  {line}")

    if all_flags:
        print(f"\n{len(all_flags)} issue(s) found:")
        for flag in all_flags:
            print(f"  - {flag}")

        if not force:
            print("\nRefusing to overwrite lexicons/. Review the issues above.")
            print("If they're expected, re-run with --force.")
            return 1
        print("\n--force passed: proceeding despite the issues above.")

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_dir = current_dir.parent / f"lexicons.backup-{timestamp}"
    shutil.copytree(current_dir, backup_dir)
    print(f"\nBacked up current lexicons/ to {backup_dir}")

    for name in sorted(current_files):
        shutil.copy2(incoming_dir / name, current_dir / name)
    print(f"Wrote {len(current_files)} lexicon file(s) to {current_dir}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("incoming", type=Path, help="Directory containing the returned/edited lexicon .txt files")
    parser.add_argument(
        "--current", type=Path, default=CURRENT_LEXICONS_DIR,
        help="Path to the current canonical lexicons/ directory (default: lexicons/)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite even if issues are found")
    args = parser.parse_args()
    sys.exit(run(args.incoming, args.current, args.force))


if __name__ == "__main__":
    main()
