"""
Validates and ingests an edited copy of songs.csv (e.g. returned by a
collaborator who filled in missing release_year/release_date values) back
into data/processed/songs.csv.

Usage:
    python src/ingest_songs.py path/to/returned_songs.csv
    python src/ingest_songs.py path/to/returned_songs.csv --force

Refuses to overwrite data/processed/songs.csv if it finds signs of
corruption or unexpected changes (see SETUP.md, "Sending Data to a
Collaborator for Review"), unless --force is passed. Always backs up the
current file before overwriting. Non-UTF-8 encoding and column-set
mismatches are hard stops that --force cannot bypass.
"""

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent.parent
CURRENT_SONGS_CSV = BASE_DIR / "data" / "processed" / "songs.csv"

YEAR_RE = re.compile(r"^\d{4}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_COLUMNS = {"release_year", "release_date"}
LENGTH_TOLERANCE = 0.20


def load_csv_strict_utf8(path: Path) -> pd.DataFrame:
    raw = path.read_bytes()
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"{path} is not valid UTF-8: {e}") from e
    return pd.read_csv(path, dtype=str, encoding="utf-8").fillna("")


def diff_songs(current: pd.DataFrame, incoming: pd.DataFrame) -> dict:
    flags = []
    changes = {"release_year": 0, "release_date": 0, "other": 0}
    other_examples = []

    current_ids = set(current["song_id"])
    incoming_ids = set(incoming["song_id"])
    missing_ids = current_ids - incoming_ids
    added_ids = incoming_ids - current_ids
    if missing_ids:
        flags.append(
            f"{len(missing_ids)} song_id(s) present in current data are missing "
            f"from the incoming file: {sorted(missing_ids)[:10]}"
        )
    if added_ids:
        flags.append(
            f"{len(added_ids)} song_id(s) in the incoming file are not in "
            f"current data: {sorted(added_ids)[:10]}"
        )

    current_by_id = current.set_index("song_id")
    incoming_by_id = incoming.set_index("song_id")
    shared_ids = current_ids & incoming_ids

    for song_id in shared_ids:
        cur_row = current_by_id.loc[song_id]
        inc_row = incoming_by_id.loc[song_id]

        cur_lyrics = cur_row.get("lyrics_clean", "")
        inc_lyrics = inc_row.get("lyrics_clean", "")
        if cur_lyrics:
            if not inc_lyrics.strip():
                flags.append(f"song_id {song_id}: lyrics_clean was non-empty and is now blank")
            else:
                length_diff = abs(len(inc_lyrics) - len(cur_lyrics)) / len(cur_lyrics)
                if length_diff > LENGTH_TOLERANCE:
                    flags.append(
                        f"song_id {song_id}: lyrics_clean length changed by "
                        f"{length_diff:.0%} (possible corruption)"
                    )

        for col in ("release_year", "release_date"):
            if cur_row.get(col, "") != inc_row.get(col, ""):
                changes[col] += 1

        year_val = inc_row.get("release_year", "")
        if year_val and not YEAR_RE.match(year_val):
            flags.append(f"song_id {song_id}: release_year '{year_val}' is not a 4-digit year")
        date_val = inc_row.get("release_date", "")
        if date_val and not DATE_RE.match(date_val):
            flags.append(f"song_id {song_id}: release_date '{date_val}' is not YYYY-MM-DD")

        other_cols = [c for c in current.columns if c not in DATE_COLUMNS and c != "song_id"]
        for col in other_cols:
            if cur_row.get(col, "") != inc_row.get(col, ""):
                changes["other"] += 1
                if len(other_examples) < 10:
                    other_examples.append(f"song_id {song_id}: column '{col}' changed unexpectedly")

    flags.extend(other_examples)
    return {"flags": flags, "changes": changes, "missing_ids": missing_ids, "added_ids": added_ids}


def run(incoming_path: Path, current_path: Path, force: bool) -> int:
    if not current_path.exists():
        print(f"Current songs file not found: {current_path}")
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

    result = diff_songs(current, incoming)

    print(f"Current songs: {len(current)}, incoming songs: {len(incoming)}")
    print(f"release_year changed: {result['changes']['release_year']}")
    print(f"release_date changed: {result['changes']['release_date']}")
    print(f"other unexpected column changes: {result['changes']['other']}")

    if result["flags"]:
        print(f"\n{len(result['flags'])} issue(s) found:")
        for flag in result["flags"]:
            print(f"  - {flag}")

        if not force:
            print("\nRefusing to overwrite data/processed/songs.csv. Review the issues above.")
            print("If they're expected, re-run with --force.")
            return 1
        print("\n--force passed: proceeding despite the issues above.")

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_path = current_path.parent / f"songs.backup-{timestamp}.csv"
    shutil.copy2(current_path, backup_path)
    print(f"\nBacked up current file to {backup_path}")

    incoming.to_csv(current_path, index=False)
    print(f"Wrote {len(incoming)} songs to {current_path}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("incoming", type=Path, help="Path to the returned/edited songs.csv")
    parser.add_argument(
        "--current", type=Path, default=CURRENT_SONGS_CSV,
        help="Path to the current canonical songs.csv (default: data/processed/songs.csv)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite even if issues are found")
    args = parser.parse_args()
    sys.exit(run(args.incoming, args.current, args.force))


if __name__ == "__main__":
    main()
