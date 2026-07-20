"""
Method 3: Hybrid analysis — keyword topic tags (from Method 1) + Spanish sentiment
via pysentimiento (RoBERTa-based, trained on Spanish social media/text).

Reads topics_keywords.csv + songs.csv.
Writes data/analysis/topics_hybrid.csv and data/analysis/sentiment.csv.

Output (topics_hybrid.csv) columns:
  song_id, artist, title, release_year,
  topic_tags (pipe-separated list of topics with hits),
  sentiment_label (POS/NEG/NEU),
  sentiment_score,
  emotion_label,
  emotion_score

Usage:
    python src/analyze_hybrid.py
"""

from pathlib import Path

import pandas as pd
from pysentimiento import create_analyzer

BASE_DIR = Path(__file__).parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
ANALYSIS_DIR = BASE_DIR / "data" / "analysis"
SONGS_CSV = PROCESSED_DIR / "songs.csv"
KEYWORDS_CSV = ANALYSIS_DIR / "topics_keywords.csv"
OUTPUT_CSV = ANALYSIS_DIR / "topics_hybrid.csv"
SENTIMENT_CSV = ANALYSIS_DIR / "sentiment.csv"

MAX_TOKENS = 512


def truncate_for_model(text: str, max_words: int = 200) -> str:
    words = text.split()
    return " ".join(words[:max_words])


def run():
    for required in [SONGS_CSV, KEYWORDS_CSV]:
        if not required.exists():
            print(f"Required file not found: {required}")
            return

    songs = pd.read_csv(SONGS_CSV, dtype=str).fillna("")
    keywords = pd.read_csv(KEYWORDS_CSV, dtype=str).fillna("")

    merged = songs.merge(keywords, on="song_id", how="left", suffixes=("", "_kw"))

    topic_cols = [c for c in keywords.columns if c.endswith("_hits")]
    topic_names = [c.replace("_hits", "") for c in topic_cols]

    print(f"Loading sentiment analyzer (Spanish)...")
    sentiment_analyzer = create_analyzer(task="sentiment", lang="es")

    print(f"Loading emotion analyzer (Spanish)...")
    emotion_analyzer = create_analyzer(task="emotion", lang="es")

    print(f"Analyzing {len(merged)} songs...")

    hybrid_rows = []
    sentiment_rows = []

    for idx, row in merged.iterrows():
        song_id = row["song_id"]
        lyrics = row.get("lyrics_clean", "")
        text_snippet = truncate_for_model(lyrics)

        # Topic tags from keyword method
        active_topics = []
        for topic in topic_names:
            hits_col = f"{topic}_hits"
            if hits_col in row and str(row.get(hits_col, "0")).strip() not in ("0", "", "nan"):
                try:
                    if int(float(row[hits_col])) > 0:
                        active_topics.append(topic)
                except (ValueError, TypeError):
                    pass
        topic_tags = "|".join(active_topics) if active_topics else "none"

        # Sentiment
        sentiment_label = "NEU"
        sentiment_score = 0.0
        emotion_label = "others"
        emotion_score = 0.0

        if text_snippet:
            try:
                sent_result = sentiment_analyzer.predict(text_snippet)
                sentiment_label = sent_result.output
                sentiment_score = round(max(sent_result.probas.values()), 4)
            except Exception as e:
                print(f"  Sentiment error for {row.get('title', song_id)}: {e}")

            try:
                emo_result = emotion_analyzer.predict(text_snippet)
                emotion_label = emo_result.output
                emotion_score = round(max(emo_result.probas.values()), 4)
            except Exception as e:
                print(f"  Emotion error for {row.get('title', song_id)}: {e}")

        hybrid_rows.append({
            "song_id": song_id,
            "artist": row.get("artist", row.get("artist_x", "")),
            "title": row.get("title", row.get("title_x", "")),
            "release_year": row.get("release_year", row.get("release_year_x", "")),
            "topic_tags": topic_tags,
            "sentiment_label": sentiment_label,
            "sentiment_score": sentiment_score,
            "emotion_label": emotion_label,
            "emotion_score": emotion_score,
        })

        sentiment_rows.append({
            "song_id": song_id,
            "sentiment_label": sentiment_label,
            "sentiment_score": sentiment_score,
            "emotion_label": emotion_label,
            "emotion_score": emotion_score,
        })

        if (idx + 1) % 50 == 0:
            print(f"  Processed {idx + 1}/{len(merged)}")

    hybrid_df = pd.DataFrame(hybrid_rows)
    sentiment_df = pd.DataFrame(sentiment_rows)

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    hybrid_df.to_csv(OUTPUT_CSV, index=False)
    sentiment_df.to_csv(SENTIMENT_CSV, index=False)

    print(f"\nWrote {len(hybrid_df)} rows to {OUTPUT_CSV}")
    print(f"Wrote {len(sentiment_df)} rows to {SENTIMENT_CSV}")

    # Summary
    print("\nSentiment distribution:")
    print(hybrid_df["sentiment_label"].value_counts().to_string())
    print("\nEmotion distribution:")
    print(hybrid_df["emotion_label"].value_counts().to_string())


if __name__ == "__main__":
    run()
