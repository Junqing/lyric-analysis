"""
Fetches full discography for a given artist from Genius.
- Song metadata (title, album, date, URL): via Genius REST API (api.genius.com)
- Lyrics: web-scraped from genius.com using requests + BeautifulSoup with
  a real browser User-Agent and Cloudflare-friendly headers.

Saves raw per-song JSON to data/raw/<artist_slug>/<song_id>.json (idempotent).
Writes/updates data/processed/songs.csv with provenance metadata.

Usage:
    python src/scrape_genius.py --artist "Los Tigres del Norte"
    python src/scrape_genius.py --artist "Los Tucanes de Tijuana"
"""

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import truststore
truststore.inject_into_ssl()  # pyenv Python lacks macOS certs; inject system keychain

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
SONGS_CSV = PROCESSED_DIR / "songs.csv"

SONGS_CSV_COLUMNS = [
    "song_id", "artist", "title", "album", "release_year", "release_date",
    "genius_url", "retrieved_at", "lyrics_raw_path", "language", "word_count",
]

API_BASE = "https://api.genius.com"
GENIUS_WEB = "https://genius.com"

# Known Genius artist IDs — avoids Cloudflare-blocked public search endpoint.
ARTIST_IDS = {
    "los tigres del norte": 68345,
    "los tucanes de tijuana": 357527,
}

# Browser-like headers to bypass Cloudflare for lyrics scraping.
SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/26.5.2 Safari/605.1.15"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# To bypass Cloudflare: copy the Cookie header from your browser's DevTools
# (genius.com → Network tab → any request → Request Headers → Cookie)
# then pass it via --cookie "cf_clearance=...; _genius_ab=..."
BROWSER_COOKIE = os.environ.get("GENIUS_BROWSER_COOKIE", "")


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def load_existing_songs() -> pd.DataFrame:
    if SONGS_CSV.exists():
        return pd.read_csv(SONGS_CSV, dtype=str).fillna("")
    return pd.DataFrame(columns=SONGS_CSV_COLUMNS)


def save_songs(df: pd.DataFrame) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(SONGS_CSV, index=False)


def api_session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def web_session(cookie: str = "") -> requests.Session:
    s = requests.Session()
    s.headers.update(SCRAPE_HEADERS)
    if cookie:
        s.headers["Cookie"] = cookie
    return s


def get_all_artist_songs(api: requests.Session, artist_id: int, max_songs: int | None = None) -> list[dict]:
    songs = []
    page = 1
    while True:
        resp = api.get(f"{API_BASE}/artists/{artist_id}/songs", params={
            "per_page": 50,
            "page": page,
            "sort": "title",
        })
        resp.raise_for_status()
        data = resp.json()["response"]
        batch = data.get("songs", [])
        if not batch:
            break
        songs.extend(batch)
        print(f"  Page {page}: +{len(batch)} songs (total {len(songs)})")
        if max_songs and len(songs) >= max_songs:
            songs = songs[:max_songs]
            break
        next_page = data.get("next_page")
        if not next_page:
            break
        page = next_page
        time.sleep(0.3)
    return songs


def scrape_lyrics(web: requests.Session, path: str) -> str:
    url = GENIUS_WEB + path
    try:
        resp = web.get(url, timeout=8)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        containers = soup.find_all("div", attrs={"data-lyrics-container": "true"})
        if not containers:
            return ""
        lines = []
        for container in containers:
            for elem in container.descendants:
                if isinstance(elem, str):
                    lines.append(elem)
                elif elem.name == "br":
                    lines.append("\n")
        return "".join(lines).strip()
    except Exception as e:
        print(f"    Lyrics fetch error for {path}: {e}")
        return ""


def fetch_discography(artist_name: str, max_songs: int | None = None, cookie: str = "") -> None:
    token = os.environ.get("GENIUS_API_TOKEN")
    if not token:
        raise EnvironmentError("GENIUS_API_TOKEN not set in environment / .env")

    artist_id = ARTIST_IDS.get(artist_name.lower())
    if not artist_id:
        raise ValueError(f"Artist ID not known for '{artist_name}'. Add it to ARTIST_IDS.")

    api = api_session(token)
    effective_cookie = cookie or BROWSER_COOKIE
    web = web_session(effective_cookie)
    if not effective_cookie:
        print("WARNING: No browser cookie set. Genius lyrics will be blocked by Cloudflare.")
        print("  Set GENIUS_BROWSER_COOKIE in .env or pass --cookie '...' to enable lyrics.")
        print("  Songs metadata will still be fetched correctly.")

    artist_slug = slugify(artist_name)
    artist_raw_dir = RAW_DIR / artist_slug
    artist_raw_dir.mkdir(parents=True, exist_ok=True)

    existing = load_existing_songs()
    existing_ids = set(existing["song_id"].astype(str).tolist())

    print(f"Fetching discography for: {artist_name} (Genius ID: {artist_id})")
    print(f"Raw cache dir: {artist_raw_dir}")
    print(f"Already cached songs: {len(existing_ids)}")

    print("Fetching song list via API...")
    songs_meta = get_all_artist_songs(api, artist_id, max_songs)
    print(f"Found {len(songs_meta)} songs total")

    new_rows = []
    retrieved_at = datetime.now(timezone.utc).isoformat()

    for i, song in enumerate(songs_meta):
        song_id = str(song["id"])
        raw_path = artist_raw_dir / f"{song_id}.json"

        if raw_path.exists():
            # Already cached — load existing and skip lyrics fetch
            cached = json.loads(raw_path.read_text())
            lyrics = cached.get("lyrics", "")
            if not lyrics and song.get("lyrics_state") == "complete":
                # Re-fetch lyrics if missing
                print(f"  REFETCH lyrics: {song['title']}")
                lyrics = scrape_lyrics(web, song["path"])
                cached["lyrics"] = lyrics
                raw_path.write_text(json.dumps(cached, ensure_ascii=False, indent=2))
                time.sleep(1.5)
            else:
                print(f"  SKIP (cached): {song['title']}")
        else:
            print(f"  [{i+1}/{len(songs_meta)}] {song['title']}", end="", flush=True)
            lyrics = ""
            if song.get("lyrics_state") == "complete":
                lyrics = scrape_lyrics(web, song["path"])
                time.sleep(1.5)

            raw_data = dict(song)
            raw_data["lyrics"] = lyrics
            raw_path.write_text(json.dumps(raw_data, ensure_ascii=False, indent=2))
            words = len(lyrics.split()) if lyrics else 0
            print(f" ({words} words)")

        if song_id in existing_ids:
            continue

        lyrics = json.loads(raw_path.read_text()).get("lyrics", "")
        word_count = len(lyrics.split()) if lyrics else 0

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
        # Fallback to release_date string field
        if not release_date:
            release_date = song.get("release_date", "") or ""
            if release_date and len(release_date) >= 4:
                release_year = release_date[:4]

        album = song.get("album") or {}
        album_name = album.get("name", "") if isinstance(album, dict) else ""

        new_rows.append({
            "song_id": song_id,
            "artist": artist_name,
            "title": song.get("title", ""),
            "album": album_name,
            "release_year": release_year,
            "release_date": release_date,
            "genius_url": song.get("url", ""),
            "retrieved_at": retrieved_at,
            "lyrics_raw_path": str(raw_path.relative_to(BASE_DIR)),
            "language": song.get("language", ""),
            "word_count": str(word_count),
        })

    if new_rows:
        new_df = pd.DataFrame(new_rows, columns=SONGS_CSV_COLUMNS)
        updated = pd.concat([existing, new_df], ignore_index=True)
        save_songs(updated)
        print(f"\nAdded {len(new_rows)} new songs to songs.csv")
    else:
        print("\nNo new songs to add.")

    print(f"Total songs in CSV: {len(load_existing_songs())}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch artist discography from Genius")
    parser.add_argument("--artist", required=True, help="Artist name to search")
    parser.add_argument("--max-songs", type=int, default=None, help="Limit number of songs")
    parser.add_argument("--cookie", type=str, default="", help="Browser Cookie header from DevTools to bypass Cloudflare")
    args = parser.parse_args()
    fetch_discography(args.artist, args.max_songs, args.cookie)
