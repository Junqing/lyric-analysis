"""
Backfills `album` and `release_year`/`release_date` in data/processed/songs.csv
from the Genius per-song API endpoint.

Root cause of the gap: scrape_genius.py only ever calls the *list* endpoint
(GET /artists/{id}/songs), whose song objects are stripped of `album` and
usually of `release_date_components`. The full data lives on the *per-song*
endpoint (GET /songs/{id}), which the scraper never calls. Since `song_id`
in songs.csv is the Genius song ID, this is an exact per-song lookup —
inherently high-confidence, no fuzzy matching involved.

Only fills cells that are currently blank; never overwrites an existing
value. Backs up songs.csv before writing (mirrors ingest_songs.py).

Usage:
    python src/enrich_metadata.py            # enrich all rows missing data
    python src/enrich_metadata.py --limit 10  # dry-run-ish: only touch 10 rows
    python src/enrich_metadata.py --dry-run   # report what would change, don't write
"""

import argparse
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import truststore
truststore.inject_into_ssl()  # pyenv/Homebrew Python lacks macOS certs; inject system keychain

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
SONGS_CSV = BASE_DIR / "data" / "processed" / "songs.csv"
API_BASE = "https://api.genius.com"


def parse_release(song: dict) -> tuple[str, str]:
    """Same extraction logic as scrape_genius.py's list-endpoint parsing,
    applied here to the richer per-song response."""
    rdc = song.get("release_date_components") or {}
    release_year = str(rdc.get("year", "")) if rdc else ""
    mo = rdc.get("month")
    dy = rdc.get("day")
    release_date = ""
    if release_year:
        release_date = release_year
        if mo:
            release_date += f"-{mo:02d}"
            if dy:
                release_date += f"-{dy:02d}"
    if not release_date:
        release_date = song.get("release_date", "") or ""
        if release_date and len(release_date) >= 4:
            release_year = release_date[:4]
    return release_year, release_date


def fetch_song(session: requests.Session, song_id: str) -> dict | None:
    resp = session.get(f"{API_BASE}/songs/{song_id}", params={"text_format": "plain"}, timeout=15)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()["response"]["song"]


def fetch_album(session: requests.Session, album_id: int) -> dict | None:
    resp = session.get(f"{API_BASE}/albums/{album_id}", timeout=15)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()["response"]["album"]


def run(limit: int | None, dry_run: bool, rate_limit_s: float) -> int:
    token = os.environ.get("GENIUS_API_TOKEN")
    if not token:
        print("GENIUS_API_TOKEN not set in environment / .env — cannot call the Genius API.")
        return 1

    if not SONGS_CSV.exists():
        print(f"{SONGS_CSV} not found.")
        return 1

    df = pd.read_csv(SONGS_CSV, dtype=str).fillna("")

    # Enrich every row: albums are empty for all 871 songs, and some rows
    # missing release_year may still have a partial release_date to fill in.
    targets = df.index[
        (df["album"] == "") | (df["release_year"] == "") | (df["release_date"] == "")
    ].tolist()
    if limit:
        targets = targets[:limit]

    print(f"Total songs: {len(df)}, candidates to check: {len(targets)}")

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})

    stats = {
        "album_filled": 0, "year_filled": 0, "date_filled": 0,
        "year_from_album": 0, "not_found": 0, "errors": 0,
    }
    album_cache: dict[int, tuple[str, str]] = {}  # album_id -> (release_year, release_date)

    for n, idx in enumerate(targets, 1):
        row = df.loc[idx]
        song_id = row["song_id"]
        title = row["title"]
        print(f"  [{n}/{len(targets)}] {song_id} — {title}", end="", flush=True)

        try:
            song = fetch_song(session, song_id)
        except requests.RequestException as e:
            print(f" ERROR: {e}")
            stats["errors"] += 1
            time.sleep(rate_limit_s)
            continue

        if song is None:
            print(" NOT FOUND")
            stats["not_found"] += 1
            time.sleep(rate_limit_s)
            continue

        changed = []

        album_obj = song.get("album") or {}
        album_id = album_obj.get("id") if isinstance(album_obj, dict) else None
        album_name = album_obj.get("name", "") if isinstance(album_obj, dict) else ""
        if album_name and not row["album"]:
            df.at[idx, "album"] = album_name
            stats["album_filled"] += 1
            changed.append(f"album={album_name!r}")

        release_year, release_date = parse_release(song)
        from_album = False

        # The song's own release date is frequently null on Genius even when
        # its album has one (e.g. compilation tracks). Fall back to the
        # album's release date — still an exact Genius ID lookup, not a
        # fuzzy match, just one hop further via the album relationship.
        if not release_year and album_id:
            if album_id not in album_cache:
                try:
                    album = fetch_album(session, album_id)
                    album_cache[album_id] = parse_release(album) if album else ("", "")
                except requests.RequestException:
                    album_cache[album_id] = ("", "")
                time.sleep(rate_limit_s)
            release_year, release_date = album_cache[album_id]
            from_album = bool(release_year)

        if release_year and not row["release_year"]:
            df.at[idx, "release_year"] = release_year
            stats["year_filled"] += 1
            if from_album:
                stats["year_from_album"] += 1
            changed.append(f"year={release_year}{' (via album)' if from_album else ''}")
        if release_date and not row["release_date"] and not from_album:
            # Only trust day/month precision from the song's own record — an
            # album's release date is a same-year proxy, not necessarily the
            # song's exact release day, so don't write it into release_date.
            df.at[idx, "release_date"] = release_date
            stats["date_filled"] += 1
            changed.append(f"date={release_date}")

        print(f" {'-> ' + ', '.join(changed) if changed else '(nothing new)'}")
        time.sleep(rate_limit_s)

    print("\n--- Summary ---")
    print(f"Albums filled:        {stats['album_filled']}")
    print(f"Release years filled: {stats['year_filled']} (of which {stats['year_from_album']} via album fallback)")
    print(f"Release dates filled: {stats['date_filled']}")
    print(f"Not found on Genius:  {stats['not_found']}")
    print(f"Errors:               {stats['errors']}")

    still_missing_year = int((df["release_year"] == "").sum())
    still_missing_album = int((df["album"] == "").sum())
    print(f"Still missing release_year: {still_missing_year} / {len(df)}")
    print(f"Still missing album:        {still_missing_album} / {len(df)}")

    if dry_run:
        print("\n--dry-run passed: not writing songs.csv.")
        return 0

    if any(stats[k] for k in ("album_filled", "year_filled", "date_filled")):
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        backup_path = SONGS_CSV.parent / f"songs.backup-{timestamp}.csv"
        shutil.copy2(SONGS_CSV, backup_path)
        print(f"\nBacked up current file to {backup_path}")

        df.to_csv(SONGS_CSV, index=False)
        print(f"Wrote {len(df)} songs to {SONGS_CSV}")
    else:
        print("\nNo changes — leaving songs.csv untouched.")

    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Only check the first N candidate rows")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing songs.csv")
    parser.add_argument("--rate-limit", type=float, default=0.3, help="Seconds to sleep between API calls")
    args = parser.parse_args()
    sys.exit(run(args.limit, args.dry_run, args.rate_limit))


if __name__ == "__main__":
    main()
