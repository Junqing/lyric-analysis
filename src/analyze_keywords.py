"""
Method 1: Spanish keyword-dictionary topic tagging.
Reads lexicons/*.txt and songs.csv, computes per-song topic hit counts
(raw + normalized by lyric word count), and writes data/analysis/topics_keywords.csv.

Output columns:
  song_id, artist, title, release_year,
  <topic>_hits, <topic>_score  (one pair per lexicon file)
  dominant_topic

Usage:
    python src/analyze_keywords.py
"""

import re
import unicodedata
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
ANALYSIS_DIR = BASE_DIR / "data" / "analysis"
LEXICONS_DIR = BASE_DIR / "lexicons"
SONGS_CSV = PROCESSED_DIR / "songs.csv"
OUTPUT_CSV = ANALYSIS_DIR / "topics_keywords.csv"


def load_lexicon(path: Path) -> list[str]:
    terms = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        terms.append(normalize_text(line))
    return terms


def normalize_text(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text


def count_hits(lyrics_norm: str, terms: list[str]) -> int:
    total = 0
    for term in terms:
        escaped = re.escape(term)
        total += len(re.findall(r"\b" + escaped + r"\b", lyrics_norm))
    return total


def run():
    if not SONGS_CSV.exists():
        print("songs.csv not found. Run scrape_genius.py and clean_lyrics.py first.")
        return

    df = pd.read_csv(SONGS_CSV, dtype=str).fillna("")

    if "lyrics_clean" not in df.columns:
        print("lyrics_clean column missing. Run clean_lyrics.py first.")
        return

    lexicon_files = sorted(LEXICONS_DIR.glob("*.txt"))
    if not lexicon_files:
        print(f"No lexicon files found in {LEXICONS_DIR}")
        return

    lexicons: dict[str, list[str]] = {}
    for lex_path in lexicon_files:
        topic = lex_path.stem
        lexicons[topic] = load_lexicon(lex_path)
        print(f"Loaded lexicon '{topic}': {len(lexicons[topic])} terms")

    rows = []
    for _, song in df.iterrows():
        lyrics_norm = normalize_text(song.get("lyrics_clean", ""))
        word_count = max(1, len(lyrics_norm.split()))

        row = {
            "song_id": song["song_id"],
            "artist": song["artist"],
            "title": song["title"],
            "release_year": song["release_year"],
        }

        topic_scores = {}
        for topic, terms in lexicons.items():
            hits = count_hits(lyrics_norm, terms)
            score = round(hits / word_count * 1000, 4)
            row[f"{topic}_hits"] = hits
            row[f"{topic}_score"] = score
            topic_scores[topic] = score

        # dominant topic = highest normalized score (0 if all zero)
        row["dominant_topic"] = max(topic_scores, key=topic_scores.get) if any(v > 0 for v in topic_scores.values()) else "none"
        rows.append(row)

    result = pd.DataFrame(rows)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_CSV, index=False)

    print(f"\nWrote {len(result)} rows to {OUTPUT_CSV}")

    # Summary
    print("\nTopic prevalence (% songs with ≥1 hit):")
    for topic in lexicons:
        hits_col = f"{topic}_hits"
        pct = (result[hits_col].astype(float) > 0).mean() * 100
        print(f"  {topic}: {pct:.1f}%")


if __name__ == "__main__":
    run()
