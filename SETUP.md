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
| enrich_metadata.py | Done | Backfilled `album` (0→757/871) and `release_year` (173→765/871) via Genius per-song + album-fallback lookups |
| Method 1 (keywords) | Done | `data/analysis/topics_keywords.csv` exists and is populated |
| Method 2 (BERTopic) | Done | `huggingface.co` reachable on this machine (Zscaler block from the original machine no longer applies); `topics_bertopic.csv` + `topics_bertopic_info.csv` populated, 6 topics found |
| Method 3 (Hybrid/sentiment) | Done | `topics_hybrid.csv` + `sentiment.csv` populated |
| correlate.py | Done | Ran on all 3 methods; `correlations.csv` (168 rows) and `timeseries.json` exist |
| export_dashboard.py | Done | `dashboard/data.json` is current, includes methodology + lexicon payloads |
| Dashboard | Working | Open `dashboard/index.html` directly — standalone, no server needed. Tabs: Analysis, Lyrics Browser, Political Events (table + timeline), Methodology, Lexicon, Initial Prompt |
| Release date coverage | Mostly complete | 106/871 songs (12%) still lack a release year — no album on Genius to fall back to |
| Collaborator round trip | Working | `songs.csv`, `political_events.csv`, `lexicons/*.txt` all have bundled editable copies + validated ingest scripts — see below |

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

Methods 2 and 3 require downloading model weights from `huggingface.co`, and `torch` needs Python 3.11/3.12 (no wheels for newer interpreters as of this writing). A `.python-version` file in the repo root pins 3.12.13 via `pyenv` for this reason — run `pyenv install 3.12.13` if you don't have it, then recreate `.venv` as below. If your network allows it:

```bash
# Test access
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
```

If this fails due to network restrictions (corporate proxy, Zscaler, etc.), Methods 2 and 3 cannot run. The pipeline continues to work without them — Method 1 results and the dashboard remain fully functional. (Confirmed working as of 2026-07-20 — the Zscaler block noted in earlier project history no longer applies on this machine.)

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

# 2b. Backfill album/release date from Genius (optional, safe to re-run — only fills blanks)
python src/enrich_metadata.py

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
1. Run `python src/enrich_metadata.py` — backfills `album` and `release_year`/`release_date`
   from Genius (per-song endpoint, falling back to the song's album release year when the
   song's own record has no date). Only fills blanks; safe to re-run.
2. For any remaining gaps, manually check songs with empty `release_year` in
   `data/processed/songs.csv` and edit directly, or use the collaborator round-trip below.
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
- If you received an edited copy back from a collaborator (see below) instead of editing directly, use `python src/ingest_events.py path/to/returned_political_events.csv` rather than overwriting the file yourself — it validates before writing.

---

## Sending Data to a Collaborator for Review

Three files can be handed to someone without Python or repo access: `songs.csv`
(missing release years), `political_events.csv` (event review/additions), and
`lexicons/*.txt` (Spanish term lists). Use whichever apply — you don't need to
send all three.

1. Regenerate the dashboard so the bundled copies are current:
   ```bash
   python src/export_dashboard.py
   ```
   This refreshes `dashboard/songs.csv`, `dashboard/political_events.csv`,
   `dashboard/lexicons/*.txt`, and `dashboard/EDITING_INSTRUCTIONS.md`
   alongside `index.html`.
2. Zip the `dashboard/` folder and send it. `index.html` (to view — all data
   is inlined, works standalone) plus whichever of the three editable files
   apply — no server, no Python, no repo access required. `EDITING_INSTRUCTIONS.md`
   walks the collaborator through all three.
3. When they send a file back, validate and ingest it with the matching script:
   ```bash
   python src/ingest_songs.py path/to/returned_songs.csv
   python src/ingest_events.py path/to/returned_political_events.csv
   python src/ingest_lexicons.py path/to/returned/lexicons/
   ```
   Each one compares the returned file(s) against the current canonical
   version and refuses to overwrite it if it finds signs of trouble —
   `ingest_songs.py`: a song that went missing, lyrics blanked out or changed
   length dramatically, a malformed `release_year`/`release_date`, non-UTF-8
   encoding, or an unexpected column change. `ingest_events.py`: a deleted
   event, an invalid `axis`, a malformed `date`, or a blank required field
   (new events are expected and not flagged). `ingest_lexicons.py`: a renamed
   file or section header (adding/removing terms within a section is
   expected and not flagged). Each prints exactly what it found; if the
   flagged changes are expected, re-run with `--force`. Non-UTF-8 encoding
   and structural mismatches (columns, file sets, section headers) are
   always hard stops that `--force` cannot bypass.
4. On success, each script backs up the previous file(s) first —
   `data/processed/songs.backup-<timestamp>.csv`,
   `data/processed/political_events.backup-<timestamp>.csv`, or
   `lexicons.backup-<timestamp>/` — so you can always recover the prior version.
5. Re-run the affected parts of the pipeline:
   ```bash
   # if songs.csv or lexicons changed:
   python src/analyze_keywords.py   # + analyze_bertopic.py / analyze_hybrid.py if you've run those
   # always, if anything changed:
   python src/correlate.py
   python src/export_dashboard.py
   ```

---

## File Structure

```
lyric-analysis/
├── README.md              ← Public-facing project overview
├── CLAUDE.md              ← Instructions for Claude Code sessions
├── SETUP.md               ← This file
├── requirements.txt
├── .env.example
├── .python-version        ← Pins 3.12.13 via pyenv (torch has no 3.14 wheels yet)
├── dashboard/
│   ├── index.html         ← Interactive dashboard (data is inlined — open directly, no server needed)
│   ├── app.js
│   ├── plotly-2.32.0.min.js
│   ├── data.json          ← Generated — do not edit manually
│   ├── songs.csv          ← Generated copy of data/processed/songs.csv — safe for a collaborator to edit
│   ├── political_events.csv ← Generated copy of data/processed/political_events.csv — safe to edit
│   ├── lexicons/           ← Generated copies of lexicons/*.txt — safe to edit
│   ├── EDITING_INSTRUCTIONS.md ← Generated — instructions for a non-technical collaborator
│   └── prompts/           ← Session log JSON files
├── data/
│   ├── raw/               ← Per-song JSON from Genius (one file per song, gitignored)
│   │   ├── los_tigres_del_norte/
│   │   └── los_tucanes_de_tijuana/
│   ├── processed/
│   │   ├── songs.csv      ← Canonical song table (edit here for manual fixes)
│   │   ├── songs.json     ← Generated mirror of songs.csv
│   │   └── political_events.csv
│   └── analysis/
│       ├── topics_keywords.csv        (Method 1)
│       ├── topics_bertopic.csv        (Method 2)
│       ├── topics_bertopic_info.csv   (Method 2 topic summary)
│       ├── topics_hybrid.csv          (Method 3)
│       ├── sentiment.csv              (Method 3)
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
    ├── enrich_metadata.py  ← Backfills album/release_year from Genius per-song + album lookups
    ├── build_events.py
    ├── analyze_keywords.py
    ├── analyze_bertopic.py
    ├── analyze_hybrid.py
    ├── correlate.py
    ├── export_dashboard.py
    ├── ingest_songs.py     ← Validates and re-ingests a collaborator's edited songs.csv
    ├── ingest_events.py    ← Validates and re-ingests a collaborator's edited political_events.csv
    └── ingest_lexicons.py  ← Validates and re-ingests a collaborator's edited lexicons/
```

---

## What a New Claude Session Should Do First

1. Read `CLAUDE.md` (project overview and commands — Claude Code loads this automatically)
2. Read `SETUP.md` (this file — current state and blockers)
3. Read `notes/methodology.md` (full scientific context)
4. Check `data/processed/songs.csv` column counts and year coverage to assess current data quality
5. Check whether `data/analysis/topics_bertopic.csv` and `topics_hybrid.csv` exist yet
6. If HuggingFace is accessible on this machine, run Methods 2 and 3 (see pipeline above)
7. If many songs are missing `release_year`/`album`, try `python src/enrich_metadata.py` first — it usually resolves most of the gap
