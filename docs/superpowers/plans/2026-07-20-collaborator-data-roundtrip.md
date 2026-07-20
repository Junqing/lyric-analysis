# Collaborator Data Round-Trip & Repo Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the repo owner zip `dashboard/` and send it to a non-technical collaborator, who fills in missing song release dates in a plain CSV and sends it back, and the owner can safely re-ingest those edits into the analysis pipeline.

**Architecture:** `export_dashboard.py` gains a step that copies the canonical `data/processed/songs.csv` into `dashboard/songs.csv` plus a static instructions file, every time it runs. A new standalone script, `src/ingest_songs.py`, validates a returned CSV against the current one (encoding, missing/added songs, corrupted lyrics, malformed dates, unexpected column changes) before backing up and overwriting `data/processed/songs.csv`. Repo cleanup and doc updates round it out.

**Tech Stack:** Python 3, pandas (already a project dependency). No new dependencies.

## Global Constraints

- No pytest or other test framework exists in this repo; verification is done by running scripts directly and inspecting output/exit codes, matching the existing project convention (`build_events.py`, `clean_lyrics.py`, etc. are all validated this way).
- All new/modified Python files must run inside the project's `.venv` (`source .venv/bin/activate` first).
- Column-set mismatches and non-UTF-8 encoding are **hard stops** in `ingest_songs.py` — `--force` cannot bypass them.
- `release_year` must be blank or exactly 4 digits (`^\d{4}$`); `release_date` must be blank or `YYYY-MM-DD` (`^\d{4}-\d{2}-\d{2}$`).
- Lyrics corruption check tolerance: flag if `lyrics_clean` length changes by more than 20% relative to the current value (only checked when the current value is non-empty).
- No changes to `correlate.py`'s date-windowing logic and no new `data/curated/` directory — both explicitly out of scope per the design spec (`docs/superpowers/specs/2026-07-20-collaborator-data-roundtrip-design.md`).

---

## Task 1: Repo cleanup

**Files:**
- Delete: `prompts/Screenshot 2026-07-20 at 10.50.31.png`
- Modify: `CLAUDE.md`
- Modify: `SETUP.md`

**Interfaces:** None — this task touches no code, only removes a file and adds documentation lines.

- [ ] **Step 1: Delete the unreferenced screenshot**

```bash
git rm "prompts/Screenshot 2026-07-20 at 10.50.31.png"
```

Expected: file removed from working tree and staged for deletion.

- [ ] **Step 2: Document `build_events.py` in CLAUDE.md's Commands section**

In `CLAUDE.md`, find this block:

```
# Dashboard
python src/export_dashboard.py
python -m http.server 8000 -d dashboard   # then open http://localhost:8000
```

Replace it with:

```
# Validate political events (optional, any time after editing political_events.csv)
python src/build_events.py

# Dashboard
python src/export_dashboard.py
python -m http.server 8000 -d dashboard   # then open http://localhost:8000
```

- [ ] **Step 3: Document `build_events.py` in SETUP.md's "Adding or Editing Political Events" section**

In `SETUP.md`, find:

```
- `source_url` is required for the paper citation corpus
- After editing: re-run `correlate.py` → `export_dashboard.py`
```

Replace with:

```
- `source_url` is required for the paper citation corpus
- After editing: run `python src/build_events.py` to validate schema/required fields, then re-run `correlate.py` → `export_dashboard.py`
```

- [ ] **Step 4: Verify build_events.py still runs cleanly**

```bash
source .venv/bin/activate && python src/build_events.py
```

Expected: prints `Loaded 65 events` followed by validation output, exit code 0.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md SETUP.md
git commit -m "Remove unreferenced screenshot, document build_events.py in command lists"
```

---

## Task 2: Ship an editable songs.csv with the dashboard

**Files:**
- Modify: `src/export_dashboard.py`
- Create (generated, not committed as source but exercised by this task): `dashboard/songs.csv`, `dashboard/EDITING_INSTRUCTIONS.md`

**Interfaces:**
- Consumes: `PROCESSED_DIR`, `SONGS_CSV`, `DASHBOARD_DIR`, `BASE_DIR` constants already defined at the top of `src/export_dashboard.py`.
- Produces: `dashboard/songs.csv` (byte-identical copy of `data/processed/songs.csv`) and `dashboard/EDITING_INSTRUCTIONS.md`, refreshed on every `export_dashboard.py` run.

- [ ] **Step 1: Add the songs.csv bundling + instructions file to export_dashboard.py**

In `src/export_dashboard.py`, find:

```python
    # --- Inline data + sessions into index.html so it opens standalone (no server) ---
    inject_inline_data(payload, sessions)
```

Replace with:

```python
    # --- Bundle an editable copy of songs.csv + instructions for a collaborator ---
    bundle_editable_songs()

    # --- Inline data + sessions into index.html so it opens standalone (no server) ---
    inject_inline_data(payload, sessions)
```

Then, directly above the `inject_inline_data` function definition, add a new function:

```python
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
```

- [ ] **Step 2: Run export_dashboard.py and verify the new files**

```bash
source .venv/bin/activate && python src/export_dashboard.py
```

Expected output includes a new line: `Bundled /Users/.../dashboard/songs.csv and EDITING_INSTRUCTIONS.md for collaborator hand-off`

- [ ] **Step 3: Verify dashboard/songs.csv matches the canonical file exactly**

```bash
diff data/processed/songs.csv dashboard/songs.csv && echo "IDENTICAL"
```

Expected: `IDENTICAL` (no diff output before it).

- [ ] **Step 4: Verify EDITING_INSTRUCTIONS.md was written**

```bash
head -5 dashboard/EDITING_INSTRUCTIONS.md
```

Expected: starts with `# Editing songs.csv`.

- [ ] **Step 5: Commit**

```bash
git add src/export_dashboard.py dashboard/songs.csv dashboard/EDITING_INSTRUCTIONS.md dashboard/index.html dashboard/data.json
git commit -m "Bundle an editable songs.csv + instructions with the dashboard export"
```

Note: `dashboard/index.html` and `dashboard/data.json` will also show as modified since running the export regenerates their inlined-data timestamspan/content — commit them alongside since they're already tracked files kept in sync with the pipeline (established pattern from the prior session).

---

## Task 3: Validated re-ingest script (`src/ingest_songs.py`)

**Files:**
- Create: `src/ingest_songs.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `data/processed/songs.csv` schema — columns `song_id, artist, title, album, release_year, release_date, genius_url, retrieved_at, lyrics_raw_path, language, word_count, lyrics_clean`.
- Produces: a CLI (`python src/ingest_songs.py <incoming_csv> [--current PATH] [--force]`) with exit code `0` on success (writes `data/processed/songs.csv` and a `data/processed/songs.backup-<timestamp>.csv`) or `1` on refusal/error (writes nothing).
- Internal functions `load_csv_strict_utf8(path) -> pd.DataFrame`, `diff_songs(current, incoming) -> dict` (keys: `flags: list[str]`, `changes: dict[str,int]`, `missing_ids: set`, `added_ids: set`), and `run(incoming_path, current_path, force) -> int`, wired together by the `main()` CLI entrypoint — later steps in this task exercise the whole thing end-to-end via the CLI (`python src/ingest_songs.py ...`), matching this repo's existing convention of testing scripts by running them rather than via a unit-test framework.

- [ ] **Step 1: Write src/ingest_songs.py**

```python
"""
Validates and ingests an edited copy of songs.csv (e.g. returned by a
collaborator who filled in missing release_year/release_date values) back
into data/processed/songs.csv.

Usage:
    python src/ingest_songs.py path/to/returned_songs.csv
    python src/ingest_songs.py path/to/returned_songs.csv --force

Refuses to overwrite data/processed/songs.csv if it finds signs of
corruption or unexpected changes (see SETUP.md, "Sending Data to a
Collaborator for Review"), unless --force is passed. Always backs up the
current file before overwriting. Non-UTF-8 encoding and column-set
mismatches are hard stops that --force cannot bypass.
"""

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent.parent
CURRENT_SONGS_CSV = BASE_DIR / "data" / "processed" / "songs.csv"

YEAR_RE = re.compile(r"^\d{4}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_COLUMNS = {"release_year", "release_date"}
LENGTH_TOLERANCE = 0.20


def load_csv_strict_utf8(path: Path) -> pd.DataFrame:
    raw = path.read_bytes()
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"{path} is not valid UTF-8: {e}") from e
    return pd.read_csv(path, dtype=str, encoding="utf-8").fillna("")


def diff_songs(current: pd.DataFrame, incoming: pd.DataFrame) -> dict:
    flags = []
    changes = {"release_year": 0, "release_date": 0, "other": 0}
    other_examples = []

    current_ids = set(current["song_id"])
    incoming_ids = set(incoming["song_id"])
    missing_ids = current_ids - incoming_ids
    added_ids = incoming_ids - current_ids
    if missing_ids:
        flags.append(
            f"{len(missing_ids)} song_id(s) present in current data are missing "
            f"from the incoming file: {sorted(missing_ids)[:10]}"
        )
    if added_ids:
        flags.append(
            f"{len(added_ids)} song_id(s) in the incoming file are not in "
            f"current data: {sorted(added_ids)[:10]}"
        )

    current_by_id = current.set_index("song_id")
    incoming_by_id = incoming.set_index("song_id")
    shared_ids = current_ids & incoming_ids

    for song_id in shared_ids:
        cur_row = current_by_id.loc[song_id]
        inc_row = incoming_by_id.loc[song_id]

        cur_lyrics = cur_row.get("lyrics_clean", "")
        inc_lyrics = inc_row.get("lyrics_clean", "")
        if cur_lyrics:
            if not inc_lyrics.strip():
                flags.append(f"song_id {song_id}: lyrics_clean was non-empty and is now blank")
            else:
                length_diff = abs(len(inc_lyrics) - len(cur_lyrics)) / len(cur_lyrics)
                if length_diff > LENGTH_TOLERANCE:
                    flags.append(
                        f"song_id {song_id}: lyrics_clean length changed by "
                        f"{length_diff:.0%} (possible corruption)"
                    )

        for col in ("release_year", "release_date"):
            if cur_row.get(col, "") != inc_row.get(col, ""):
                changes[col] += 1

        year_val = inc_row.get("release_year", "")
        if year_val and not YEAR_RE.match(year_val):
            flags.append(f"song_id {song_id}: release_year '{year_val}' is not a 4-digit year")
        date_val = inc_row.get("release_date", "")
        if date_val and not DATE_RE.match(date_val):
            flags.append(f"song_id {song_id}: release_date '{date_val}' is not YYYY-MM-DD")

        other_cols = [c for c in current.columns if c not in DATE_COLUMNS and c != "song_id"]
        for col in other_cols:
            if cur_row.get(col, "") != inc_row.get(col, ""):
                changes["other"] += 1
                if len(other_examples) < 10:
                    other_examples.append(f"song_id {song_id}: column '{col}' changed unexpectedly")

    flags.extend(other_examples)
    return {"flags": flags, "changes": changes, "missing_ids": missing_ids, "added_ids": added_ids}


def run(incoming_path: Path, current_path: Path, force: bool) -> int:
    if not current_path.exists():
        print(f"Current songs file not found: {current_path}")
        return 1
    if not incoming_path.exists():
        print(f"Incoming file not found: {incoming_path}")
        return 1

    try:
        incoming = load_csv_strict_utf8(incoming_path)
    except ValueError as e:
        print(f"REFUSING to ingest: {e}")
        return 1

    current = load_csv_strict_utf8(current_path)

    if set(incoming.columns) != set(current.columns):
        missing_cols = set(current.columns) - set(incoming.columns)
        extra_cols = set(incoming.columns) - set(current.columns)
        print("REFUSING to ingest: column mismatch between current and incoming file")
        if missing_cols:
            print(f"  Missing columns: {sorted(missing_cols)}")
        if extra_cols:
            print(f"  Unexpected columns: {sorted(extra_cols)}")
        return 1

    result = diff_songs(current, incoming)

    print(f"Current songs: {len(current)}, incoming songs: {len(incoming)}")
    print(f"release_year changed: {result['changes']['release_year']}")
    print(f"release_date changed: {result['changes']['release_date']}")
    print(f"other unexpected column changes: {result['changes']['other']}")

    if result["flags"]:
        print(f"\n{len(result['flags'])} issue(s) found:")
        for flag in result["flags"]:
            print(f"  - {flag}")

        if not force:
            print("\nRefusing to overwrite data/processed/songs.csv. Review the issues above.")
            print("If they're expected, re-run with --force.")
            return 1
        print("\n--force passed: proceeding despite the issues above.")

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_path = current_path.parent / f"songs.backup-{timestamp}.csv"
    shutil.copy2(current_path, backup_path)
    print(f"\nBacked up current file to {backup_path}")

    incoming.to_csv(current_path, index=False)
    print(f"Wrote {len(incoming)} songs to {current_path}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("incoming", type=Path, help="Path to the returned/edited songs.csv")
    parser.add_argument(
        "--current", type=Path, default=CURRENT_SONGS_CSV,
        help="Path to the current canonical songs.csv (default: data/processed/songs.csv)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite even if issues are found")
    args = parser.parse_args()
    sys.exit(run(args.incoming, args.current, args.force))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Gitignore the backup files ingest_songs.py creates**

`ingest_songs.py` writes `data/processed/songs.backup-<timestamp>.csv` before every overwrite. These are local safety copies, not meant for version control (git history already tracks `data/processed/songs.csv` itself). In `.gitignore`, find:

```
# Generated files (re-created by export_dashboard.py)
dashboard/prompts/
```

Replace with:

```
# Generated files (re-created by export_dashboard.py)
dashboard/prompts/

# Local safety backups written by ingest_songs.py before each overwrite
data/processed/songs.backup-*.csv
```

- [ ] **Step 3: Build fixture CSVs for testing**

```bash
mkdir -p /tmp/ingest_test
cat > /tmp/ingest_test/current.csv <<'EOF'
song_id,artist,title,album,release_year,release_date,genius_url,retrieved_at,lyrics_raw_path,language,word_count,lyrics_clean
1,Los Tigres del Norte,Song One,,,,http://example.com/1,2026-01-01T00:00:00Z,data/raw/a/1.json,es,12,"Line one
Line two
Line three padding text to reach a reasonable length for the ratio check to be meaningful"
2,Los Tigres del Norte,Song Two,,,,http://example.com/2,2026-01-01T00:00:00Z,data/raw/a/2.json,es,10,"Another song with some lyrics here for testing purposes today"
EOF
cp /tmp/ingest_test/current.csv /tmp/ingest_test/clean_edit.csv
python3 - <<'EOF'
path = "/tmp/ingest_test/clean_edit.csv"
text = open(path, encoding="utf-8").read()
text = text.replace(
    "1,Los Tigres del Norte,Song One,,,,",
    "1,Los Tigres del Norte,Song One,,1998,1998-06-15,",
).replace(
    "2,Los Tigres del Norte,Song Two,,,,",
    "2,Los Tigres del Norte,Song Two,,2001,,",
)
open(path, "w", encoding="utf-8").write(text)
EOF
```

Expected: no output from the heredocs; `ls /tmp/ingest_test` shows `current.csv` and `clean_edit.csv`.

- [ ] **Step 4: Scenario (a) — clean edit succeeds without --force**

```bash
source .venv/bin/activate
python src/ingest_songs.py /tmp/ingest_test/clean_edit.csv --current /tmp/ingest_test/current.csv
echo "exit code: $?"
```

Expected: prints `release_year changed: 2`, `release_date changed: 1`, `other unexpected column changes: 0`, no issues section, ends with `Wrote 2 songs to /tmp/ingest_test/current.csv`, `exit code: 0`. Confirm a backup file was created:

```bash
ls /tmp/ingest_test/songs.backup-*.csv
```

Expected: one backup file listed.

- [ ] **Step 5: Scenario (b) — corrupted lyrics refused, then forced**

```bash
cp /tmp/ingest_test/clean_edit.csv /tmp/ingest_test/corrupted.csv
python3 - <<'EOF'
import csv
rows = list(csv.DictReader(open("/tmp/ingest_test/corrupted.csv", encoding="utf-8")))
rows[0]["lyrics_clean"] = ""
with open("/tmp/ingest_test/corrupted.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(rows)
EOF
cp /tmp/ingest_test/current.csv /tmp/ingest_test/current2.csv
python src/ingest_songs.py /tmp/ingest_test/corrupted.csv --current /tmp/ingest_test/current2.csv
echo "exit code without --force: $?"
python src/ingest_songs.py /tmp/ingest_test/corrupted.csv --current /tmp/ingest_test/current2.csv --force
echo "exit code with --force: $?"
```

Expected: first run prints `song_id 1: lyrics_clean was non-empty and is now blank`, ends with "Refusing to overwrite", `exit code without --force: 1`. Second run prints the same flag, then `--force passed: proceeding despite the issues above.`, ends with `Wrote 2 songs...`, `exit code with --force: 0`.

- [ ] **Step 6: Scenario (c) — missing song_id refused**

```bash
head -1 /tmp/ingest_test/clean_edit.csv > /tmp/ingest_test/missing_row.csv
sed -n '2p' /tmp/ingest_test/clean_edit.csv >> /tmp/ingest_test/missing_row.csv
cp /tmp/ingest_test/current.csv /tmp/ingest_test/current3.csv
python src/ingest_songs.py /tmp/ingest_test/missing_row.csv --current /tmp/ingest_test/current3.csv
echo "exit code: $?"
```

Expected: prints `1 song_id(s) present in current data are missing from the incoming file: ['2']`, ends with "Refusing to overwrite", `exit code: 1`.

- [ ] **Step 7: Scenario (d) — bad encoding is a hard stop even with --force**

```bash
python3 - <<'EOF'
text = open("/tmp/ingest_test/clean_edit.csv", encoding="utf-8").read()
text = text.replace("Song One", "Canción Uno")
with open("/tmp/ingest_test/bad_encoding.csv", "wb") as f:
    f.write(text.encode("latin-1"))
EOF
cp /tmp/ingest_test/current.csv /tmp/ingest_test/current4.csv
python src/ingest_songs.py /tmp/ingest_test/bad_encoding.csv --current /tmp/ingest_test/current4.csv --force
echo "exit code: $?"
```

Expected: prints a line starting with `REFUSING to ingest:` mentioning "not valid UTF-8", `exit code: 1` (even though `--force` was passed — this is the hard-stop path).

- [ ] **Step 8: Clean up test fixtures**

```bash
rm -rf /tmp/ingest_test
```

- [ ] **Step 9: Commit**

```bash
git add src/ingest_songs.py .gitignore
git commit -m "Add ingest_songs.py to validate and safely re-ingest collaborator edits"
```

---

## Task 4: Document the round-trip workflow

**Files:**
- Modify: `SETUP.md`
- Modify: `CLAUDE.md`

**Interfaces:** None — documentation only, describing the behavior built in Tasks 2 and 3.

- [ ] **Step 1: Add a new section to SETUP.md**

In `SETUP.md`, find this section header and the section that follows it:

```
## Editing Lexicons
```

Insert a new section immediately **before** it:

```markdown
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
```

- [ ] **Step 2: Update SETUP.md's File Structure diagram**

Find:

```
├── dashboard/
│   ├── index.html         ← Interactive dashboard (serves from data.json)
│   ├── app.js
│   ├── data.json          ← Generated — do not edit manually
│   └── prompts/           ← Session log JSON files
```

Replace with:

```
├── dashboard/
│   ├── index.html         ← Interactive dashboard (data is inlined — open directly, no server needed)
│   ├── app.js
│   ├── data.json          ← Generated — do not edit manually
│   ├── songs.csv          ← Generated copy of data/processed/songs.csv — safe for a collaborator to edit
│   ├── EDITING_INSTRUCTIONS.md ← Generated — instructions for a non-technical collaborator
│   └── prompts/           ← Session log JSON files
```

And find:

```
└── src/
    ├── scrape_genius.py
    ├── clean_lyrics.py
    ├── build_events.py
    ├── analyze_keywords.py
    ├── analyze_bertopic.py
    ├── analyze_hybrid.py
    ├── correlate.py
    └── export_dashboard.py
```

Replace with:

```
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

- [ ] **Step 3: Update CLAUDE.md's Key Data Files table**

Find:

```
| `dashboard/data.json` | Generated payload — do NOT edit manually |
```

Replace with:

```
| `dashboard/data.json` | Generated payload — do NOT edit manually |
| `dashboard/songs.csv` | Generated copy of `songs.csv`, bundled for a collaborator to edit and return — see SETUP.md |
```

- [ ] **Step 4: Add ingest_songs.py to CLAUDE.md's Commands section**

Find (the block Task 1 already updated):

```
# Validate political events (optional, any time after editing political_events.csv)
python src/build_events.py

# Dashboard
python src/export_dashboard.py
python -m http.server 8000 -d dashboard   # then open http://localhost:8000
```

Replace with:

```
# Validate political events (optional, any time after editing political_events.csv)
python src/build_events.py

# Dashboard
python src/export_dashboard.py
# dashboard/index.html now works standalone — open it directly, no server needed

# Re-ingest a collaborator's edited songs.csv (see SETUP.md for the full round trip)
python src/ingest_songs.py path/to/returned_songs.csv
```

- [ ] **Step 5: Verify the docs render sensibly**

```bash
grep -c "ingest_songs.py" SETUP.md CLAUDE.md
```

Expected: both files report a count of at least 2.

- [ ] **Step 6: Commit**

```bash
git add SETUP.md CLAUDE.md
git commit -m "Document the collaborator data round-trip workflow"
```
