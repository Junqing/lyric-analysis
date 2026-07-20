# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Scientific data pipeline for analyzing lyrical content of **Los Tigres del Norte** and **Los Tucanes de Tijuana** over time, correlating thematic patterns with political events across four axes: Mexican drug war, US–Mexico immigration policy, Mexican elections, and US presidential terms.

## Commands

```bash
# Setup (venv already exists at .venv/ — re-create on a new machine)
cp .env.example .env          # then add your GENIUS_API_TOKEN
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Activate venv before any script
source .venv/bin/activate

# Data acquisition (run in order)
python src/scrape_genius.py --artist "Los Tigres del Norte"
python src/scrape_genius.py --artist "Los Tucanes de Tijuana"
python src/clean_lyrics.py

# Analysis (can run in any order after cleaning)
python src/analyze_keywords.py
python src/analyze_bertopic.py   # requires HuggingFace access
python src/analyze_hybrid.py     # requires HuggingFace access
python src/correlate.py

# Validate political events (optional, any time after editing political_events.csv)
python src/build_events.py

# Dashboard
python src/export_dashboard.py
# dashboard/index.html now works standalone — open it directly, no server needed

# Re-ingest a collaborator's edited songs.csv (see SETUP.md for the full round trip)
python src/ingest_songs.py path/to/returned_songs.csv
```

## Architecture

The pipeline has four sequential stages:

1. **Acquisition** (`scrape_genius.py`) — calls Genius API via `lyricsgenius`, saves per-song raw JSON to `data/raw/<artist_slug>/<song_id>.json` (idempotent), and writes `data/processed/songs.csv`.

2. **Cleaning** (`clean_lyrics.py`) — strips Genius section markers, normalizes, dedupes by title, language-detects via `langdetect`. Produces `songs.json` alongside the CSV.

3. **Three parallel NLP analyses** that all read `songs.csv` and write to `data/analysis/`:
   - `analyze_keywords.py` → `topics_keywords.csv` (Method 1: Spanish lexicons in `lexicons/`)
   - `analyze_bertopic.py` → `topics_bertopic.csv` (Method 2: multilingual embeddings + HDBSCAN)
   - `analyze_hybrid.py` → `topics_hybrid.csv` + `sentiment.csv` (Method 3: keywords + pysentimiento)

4. **Correlation** (`correlate.py`) reads all three topic CSVs + `data/processed/political_events.csv` and computes windowed Pearson/Spearman correlations → `correlations.csv`.

5. **Export** (`export_dashboard.py`) merges all outputs into a single `dashboard/data.json` payload consumed by the browser app.

## Key Data Files

| File | Description |
|------|-------------|
| `data/processed/songs.csv` | Canonical song table — `song_id, artist, title, album, release_year, release_date, genius_url, retrieved_at, lyrics_raw_path, language, word_count, lyrics_clean` |
| `data/processed/political_events.csv` | Hand-curated ~100 events — schema: `event_id, date, axis, title, description, source_url` |
| `data/analysis/topics_keywords.csv` | Per-song topic hits per lexicon, normalized by lyric length |
| `data/analysis/correlations.csv` | Per-`(topic, event_axis, method, artist)` Pearson r + p-value |
| `dashboard/data.json` | Generated payload — do NOT edit manually |
| `dashboard/songs.csv` | Generated copy of `songs.csv`, bundled for a collaborator to edit and return — see SETUP.md |

## Lexicons

`lexicons/*.txt` — one term per line, lowercase Spanish. Sourced from Astorga's narcocorrido research and migration studies glossaries. Edit these to refine Method 1 topic tagging.

## Scientific Notes

- Analysis stays in Spanish throughout — no translation to avoid artifact bias.
- `political_events.csv` must have `source_url` populated for all rows — this is the paper's primary citation corpus.
- BERTopic model is `paraphrase-multilingual-MiniLM-L12-v2`.
- Correlation uses a ±2-year event window vs. baseline (full-discography mean).
- The paper reports all three NLP methods side-by-side in the methods section.
