"""
Validates and summarizes the political_events.csv file.
Checks schema integrity, required fields, date parsing, and source URLs.

Usage:
    python src/build_events.py
"""

from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent.parent
EVENTS_CSV = BASE_DIR / "data" / "processed" / "political_events.csv"

REQUIRED_COLUMNS = ["event_id", "date", "axis", "title", "source_url"]
VALID_AXES = {"drug_war_mx", "immigration_usmx", "elections_mx", "us_presidency"}


def run():
    if not EVENTS_CSV.exists():
        print(f"Events CSV not found: {EVENTS_CSV}")
        return

    df = pd.read_csv(EVENTS_CSV, dtype=str).fillna("")

    print(f"Loaded {len(df)} events")

    # Schema checks
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        print(f"MISSING COLUMNS: {missing_cols}")
        return

    # Check for required field completeness
    for col in REQUIRED_COLUMNS:
        empty = df[df[col].str.strip() == ""]
        if not empty.empty:
            print(f"WARNING: {len(empty)} rows missing '{col}':")
            for _, row in empty.iterrows():
                print(f"  {row['event_id']}: {row['title']}")

    # Validate axes
    invalid_axes = df[~df["axis"].isin(VALID_AXES)]
    if not invalid_axes.empty:
        print(f"\nINVALID AXES found:")
        for _, row in invalid_axes.iterrows():
            print(f"  {row['event_id']}: axis='{row['axis']}'")
    else:
        print("All axes valid.")

    # Parse dates
    df["parsed_date"] = pd.to_datetime(df["date"], errors="coerce")
    bad_dates = df[df["parsed_date"].isna()]
    if not bad_dates.empty:
        print(f"\nUNPARSABLE DATES:")
        for _, row in bad_dates.iterrows():
            print(f"  {row['event_id']}: date='{row['date']}'")
    else:
        print(f"All {len(df)} dates parse correctly.")

    # Summary by axis
    print("\nEvents per axis:")
    for axis, group in df.groupby("axis"):
        yr_min = pd.to_datetime(group["date"], errors="coerce").dt.year.min()
        yr_max = pd.to_datetime(group["date"], errors="coerce").dt.year.max()
        print(f"  {axis}: {len(group)} events ({int(yr_min)}–{int(yr_max)})")

    # Year distribution
    df["year"] = df["parsed_date"].dt.year
    print("\nEvents by decade:")
    df["decade"] = (df["year"] // 10 * 10).astype("Int64")
    print(df.groupby("decade").size().to_string())


if __name__ == "__main__":
    run()
