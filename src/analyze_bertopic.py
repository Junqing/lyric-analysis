"""
Method 2: BERTopic unsupervised topic modeling.
Embeds lyrics with paraphrase-multilingual-MiniLM-L12-v2,
clusters with UMAP + HDBSCAN, generates c-TF-IDF topic labels.
Writes data/analysis/topics_bertopic.csv.

Output columns:
  song_id, artist, title, release_year,
  bertopic_topic_id, bertopic_topic_label, bertopic_prob

Usage:
    python src/analyze_bertopic.py
"""

import os
from pathlib import Path

import truststore
truststore.inject_into_ssl()

import certifi
import httpx
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("CURL_CA_BUNDLE", certifi.where())

# pyenv Python links against Homebrew OpenSSL; use its cert bundle for httpx
import ssl as _ssl
_HF_SSL_CTX = _ssl.create_default_context(cafile="/opt/homebrew/etc/openssl@3/cert.pem")
from huggingface_hub.utils._http import set_client_factory, close_session, hf_request_event_hook
set_client_factory(lambda: httpx.Client(
    event_hooks={"request": [hf_request_event_hook]},
    follow_redirects=True,
    timeout=None,
    verify=_HF_SSL_CTX,
))
close_session()

import pandas as pd
from bertopic import BERTopic
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
ANALYSIS_DIR = BASE_DIR / "data" / "analysis"
SONGS_CSV = PROCESSED_DIR / "songs.csv"
OUTPUT_CSV = ANALYSIS_DIR / "topics_bertopic.csv"
TOPIC_INFO_CSV = ANALYSIS_DIR / "topics_bertopic_info.csv"

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
MIN_TOPIC_SIZE = 10


def run():
    if not SONGS_CSV.exists():
        print("songs.csv not found. Run scrape_genius.py and clean_lyrics.py first.")
        return

    df = pd.read_csv(SONGS_CSV, dtype=str).fillna("")

    if "lyrics_clean" not in df.columns:
        print("lyrics_clean column missing. Run clean_lyrics.py first.")
        return

    # Filter to songs with meaningful lyrics
    mask = df["lyrics_clean"].str.split().str.len() > 20
    working = df[mask].copy().reset_index(drop=True)
    print(f"Running BERTopic on {len(working)} songs (filtered from {len(df)} total)")

    docs = working["lyrics_clean"].tolist()

    print(f"Loading embedding model: {EMBEDDING_MODEL}")
    embedding_model = SentenceTransformer(EMBEDDING_MODEL)

    print("Computing embeddings...")
    embeddings = embedding_model.encode(docs, show_progress_bar=True, batch_size=32)

    print("Fitting BERTopic model...")
    topic_model = BERTopic(
        embedding_model=embedding_model,
        min_topic_size=MIN_TOPIC_SIZE,
        nr_topics="auto",
        calculate_probabilities=True,
        verbose=True,
    )
    topics, probs = topic_model.fit_transform(docs, embeddings)

    topic_info = topic_model.get_topic_info()
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    topic_info.to_csv(TOPIC_INFO_CSV, index=False)
    print(f"Wrote topic info to {TOPIC_INFO_CSV}")
    print(f"\nDiscovered {len(topic_info) - 1} topics (excluding -1 outlier topic)")

    topic_labels = {}
    for _, row in topic_info.iterrows():
        tid = row["Topic"]
        label = row["Name"] if "Name" in row else f"topic_{tid}"
        topic_labels[tid] = label

    rows = []
    for i, (song_idx) in enumerate(working.index):
        song = working.iloc[i]
        rows.append({
            "song_id": song["song_id"],
            "artist": song["artist"],
            "title": song["title"],
            "release_year": song["release_year"],
            "bertopic_topic_id": topics[i],
            "bertopic_topic_label": topic_labels.get(topics[i], f"topic_{topics[i]}"),
            "bertopic_prob": round(float(probs[i].max()) if hasattr(probs[i], "__len__") else float(probs[i]), 4),
        })

    # Songs that were filtered out — add placeholder rows
    skipped = df[~mask].copy()
    for _, song in skipped.iterrows():
        rows.append({
            "song_id": song["song_id"],
            "artist": song["artist"],
            "title": song["title"],
            "release_year": song["release_year"],
            "bertopic_topic_id": -1,
            "bertopic_topic_label": "insufficient_lyrics",
            "bertopic_prob": 0.0,
        })

    result = pd.DataFrame(rows)
    result.to_csv(OUTPUT_CSV, index=False)
    print(f"\nWrote {len(result)} rows to {OUTPUT_CSV}")

    # Print top topics
    print("\nTop 10 topics by size:")
    print(topic_info.head(11).to_string(index=False))


if __name__ == "__main__":
    run()
