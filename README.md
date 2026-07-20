# Lyric Analysis: Los Tigres del Norte & Los Tucanes de Tijuana

A data pipeline correlating the lyrical themes of two major norteño/corrido groups with political events in Mexico and the US, 1968–present.

**Research question:** does thematic variation in the discography of *Los Tigres del Norte* (founded 1968) and *Los Tucanes de Tijuana* (founded 1987) correlate with historical events along four political axes — the Mexican drug war, US–Mexico immigration policy, Mexican elections, and US presidential terms?

Full write-up: [`notes/methodology.md`](notes/methodology.md).

## What's here

- **871 songs** (557 Tigres, 314 Tucanes) scraped from Genius, cleaned, language-detected, and deduplicated
- **65 hand-curated political events** across the four axes, each with a cited primary source
- **Three independent NLP methods**, run side by side for cross-validation:
  1. **Keyword lexicons** — four hand-built Spanish term dictionaries (`lexicons/`)
  2. **BERTopic** — multilingual sentence embeddings + HDBSCAN clustering
  3. **Hybrid** — keyword tags + Spanish sentiment/emotion classification (`pysentimiento`)
- **Correlation analysis** — windowed Pearson/Spearman correlations between yearly topic prevalence and event-axis activity
- **An interactive dashboard** (`dashboard/index.html`) — opens standalone in any browser, no server or install needed. Tabs for the correlation charts, a lyrics browser, the political events reference (table + timeline), the methodology write-up, and the lexicons themselves.

## Quick start

```bash
git clone https://github.com/Junqing/lyric-analysis.git
cd lyric-analysis
cp .env.example .env          # add your own GENIUS_API_TOKEN (free: https://genius.com/api-clients)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python src/export_dashboard.py
open dashboard/index.html     # or just double-click it
```

That regenerates the dashboard from the data already in the repo. To re-run the full pipeline from scratch (re-scrape, re-analyze, re-correlate), see [`SETUP.md`](SETUP.md).

## Documentation map

| File | For |
|---|---|
| [`SETUP.md`](SETUP.md) | Full environment setup, pipeline run order, current data-quality state, and the collaborator hand-off workflow |
| [`CLAUDE.md`](CLAUDE.md) | Architecture reference and command list (written for AI coding assistants, useful for humans too) |
| [`notes/methodology.md`](notes/methodology.md) | The scientific write-up — corpus construction, method details, statistics, known limitations, references |

## Collaborator hand-off

Non-technical collaborators can review and correct the data without any Python or repo access: zip the `dashboard/` folder and send it. They open `index.html` to see everything, edit whichever of `songs.csv` / `political_events.csv` / `lexicons/*.txt` applies (see the bundled `EDITING_INSTRUCTIONS.md`), and send it back. Each file has a matching `src/ingest_*.py` script that validates the return before merging it in. Details in [`SETUP.md`](SETUP.md#sending-data-to-a-collaborator-for-review).

## Data sources

- Lyrics and metadata: [Genius API](https://genius.com/api-clients) via `lyricsgenius`
- Political events: government archives, peer-reviewed journals (DOI-linked), and established news organizations — every event cites a `source_url`
- Lexicons: built from Astorga (2005) *El siglo de las drogas* and Wald (2001) *Narcocorrido*, plus migration-studies glossaries and manual curation

See [`notes/methodology.md`](notes/methodology.md) for the full reference list.
