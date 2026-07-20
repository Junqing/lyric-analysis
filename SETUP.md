# SETUP — Lyric Analysis Project

This document describes the current state of the project and the steps required to reproduce or continue the work on any machine. It is intended to be read by a Claude session picking up this project from scratch.

---

## What This Project Is

A scientific data pipeline correlating lyric themes in the discographies of *Los Tigres del Norte* and *Los Tucanes de Tijuana* with political events across four axes (Mexican drug war, US–Mexico immigration, Mexican elections, US presidency), 1968–present. Full methodology is in `notes/methodology.md`.

---

## Current State (as of 2026-07-20)

| Stage | Status | Notes |
|---|---|---|
| Genius API scrape | Done | 558 Tigres + 317 Tucanes raw JSON files in `data/raw/` |
| songs.csv | Done | ~31,876 rows (includes duplicates pre-clean; also includes songs with empty lyrics) |
| clean_lyrics.py | Done | `lyrics_clean` column populated; language detection run; deduplication applied |
| Method 1 (keywords) | Done | `data/analysis/topics_keywords.csv` exists and is populated |
| Method 2 (BERTopic) | Blocked | Requires HuggingFace model weights; `huggingface.co` blocked by Zscaler at original machine |
| Method 3 (Hybrid/sentiment) | Blocked | Same HuggingFace/Zscaler issue |
| correlate.py | Partial | Ran on Method 1 only; `correlations.csv` and `timeseries.json` exist |
| export_dashboard.py | Done | `dashboard/data.json` is current |
| Dashboard | Working | Open `dashboard/index.html` via local HTTP server |
| Release date coverage | Incomplete | Many songs have empty `release_year`; dataset adjustment ongoing |

---

## Environment Setup

### Prerequisites

- Python 3.11+ (tested on 3.12)
- macOS system Python keychain trust injection (`truststore` package handles this automatically on macOS with pyenv Python)
- A Genius API token (free — register at https://genius.com/api-clients)
- Optionally: a Genius browser cookie for lyrics scraping (see below)

### Install

```bash
cd lyric-analysis
cp .env.example .env
# Edit .env and add GENIUS_API_TOKEN=your_token_here
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Note:** A `.venv` already exists at `lyric-analysis/.venv/`. On a new machine, re-create it as above. All pipeline scripts must be run using the venv interpreter (`.venv/bin/python`) or with the venv activated.

### HuggingFace access (for Methods 2 and 3)

Methods 2 and 3 require downloading model weights from `huggingface.co`. If your network allows it:

```bash
# Test access
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
```

If this fails due to network restrictions (corporate proxy, Zscaler, etc.), Methods 2 and 3 cannot run. The pipeline continues to work without them — Method 1 results and the dashboard remain fully functional.

---

## Running the Full Pipeline

Run scripts in this order:

```bash
source .venv/bin/activate

# 1. Scrape (skip if data/raw/ already populated — idempotent)
python src/scrape_genius.py --artist "Los Tigres del Norte"
python src/scrape_genius.py --artist "Los Tucanes de Tijuana"

# 2. Clean
python src/clean_lyrics.py

# 3. Analysis (can run in parallel; skip any blocked by HuggingFace)
python src/analyze_keywords.py
python src/analyze_bertopic.py   # requires HuggingFace access
python src/analyze_hybrid.py     # requires HuggingFace access

# 4. Correlate
python src/correlate.py

# 5. Export and serve
python src/export_dashboard.py
python -m http.server 8000 -d dashboard
# then open: http://localhost:8000
```

---

## Lyrics Scraping: Cloudflare Cookie

Genius.com uses Cloudflare to block automated lyrics requests. To get actual lyric text (not just metadata), you need to pass a valid browser cookie.

**How to get the cookie:**
1. Log in to genius.com in any browser
2. Open Developer Tools → Network tab → reload any page on genius.com
3. Click any request, look at Request Headers → find the `Cookie:` header
4. Copy the full value (it will contain `cf_clearance=...` among other tokens)

**How to use it:**
```bash
# Option A: pass on command line
python src/scrape_genius.py --artist "Los Tigres del Norte" --cookie "cf_clearance=...; _genius_ab=..."

# Option B: set in .env file
GENIUS_BROWSER_COOKIE=cf_clearance=...; _genius_ab=...
```

The `cf_clearance` token expires after some hours. Songs already cached with empty lyrics can be re-fetched by deleting their raw JSON file and re-running the scraper.

---

## Release Date Issue

A significant number of songs in the Genius database have incomplete or missing release date data. This affects:

- The time-series charts (songs without a year are excluded)
- The correlation analysis (only dated songs contribute)
- Summary statistics in the dashboard

**To improve year coverage:**
1. Manually check songs with empty `release_year` in `data/processed/songs.csv`
2. Edit `songs.csv` directly to add known years
3. Re-run `correlate.py` and `export_dashboard.py` to regenerate analysis

The dashboard automatically adapts to whatever year range and song count is present in `data.json` — the year sliders and stats are computed dynamically from the data at load time.

---

## Adding or Editing Political Events

Edit `data/processed/political_events.csv` directly. Schema:

```
event_id, date, axis, subtype, title, description, source_url, source_type, notes
```

- `axis` must be one of: `drug_war_mx`, `immigration_usmx`, `elections_mx`, `us_presidency`
- `date` format: `YYYY-MM-DD`
- `source_url` is required for the paper citation corpus
- After editing: run `python src/build_events.py` to validate schema/required fields, then re-run `correlate.py` → `export_dashboard.py`

---

## Sending Data to a Collaborator for Review

Many songs are missing `release_year`. To get help filling those in from
someone without Python or repo access:

1. Regenerate the dashboard so the bundled copy is current:
   ```bash
   python src/export_dashboard.py
   ```
   This refreshes `dashboard/songs.csv` (an exact copy of
   `data/processed/songs.csv`) and `dashboard/EDITING_INSTRUCTIONS.md`
   alongside `index.html`.
2. Zip the `dashboard/` folder and send it. The recipient only needs
   `index.html` (to view) and `songs.csv` + `EDITING_INSTRUCTIONS.md` (to
   edit) — no server, no Python, no repo access required.
3. When they send `songs.csv` back, validate and ingest it:
   ```bash
   python src/ingest_songs.py path/to/returned_songs.csv
   ```
   This compares the returned file against the current
   `data/processed/songs.csv` and refuses to overwrite it if it finds signs
   of trouble: a song that went missing, lyrics that got blanked out or
   changed length dramatically (a sign a spreadsheet app mangled the file),
   a `release_year`/`release_date` that isn't in the expected format, a
   non-UTF-8 file (breaks Spanish accents), or any column other than
   `release_year`/`release_date` that changed. It prints exactly what it
   found. If the flagged changes are expected, re-run with `--force`.
   Non-UTF-8 encoding and a changed column set are always hard stops —
   fix the file and try again rather than forcing those.
4. On success, `ingest_songs.py` backs up the previous file to
   `data/processed/songs.backup-<timestamp>.csv` before writing the new one,
   so you can always recover the prior version.
5. Re-run the pipeline to pick up the new dates:
   ```bash
   python src/analyze_keywords.py   # + analyze_bertopic.py / analyze_hybrid.py if you've run those
   python src/correlate.py
   python src/export_dashboard.py
   ```

---

## Editing Lexicons

`lexicons/*.txt` — one Spanish term per line; lines beginning with `#` are comments.

After editing any lexicon:
1. Re-run `python src/analyze_keywords.py`
2. Re-run `python src/correlate.py`
3. Re-run `python src/export_dashboard.py`

---

## File Structure

```
lyric-analysis/
├── CLAUDE.md              ← Instructions for Claude Code sessions
├── SETUP.md               ← This file
├── requirements.txt
├── .env.example
├── dashboard/
│   ├── index.html         ← Interactive dashboard (data is inlined — open directly, no server needed)
│   ├── app.js
│   ├── data.json          ← Generated — do not edit manually
│   ├── songs.csv          ← Generated copy of data/processed/songs.csv — safe for a collaborator to edit
│   ├── EDITING_INSTRUCTIONS.md ← Generated — instructions for a non-technical collaborator
│   └── prompts/           ← Session log JSON files
├── data/
│   ├── raw/               ← Per-song JSON from Genius (one file per song)
│   │   ├── los_tigres_del_norte/
│   │   └── los_tucanes_de_tijuana/
│   ├── processed/
│   │   ├── songs.csv      ← Canonical song table (edit here for manual fixes)
│   │   ├── songs.json     ← Generated mirror of songs.csv
│   │   └── political_events.csv
│   └── analysis/
│       ├── topics_keywords.csv
│       ├── topics_bertopic.csv  (absent if Method 2 not run)
│       ├── topics_hybrid.csv    (absent if Method 3 not run)
│       ├── correlations.csv
│       └── timeseries.json
├── lexicons/
│   ├── narco.txt
│   ├── migracion.txt
│   ├── politica_mx.txt
│   └── politica_us.txt
├── notes/
│   └── methodology.md     ← Academic-language methodology write-up
├── prompts/
│   └── session_01.json    ← Original session log
└── src/
    ├── scrape_genius.py
    ├── clean_lyrics.py
    ├── build_events.py
    ├── analyze_keywords.py
    ├── analyze_bertopic.py
    ├── analyze_hybrid.py
    ├── correlate.py
    ├── export_dashboard.py
    └── ingest_songs.py    ← Validates and re-ingests a collaborator's edited songs.csv
```

---

## What a New Claude Session Should Do First

1. Read `CLAUDE.md` (project overview and commands — Claude Code loads this automatically)
2. Read `SETUP.md` (this file — current state and blockers)
3. Read `notes/methodology.md` (full scientific context)
4. Check `data/processed/songs.csv` column counts and year coverage to assess current data quality
5. Check whether `data/analysis/topics_bertopic.csv` and `topics_hybrid.csv` exist yet
6. If HuggingFace is accessible on this machine, run Methods 2 and 3 (see pipeline above)
