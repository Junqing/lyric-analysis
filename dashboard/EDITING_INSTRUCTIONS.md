# Editing this dataset

This folder contains an interactive dashboard (`index.html`) and three
editable files: `songs.csv`, `political_events.csv`, and the `lexicons/`
folder. Edit whichever ones apply to what you were asked to review — you
don't need to touch all three.

## Viewing the data

Open `index.html` in any browser — no internet connection or installation
needed. It shows everything: the Analysis charts, Lyrics Browser, Political
Events (table + timeline), Methodology, and the Lexicon term lists.

## 1. Editing songs.csv (release years / albums)

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
5. Send `songs.csv` back.

## 2. Editing political_events.csv (add or correct events)

This is the reference timeline of political events the analysis is compared
against — shown in the Political Events tab.

1. Open `political_events.csv` in a spreadsheet.
2. To fix an existing event: edit any field in its row, but leave `event_id`
   as-is.
3. To add a new event: add a new row with a new unique `event_id` (use the
   next number after the highest existing one, e.g. if the last is `E065`,
   use `E066`), and fill in every column — `date` (`YYYY-MM-DD`), `axis`
   (must be one of `drug_war_mx`, `immigration_usmx`, `elections_mx`,
   `us_presidency`), `title`, `description`, and `source_url` (required —
   this is the paper's citation corpus, so every event needs a real source).
4. Don't delete rows unless you're sure an event should be removed — deleted
   `event_id`s are flagged on re-import.
5. Send `political_events.csv` back.

## 3. Editing lexicons/ (add or remove Spanish terms)

Each `.txt` file in `lexicons/` is a list of Spanish terms Method 1 searches
for in the lyrics, grouped into sections.

1. Open any `.txt` file in a plain text editor (not Word — it must stay
   plain text).
2. Add or remove terms freely — one term per line.
3. Do NOT rename the files, add/remove/rename the `# Section Header` comment
   lines, or change the file-level `#` comments at the top. Those are
   structural and changing them will break the re-import.
4. Send the whole `lexicons/` folder back.

## Saving CSV files

- **Excel:** File → Save As → File Format: "CSV UTF-8 (Comma delimited)".
  Do NOT use the plain "CSV" option — it can save with the wrong character
  encoding and break the Spanish accents.
- **Google Sheets:** File → Download → Comma-separated values (.csv) — this
  is UTF-8 by default, no extra steps needed.
- **Numbers:** File → Export To → CSV → Text Encoding: Unicode (UTF-8).
