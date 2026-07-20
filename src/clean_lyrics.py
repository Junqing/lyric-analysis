"""
Cleans raw lyrics from songs.csv:
  - Strips Genius section markers ([Verso 1], [Coro], etc.)
  - Normalizes whitespace
  - Language-detects with langdetect; flags non-Spanish rows
  - Deduplicates by normalized title within each artist
  - Writes cleaned lyrics back into songs.csv (adds lyrics_clean column)
  - Also writes data/processed/songs.json for richer downstream use

Usage:
    python src/clean_lyrics.py
"""

import json
import re
import unicodedata
from pathlib import Path

import pandas as pd
from langdetect import detect, LangDetectException

BASE_DIR = Path(__file__).parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
RAW_DIR = BASE_DIR / "data" / "raw"
SONGS_CSV = PROCESSED_DIR / "songs.csv"
SONGS_JSON = PROCESSED_DIR / "songs.json"

SECTION_HEADER_RE = re.compile(r"\[.*?\]", re.UNICODE)
# Strips Genius header: "3 ContributorsSong Title Lyrics" at the start of raw text
GENIUS_HEADER_RE = re.compile(r"^\d+\s+contributors?\s*.+?Lyrics\s*", re.IGNORECASE | re.DOTALL)
CONTRIBUTOR_LINE_RE = re.compile(
    r"^\d+\s+contributor[s]?\s*$|^[A-Za-z]+ contributor[s]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
EMBED_FOOTER_RE = re.compile(r"\d+Embed$", re.MULTILINE)
WHITESPACE_RE = re.compile(r"\n{3,}")


def normalize_title(title: str) -> str:
    title = title.lower().strip()
    title = unicodedata.normalize("NFKD", title)
    title = "".join(c for c in title if not unicodedata.combining(c))
    title = re.sub(r"[^a-z0-9 ]", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def clean_lyrics(raw: str) -> str:
    if not raw:
        return ""
    text = GENIUS_HEADER_RE.sub("", raw, count=1)
    text = SECTION_HEADER_RE.sub("", text)
    text = CONTRIBUTOR_LINE_RE.sub("", text)
    text = EMBED_FOOTER_RE.sub("", text)
    text = WHITESPACE_RE.sub("\n\n", text)
    return text.strip()


def detect_language(text: str) -> str:
    if not text or len(text.split()) < 10:
        return "unknown"
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def load_lyrics_from_raw(raw_path: str) -> str:
    path = BASE_DIR / raw_path
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text())
        return data.get("lyrics") or ""
    except (json.JSONDecodeError, KeyError):
        return ""


def run():
    if not SONGS_CSV.exists():
        print("songs.csv not found. Run scrape_genius.py first.")
        return

    df = pd.read_csv(SONGS_CSV, dtype=str).fillna("")

    print(f"Loaded {len(df)} songs from songs.csv")

    if "lyrics_clean" not in df.columns:
        df["lyrics_clean"] = ""
    if "language" not in df.columns:
        df["language"] = ""

    for idx, row in df.iterrows():
        if row.get("lyrics_clean"):
            continue
        raw_lyrics = load_lyrics_from_raw(row["lyrics_raw_path"])
        cleaned = clean_lyrics(raw_lyrics)
        df.at[idx, "lyrics_clean"] = cleaned
        if not row.get("language"):
            df.at[idx, "language"] = detect_language(cleaned)

    # Deduplicate within each artist by normalized title
    df["_title_norm"] = df["title"].apply(normalize_title)
    before = len(df)
    df = df.sort_values("release_year").drop_duplicates(
        subset=["artist", "_title_norm"], keep="first"
    )
    df = df.drop(columns=["_title_norm"])
    after = len(df)

    if before != after:
        print(f"Deduplication removed {before - after} duplicate titles")

    # Language summary
    lang_counts = df["language"].value_counts()
    print("\nLanguage breakdown:")
    for lang, count in lang_counts.items():
        flag = " *** REVIEW ***" if lang not in ("es", "unknown") else ""
        print(f"  {lang}: {count}{flag}")

    non_spanish = df[~df["language"].isin(["es", "unknown"])]
    if not non_spanish.empty:
        print(f"\n{len(non_spanish)} songs flagged as non-Spanish:")
        for _, row in non_spanish.iterrows():
            print(f"  [{row['artist']}] {row['title']} (detected: {row['language']})")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(SONGS_CSV, index=False)
    print(f"\nWrote {len(df)} cleaned songs to {SONGS_CSV}")

    # Also write JSON
    records = df.to_dict(orient="records")
    SONGS_JSON.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    print(f"Wrote {SONGS_JSON}")


if __name__ == "__main__":
    run()
