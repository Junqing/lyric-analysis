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
NOTES_DIR = BASE_DIR / "notes"
LEXICONS_DIR = BASE_DIR / "lexicons"

SONGS_CSV = PROCESSED_DIR / "songs.csv"
EVENTS_CSV = PROCESSED_DIR / "political_events.csv"
KEYWORDS_CSV = ANALYSIS_DIR / "topics_keywords.csv"
BERTOPIC_CSV = ANALYSIS_DIR / "topics_bertopic.csv"
HYBRID_CSV = ANALYSIS_DIR / "topics_hybrid.csv"
CORRELATIONS_CSV = ANALYSIS_DIR / "correlations.csv"
TIMESERIES_JSON = ANALYSIS_DIR / "timeseries.json"
METHODOLOGY_MD = NOTES_DIR / "methodology.md"


# --- Minimal markdown → HTML renderer (headings, hr, bold/italic, inline code,
#     links, bare-URL autolink, ordered/unordered lists, GFM pipe tables,
#     paragraphs) — just enough to render notes/methodology.md without a
#     third-party dependency, so the dashboard stays a standalone HTML file. ---

def _inline_md(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    stash = []

    def stash_it(html: str) -> str:
        token = f"\x00{len(stash)}\x00"
        stash.append(html)
        return token

    text = re.sub(r"`([^`]+)`", lambda m: stash_it(f"<code>{m.group(1)}</code>"), text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: stash_it(
            f'<a href="{m.group(2).replace("&", "&amp;")}" target="_blank" rel="noopener">{m.group(1)}</a>'
        ),
        text,
    )
    text = re.sub(
        r'(https?://[^\s<>"\']+)',
        lambda m: stash_it(
            f'<a href="{m.group(1).replace("&", "&amp;")}" target="_blank" rel="noopener">{m.group(1)}</a>'
        ),
        text,
    )
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    for idx, html in enumerate(stash):
        text = text.replace(f"\x00{idx}\x00", html)
    return text


def render_markdown(md_text: str) -> str:
    lines = md_text.split("\n")
    out = []
    para_buf: list[str] = []
    i, n = 0, len(lines)

    def flush_para():
        if para_buf:
            text = " ".join(l.strip() for l in para_buf if l.strip())
            if text:
                out.append(f"<p>{_inline_md(text)}</p>")
            para_buf.clear()

    table_sep_re = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?$")
    heading_re = re.compile(r"^(#{1,6})\s+(.*)$")
    ordered_re = re.compile(r"^\d+\.\s+")
    unordered_re = re.compile(r"^[-*]\s+")

    while i < n:
        stripped = lines[i].strip()

        if stripped == "":
            flush_para()
            i += 1
            continue

        m = heading_re.match(stripped)
        if m:
            flush_para()
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline_md(m.group(2))}</h{level}>")
            i += 1
            continue

        if re.match(r"^-{3,}$", stripped):
            flush_para()
            out.append("<hr>")
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < n and table_sep_re.match(lines[i + 1].strip()):
            flush_para()
            header_cells = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            thead = "".join(f"<th>{_inline_md(c)}</th>" for c in header_cells)
            tbody = "".join(
                "<tr>" + "".join(f"<td>{_inline_md(c)}</td>" for c in row) + "</tr>"
                for row in rows
            )
            out.append(f"<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>")
            continue

        if ordered_re.match(stripped):
            flush_para()
            items = []
            while i < n and ordered_re.match(lines[i].strip()):
                items.append(ordered_re.sub("", lines[i].strip()))
                i += 1
            out.append("<ol>" + "".join(f"<li>{_inline_md(it)}</li>" for it in items) + "</ol>")
            continue

        if unordered_re.match(stripped):
            flush_para()
            items = []
            while i < n and unordered_re.match(lines[i].strip()):
                items.append(unordered_re.sub("", lines[i].strip()))
                i += 1
            out.append("<ul>" + "".join(f"<li>{_inline_md(it)}</li>" for it in items) + "</ul>")
            continue

        para_buf.append(lines[i])
        i += 1

    flush_para()
    return "\n".join(out)


def parse_lexicons() -> list[dict]:
    """Parse lexicons/*.txt into {name, description, sections:[{header, terms[]}]}.

    File convention: leading '#' comment lines (until the first blank line) are
    the file header/citation; each subsequent '# Section Name' comment starts a
    new section whose terms are the following non-comment lines, until the next
    blank line + comment or EOF.
    """
    lexicons = []
    if not LEXICONS_DIR.exists():
        return lexicons

    for path in sorted(LEXICONS_DIR.glob("*.txt")):
        lines = path.read_text(encoding="utf-8").split("\n")
        header_lines = []
        i = 0
        while i < len(lines) and lines[i].strip().startswith("#"):
            header_lines.append(lines[i].strip().lstrip("#").strip())
            i += 1
        description = " ".join(header_lines)

        sections = []
        current = None
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped == "":
                i += 1
                continue
            if stripped.startswith("#"):
                current = {"header": stripped.lstrip("#").strip(), "terms": []}
                sections.append(current)
            elif current is not None:
                current["terms"].append(stripped)
            i += 1

        lexicons.append({
            "name": path.stem,
            "description": description,
            "sections": sections,
            "term_count": sum(len(s["terms"]) for s in sections),
        })
    return lexicons


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

    # --- Methodology (rendered from notes/methodology.md) ---
    if METHODOLOGY_MD.exists():
        payload["methodology_html"] = render_markdown(METHODOLOGY_MD.read_text(encoding="utf-8"))
        print(f"Methodology: rendered {METHODOLOGY_MD.name}")
    else:
        print(f"Warning: {METHODOLOGY_MD} not found — skipping methodology tab")

    # --- Lexicons ---
    lexicons = parse_lexicons()
    if lexicons:
        payload["lexicons"] = lexicons
        print(f"Lexicons: {len(lexicons)} file(s), {sum(l['term_count'] for l in lexicons)} terms")

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
