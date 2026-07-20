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
