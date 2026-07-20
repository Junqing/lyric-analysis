# Collaborator data round-trip & repo cleanup — design

Date: 2026-07-20

## Problem

The `dashboard/` folder is now self-contained (see prior session: data is
inlined into `index.html`, no server required). The next step is to send
`dashboard/` to a collaborator so they can view the data and fill in missing
`release_year`/`release_date` values on songs, then send it back so the owner
can re-run analysis with the corrected dates.

Two constraints from the project owner:
- Python analysis stays owner-only; the collaborator only ever touches data,
  never scripts.
- Crawled (raw, immutable) data must stay separate from the tweakable,
  analysis-feeding data — the collaborator should only ever be able to touch
  the latter.

A secondary ask: clean up redundant/unnecessary files in the repo while here.

## Current state (verified by inspection)

- `data/raw/` — per-song scraped JSON from Genius. Gitignored, reproducible,
  not present in this checkout. Immutable in practice: `scrape_genius.py`
  only *appends* new `song_id`s to `songs.csv`, it never rewrites existing
  rows.
- `data/processed/songs.csv` — the canonical, already-deduped, already-edited
  song table (871 rows). `clean_lyrics.py` only fills `lyrics_clean` when
  currently blank and never overwrites already-populated fields (including
  `release_year`/`release_date`). So this file already behaves like the
  correct "tweakable, analysis-feeding" layer — manual date edits already
  survive re-scraping and re-cleaning today.
- Conclusion: the raw/processed separation the owner wants **already
  exists** architecturally. What's missing is (a) a copy of the processed
  table actually shipped to the collaborator, (b) a documented, safe way to
  bring their edits back in, and (c) repo cruft cleanup.

### Cleanup findings

- `prompts/Screenshot 2026-07-20 at 10.50.31.png` (790KB) — unreferenced
  anywhere in the repo. Accidental artifact. Delete.
- `src/build_events.py` — a real, working validator for
  `political_events.csv`. Not dead code, just missing from the documented
  command list in `CLAUDE.md`/`SETUP.md`. Document it, don't delete it.
- `.DS_Store`, `.venv/`, `data/raw/` — already correctly gitignored and
  untracked. No action needed.

## Design

### 1. Ship the editable table with the dashboard

`export_dashboard.py` gains a step that copies `data/processed/songs.csv` →
`dashboard/songs.csv` on every run (mirrors the existing `prompts/` copy
step). This keeps the shipped copy in sync with whatever `data.json` /
`index.html` currently reflect, every time the export script runs.

A new `dashboard/EDITING_INSTRUCTIONS.md` ships alongside it, written for a
non-technical recipient:
- Only edit `release_year` (YYYY) and `release_date` (YYYY-MM-DD) columns.
- Leave every other column untouched (song_id, lyrics, URLs, etc.).
- Save as CSV UTF-8 when done (specific guidance for Excel/Google Sheets).
- Send the file back to the owner.

The owner zips `dashboard/` and sends it. Full round trip: collaborator
edits `dashboard/songs.csv` in place in the folder they received, sends that
one file back.

### 2. Validated re-ingest (`src/ingest_songs.py`, new script)

Rather than a blind drop-in replacement (risk: spreadsheet apps can corrupt
multi-paragraph quoted CSV cells — embedded newlines in `lyrics_clean`,
UTF-8 → other encoding silently on save, auto-reformatted dates), the owner
runs:

```bash
python src/ingest_songs.py path/to/returned_songs.csv
```

This script:
1. Reads the returned file and the current `data/processed/songs.csv`.
2. Diffs `song_id` sets — reports any IDs missing or unexpectedly added.
3. For every row where the current file has non-empty `lyrics_clean`, checks
   the returned row's `lyrics_clean` is still non-empty and within 20% of
   the original character length (catches truncation/corruption). Flags
   mismatches.
4. Verifies the file decodes as strict UTF-8. Flags decode errors.
5. Validates `release_year` (blank or 4-digit int) and `release_date` (blank
   or `YYYY-MM-DD`) formats on every row; flags anything else (e.g. Excel
   serial numbers, `M/D/YYYY`).
6. Prints a summary: how many rows changed `release_year`/`release_date`
   (the expected, wanted edits), and how many other columns changed
   unexpectedly (should be zero — flag if not).
7. If any red flags were found, refuses to write and exits non-zero unless
   `--force` is passed.
8. On success, backs up the current `data/processed/songs.csv` to
   `data/processed/songs.backup-<timestamp>.csv` before overwriting it with
   the validated incoming file.

After ingest, the owner reruns the existing pipeline commands
(`analyze_keywords.py` [+ M2/M3 if run] → `correlate.py` →
`export_dashboard.py`) — no changes needed to those scripts since they
already read `data/processed/songs.csv` as-is.

### 3. Cleanup

- Delete `prompts/Screenshot 2026-07-20 at 10.50.31.png`.
- Add `build_events.py` to the command lists in `CLAUDE.md` and `SETUP.md`.

### 4. Docs

`SETUP.md` gets a new section: "Sending data to a collaborator for
review" documenting the zip → edit → ingest round trip end to end, plus the
`ingest_songs.py` usage and what its flags/output mean.

## Out of scope

- No change to `correlate.py`'s date-windowing logic (still year-granularity
  ± 2 years) — collecting `release_date` at month precision is for future
  use / record-keeping, not a request to rewrite the correlation math now.
- No new `data/curated/` directory or patch/override file format — the
  owner explicitly chose full-table drop-in replacement over a smaller
  overrides-patch file.
- No automated email/transfer mechanism — zipping and sending the folder
  stays a manual, out-of-band step for the owner.

## Testing

- `ingest_songs.py` gets exercised against: (a) a clean edited copy (only
  date columns changed) → succeeds without `--force`; (b) a copy with a
  blanked lyrics cell → refuses without `--force`, succeeds with it; (c) a
  copy with a missing song_id → flagged; (d) a non-UTF-8 saved copy →
  flagged.
- `export_dashboard.py` run end-to-end, confirm `dashboard/songs.csv` and
  `dashboard/EDITING_INSTRUCTIONS.md` appear and `dashboard/songs.csv`
  matches `data/processed/songs.csv` exactly.
