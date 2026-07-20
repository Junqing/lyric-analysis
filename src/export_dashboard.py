"""
Merges all analysis outputs into a single dashboard/data.json payload
for the interactive HTML dashboard.

Usage:
    python src/export_dashboard.py
"""

import json
import re
import shutil
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
ANALYSIS_DIR = BASE_DIR / "data" / "analysis"
DASHBOARD_DIR = BASE_DIR / "dashboard"

SONGS_CSV = PROCESSED_DIR / "songs.csv"
EVENTS_CSV = PROCESSED_DIR / "political_events.csv"
KEYWORDS_CSV = ANALYSIS_DIR / "topics_keywords.csv"
BERTOPIC_CSV = ANALYSIS_DIR / "topics_bertopic.csv"
HYBRID_CSV = ANALYSIS_DIR / "topics_hybrid.csv"
CORRELATIONS_CSV = ANALYSIS_DIR / "correlations.csv"
TIMESERIES_JSON = ANALYSIS_DIR / "timeseries.json"


def safe_read_csv(path: Path) -> pd.DataFrame | None:
    if path.exists():
        return pd.read_csv(path, dtype=str).fillna("")
    print(f"Warning: {path.name} not found — skipping")
    return None


def run():
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

    songs = safe_read_csv(SONGS_CSV)
    events = safe_read_csv(EVENTS_CSV)
    keywords = safe_read_csv(KEYWORDS_CSV)
    bertopic = safe_read_csv(BERTOPIC_CSV)
    hybrid = safe_read_csv(HYBRID_CSV)
    correlations = safe_read_csv(CORRELATIONS_CSV)

    payload = {}

    # --- Songs ---
    if songs is not None:
        song_records = []
        for _, row in songs.iterrows():
            song_records.append({
                "song_id": row["song_id"],
                "artist": row["artist"],
                "title": row["title"],
                "album": row.get("album", ""),
                "release_year": row["release_year"],
                "release_date": row.get("release_date", ""),
                "genius_url": row.get("genius_url", ""),
                "retrieved_at": row.get("retrieved_at", ""),
                "language": row.get("language", ""),
                "word_count": row.get("word_count", ""),
                "lyrics_preview": " ".join(row.get("lyrics_clean", "").split()[:80]),
                "lyrics": row.get("lyrics_clean", ""),
            })
        payload["songs"] = song_records
        print(f"Songs: {len(song_records)}")

    # --- Events ---
    if events is not None:
        event_records = events.to_dict(orient="records")
        payload["events"] = event_records
        print(f"Events: {len(event_records)}")

    # --- Topic analyses (per method) ---
    payload["topics"] = {}

    if keywords is not None:
        topic_cols = [c for c in keywords.columns if c.endswith("_score")]
        topic_names = [c.replace("_score", "") for c in topic_cols]
        kw_records = []
        for _, row in keywords.iterrows():
            rec = {"song_id": row["song_id"], "dominant_topic": row.get("dominant_topic", "")}
            for t in topic_names:
                rec[f"{t}_hits"] = row.get(f"{t}_hits", "0")
                rec[f"{t}_score"] = row.get(f"{t}_score", "0")
            kw_records.append(rec)
        payload["topics"]["keywords"] = {
            "topic_names": topic_names,
            "records": kw_records,
        }
        print(f"Keyword topic records: {len(kw_records)}")

    if bertopic is not None:
        bt_records = bertopic[["song_id", "bertopic_topic_id", "bertopic_topic_label", "bertopic_prob"]].to_dict(orient="records")
        payload["topics"]["bertopic"] = {
            "records": bt_records,
        }
        print(f"BERTopic records: {len(bt_records)}")

    if hybrid is not None:
        hy_records = hybrid[["song_id", "topic_tags", "sentiment_label", "sentiment_score", "emotion_label", "emotion_score"]].to_dict(orient="records")
        payload["topics"]["hybrid"] = {
            "records": hy_records,
        }
        print(f"Hybrid records: {len(hy_records)}")

    # --- Correlations ---
    if correlations is not None:
        payload["correlations"] = correlations.to_dict(orient="records")
        print(f"Correlation rows: {len(correlations)}")

    # --- Time series ---
    if TIMESERIES_JSON.exists():
        payload["timeseries"] = json.loads(TIMESERIES_JSON.read_text())
        print(f"Time series keys: {len(payload['timeseries'])}")

    # --- Metadata ---
    if songs is not None:
        years = pd.to_numeric(songs["release_year"], errors="coerce")
        dated = years.dropna()
        payload["meta"] = {
            "artists": sorted(songs["artist"].dropna().unique().tolist()),
            "year_min": int(dated.min()) if not dated.empty else 1968,
            "year_max": int(dated.max()) if not dated.empty else 2025,
            "songs_total": len(songs),
            "songs_with_year": int(dated.notna().sum()),
            "songs_no_year": int(years.isna().sum()),
            "methods": list(payload.get("topics", {}).keys()),
            "event_axes": sorted(events["axis"].dropna().unique().tolist()) if events is not None else [],
        }

    output_path = DASHBOARD_DIR / "data.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    size_kb = output_path.stat().st_size / 1024
    print(f"\nWrote dashboard payload to {output_path} ({size_kb:.1f} KB)")

    # --- Copy prompts into dashboard/ so they're reachable when serving from project root ---
    prompts_src = BASE_DIR / "prompts"
    prompts_dst = DASHBOARD_DIR / "prompts"
    sessions = {}
    if prompts_src.exists():
        prompts_dst.mkdir(parents=True, exist_ok=True)
        for f in prompts_src.glob("*.json"):
            shutil.copy2(f, prompts_dst / f.name)
            sessions[f.name] = json.loads(f.read_text())
        print(f"Copied {len(list(prompts_src.glob('*.json')))} prompt file(s) to {prompts_dst}")

    # --- Bundle an editable copy of songs.csv + instructions for a collaborator ---
    bundle_editable_songs()

    # --- Inline data + sessions into index.html so it opens standalone (no server) ---
    inject_inline_data(payload, sessions)


EDITING_INSTRUCTIONS = """\
# Editing songs.csv

This folder contains an interactive dashboard (`index.html`) and a spreadsheet
(`songs.csv`) with every song in the dataset.

## What to do

Many songs are missing a release year, which means they don't show up in the
timeline or topic charts. If you know (or can look up) when a song was
released, please fill it in.

1. Open `songs.csv` in Excel, Google Sheets, or Numbers.
2. Find rows where `release_year` is blank.
3. Fill in `release_year` (a 4-digit year, e.g. `1998`) and, if you know the
   exact date, `release_date` (format `YYYY-MM-DD`, e.g. `1998-06-15`).
4. Leave every other column exactly as it is — especially `lyrics_clean`,
   `song_id`, and `genius_url`. Those are used internally, and changing them
   (even by accident) can break the re-import.
5. When you're done, save the file:
   - **Excel:** File → Save As → File Format: "CSV UTF-8 (Comma delimited)".
     Do NOT use the plain "CSV" option — it can save with the wrong
     character encoding and break the Spanish accents.
   - **Google Sheets:** File → Download → Comma-separated values (.csv) —
     this is UTF-8 by default, no extra steps needed.
   - **Numbers:** File → Export To → CSV → Text Encoding: Unicode (UTF-8).
6. Send `songs.csv` back. You don't need to send anything else.

## Viewing the data

Open `index.html` in any browser — no internet connection or installation
needed. Use the Analysis tab for charts, Lyrics Browser to read individual
songs, and Political Events for the reference timeline the analysis is
compared against.
"""


def bundle_editable_songs() -> None:
    if not SONGS_CSV.exists():
        print(f"Warning: {SONGS_CSV} not found — skipping editable songs.csv bundle")
        return
    dst = DASHBOARD_DIR / "songs.csv"
    shutil.copy2(SONGS_CSV, dst)
    (DASHBOARD_DIR / "EDITING_INSTRUCTIONS.md").write_text(EDITING_INSTRUCTIONS)
    print(f"Bundled {dst} and EDITING_INSTRUCTIONS.md for collaborator hand-off")


def inject_inline_data(payload: dict, sessions: dict) -> None:
    index_path = DASHBOARD_DIR / "index.html"
    html = index_path.read_text()

    def js_json(obj):
        return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")

    block = (
        "<!-- INLINE_DATA_START -->\n"
        "<!-- Populated by src/export_dashboard.py — do not edit by hand -->\n"
        f"<script>window.__DASHBOARD_DATA__ = {js_json(payload)};\n"
        f"window.__SESSION_DATA__ = {js_json(sessions)};</script>\n"
        "<!-- INLINE_DATA_END -->"
    )

    pattern = re.compile(
        r"<!-- INLINE_DATA_START -->.*?<!-- INLINE_DATA_END -->", re.DOTALL
    )
    if not pattern.search(html):
        raise RuntimeError(
            "index.html is missing the INLINE_DATA_START/END markers — cannot inject data"
        )
    html = pattern.sub(lambda m: block, html)
    index_path.write_text(html)

    size_kb = index_path.stat().st_size / 1024
    print(f"Embedded data + {len(sessions)} session file(s) into {index_path} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    run()
