"""
Validates and ingests an edited copy of political_events.csv (e.g. returned by
a collaborator who reviewed/corrected event details or added new events) back
into data/processed/political_events.csv.

Usage:
    python src/ingest_events.py path/to/returned_political_events.csv
    python src/ingest_events.py path/to/returned_political_events.csv --force

Unlike songs.csv, adding brand-new events is expected collaborator behavior
(not treated as suspicious) — next_event_id() suggests the next free ID for
them. Refuses to overwrite data/processed/political_events.csv if it finds
signs of corruption or unexpected deletions (see SETUP.md), unless --force is
passed. Always backs up the current file before overwriting. Non-UTF-8
encoding and column-set mismatches are hard stops that --force cannot bypass.
"""

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent.parent
CURRENT_EVENTS_CSV = BASE_DIR / "data" / "processed" / "political_events.csv"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALID_AXES = {"drug_war_mx", "immigration_usmx", "elections_mx", "us_presidency"}
REQUIRED_FIELDS = ["event_id", "date", "axis", "title", "source_url"]


def load_csv_strict_utf8(path: Path) -> pd.DataFrame:
    raw = path.read_bytes()
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"{path} is not valid UTF-8: {e}") from e
    return pd.read_csv(path, dtype=str, encoding="utf-8").fillna("")


def diff_events(current: pd.DataFrame, incoming: pd.DataFrame) -> dict:
    flags = []
    info = []

    current_ids = set(current["event_id"])
    incoming_ids = set(incoming["event_id"])
    missing_ids = current_ids - incoming_ids
    added_ids = incoming_ids - current_ids

    if missing_ids:
        flags.append(
            f"{len(missing_ids)} event_id(s) present in current data are missing "
            f"from the incoming file (looks like a deletion): {sorted(missing_ids)[:10]}"
        )
    if added_ids:
        info.append(f"{len(added_ids)} new event(s) added: {sorted(added_ids)[:10]}")

    current_id_counts = current["event_id"].value_counts()
    incoming_id_counts = incoming["event_id"].value_counts()
    current_dupes = set(current_id_counts[current_id_counts > 1].index)
    incoming_dupes = set(incoming_id_counts[incoming_id_counts > 1].index)
    if current_dupes:
        flags.append(f"{len(current_dupes)} event_id(s) duplicated in the current file: {sorted(current_dupes)[:10]}")
    if incoming_dupes:
        flags.append(f"{len(incoming_dupes)} event_id(s) duplicated in the incoming file: {sorted(incoming_dupes)[:10]}")

    # Field validation applies to every row in the incoming file (shared + new).
    for _, row in incoming.iterrows():
        eid = row.get("event_id", "<blank>")
        for field in REQUIRED_FIELDS:
            if not row.get(field, "").strip():
                flags.append(f"event_id {eid}: required field '{field}' is blank")
        axis = row.get("axis", "")
        if axis and axis not in VALID_AXES:
            flags.append(f"event_id {eid}: axis '{axis}' is not one of {sorted(VALID_AXES)}")
        date = row.get("date", "")
        if date and not DATE_RE.match(date):
            flags.append(f"event_id {eid}: date '{date}' is not YYYY-MM-DD")

    changed_rows = 0
    dupe_ids = current_dupes | incoming_dupes
    shared_ids = (current_ids & incoming_ids) - dupe_ids
    current_by_id = current.set_index("event_id")
    incoming_by_id = incoming.set_index("event_id")
    changed_cols = {c: 0 for c in current.columns if c != "event_id"}
    for eid in shared_ids:
        cur_row, inc_row = current_by_id.loc[eid], incoming_by_id.loc[eid]
        row_changed = False
        for col in changed_cols:
            if cur_row.get(col, "") != inc_row.get(col, ""):
                changed_cols[col] += 1
                row_changed = True
        if row_changed:
            changed_rows += 1

    return {
        "flags": flags,
        "info": info,
        "missing_ids": missing_ids,
        "added_ids": added_ids,
        "changed_rows": changed_rows,
        "changed_cols": changed_cols,
    }


def next_event_id(current: pd.DataFrame) -> str:
    nums = [int(m.group(1)) for eid in current["event_id"] if (m := re.match(r"^E(\d+)$", eid))]
    return f"E{max(nums) + 1:03d}" if nums else "E001"


def run(incoming_path: Path, current_path: Path, force: bool) -> int:
    if not current_path.exists():
        print(f"Current events file not found: {current_path}")
        return 1
    if not incoming_path.exists():
        print(f"Incoming file not found: {incoming_path}")
        return 1

    try:
        incoming = load_csv_strict_utf8(incoming_path)
    except ValueError as e:
        print(f"REFUSING to ingest: {e}")
        return 1

    current = load_csv_strict_utf8(current_path)

    if set(incoming.columns) != set(current.columns):
        missing_cols = set(current.columns) - set(incoming.columns)
        extra_cols = set(incoming.columns) - set(current.columns)
        print("REFUSING to ingest: column mismatch between current and incoming file")
        if missing_cols:
            print(f"  Missing columns: {sorted(missing_cols)}")
        if extra_cols:
            print(f"  Unexpected columns: {sorted(extra_cols)}")
        return 1

    result = diff_events(current, incoming)

    print(f"Current events: {len(current)}, incoming events: {len(incoming)}")
    print(f"Rows with at least one changed field: {result['changed_rows']}")
    for col, n in result["changed_cols"].items():
        if n:
            print(f"  {col} changed: {n}")

    if result["info"]:
        print()
        for line in result["info"]:
            print(f"  + {line}")

    if result["flags"]:
        print(f"\n{len(result['flags'])} issue(s) found:")
        for flag in result["flags"]:
            print(f"  - {flag}")

        if not force:
            print("\nRefusing to overwrite data/processed/political_events.csv. Review the issues above.")
            print("If they're expected, re-run with --force.")
            return 1
        print("\n--force passed: proceeding despite the issues above.")

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_path = current_path.parent / f"political_events.backup-{timestamp}.csv"
    shutil.copy2(current_path, backup_path)
    print(f"\nBacked up current file to {backup_path}")

    incoming.to_csv(current_path, index=False)
    print(f"Wrote {len(incoming)} events to {current_path}")
    print(f"\nNext free event_id if adding more by hand: {next_event_id(incoming)}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("incoming", type=Path, help="Path to the returned/edited political_events.csv")
    parser.add_argument(
        "--current", type=Path, default=CURRENT_EVENTS_CSV,
        help="Path to the current canonical political_events.csv (default: data/processed/political_events.csv)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite even if issues are found")
    args = parser.parse_args()
    sys.exit(run(args.incoming, args.current, args.force))


if __name__ == "__main__":
    main()
