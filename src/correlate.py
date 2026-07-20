"""
Computes time-windowed correlations between lyric topic prevalence and political events.

For each (topic, method, artist) combination:
  - Builds a yearly time series of topic prevalence
  - For each political event, computes mean prevalence in [event_year-2, event_year+2]
    vs. the artist's baseline (full-discography mean)
  - Reports Pearson and Spearman correlations between topic prevalence series
    and event-axis indicator series, with permutation p-values

Writes data/analysis/correlations.csv.

Usage:
    python src/correlate.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

BASE_DIR = Path(__file__).parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
ANALYSIS_DIR = BASE_DIR / "data" / "analysis"

SONGS_CSV = PROCESSED_DIR / "songs.csv"
EVENTS_CSV = PROCESSED_DIR / "political_events.csv"
KEYWORDS_CSV = ANALYSIS_DIR / "topics_keywords.csv"
BERTOPIC_CSV = ANALYSIS_DIR / "topics_bertopic.csv"
HYBRID_CSV = ANALYSIS_DIR / "topics_hybrid.csv"

OUTPUT_CSV = ANALYSIS_DIR / "correlations.csv"
TIMESERIES_JSON = ANALYSIS_DIR / "timeseries.json"

EVENT_WINDOW_YEARS = 2
N_PERMUTATIONS = 1000


def load_method_data() -> dict[str, pd.DataFrame]:
    methods = {}

    if KEYWORDS_CSV.exists():
        df = pd.read_csv(KEYWORDS_CSV, dtype=str).fillna("0")
        methods["keywords"] = df
    else:
        print(f"Missing: {KEYWORDS_CSV}")

    if BERTOPIC_CSV.exists():
        df = pd.read_csv(BERTOPIC_CSV, dtype=str).fillna("")
        methods["bertopic"] = df
    else:
        print(f"Missing: {BERTOPIC_CSV}")

    if HYBRID_CSV.exists():
        df = pd.read_csv(HYBRID_CSV, dtype=str).fillna("")
        methods["hybrid"] = df
    else:
        print(f"Missing: {HYBRID_CSV}")

    return methods


def get_keyword_topics(df: pd.DataFrame) -> list[str]:
    return [c.replace("_score", "") for c in df.columns if c.endswith("_score")]


def yearly_topic_series(df: pd.DataFrame, topic: str, method: str, artist: str | None = None) -> pd.Series:
    working = df.copy()
    if artist:
        col = "artist" if "artist" in working.columns else "artist_x"
        working = working[working[col].str.lower() == artist.lower()]

    working["release_year"] = pd.to_numeric(working["release_year"], errors="coerce")
    working = working.dropna(subset=["release_year"])
    working["release_year"] = working["release_year"].astype(int)

    if method == "keywords":
        score_col = f"{topic}_score"
        if score_col not in working.columns:
            return pd.Series(dtype=float)
        working[score_col] = pd.to_numeric(working[score_col], errors="coerce").fillna(0)
        series = working.groupby("release_year")[score_col].mean()

    elif method == "bertopic":
        working["has_topic"] = (working["bertopic_topic_label"].str.contains(topic, case=False, na=False)).astype(float)
        series = working.groupby("release_year")["has_topic"].mean()

    elif method == "hybrid":
        working["has_topic"] = working["topic_tags"].str.contains(topic, case=False, na=False).astype(float)
        series = working.groupby("release_year")["has_topic"].mean()

    else:
        return pd.Series(dtype=float)

    return series


def permutation_pvalue(x: np.ndarray, y: np.ndarray, observed_r: float, n_perms: int = 1000) -> float:
    count = 0
    for _ in range(n_perms):
        y_shuffled = np.random.permutation(y)
        r, _ = stats.pearsonr(x, y_shuffled)
        if abs(r) >= abs(observed_r):
            count += 1
    return count / n_perms


def run():
    for required in [SONGS_CSV, EVENTS_CSV]:
        if not required.exists():
            print(f"Required file not found: {required}")
            return

    events = pd.read_csv(EVENTS_CSV, dtype=str).fillna("")
    events["year"] = pd.to_datetime(events["date"], errors="coerce").dt.year
    events = events.dropna(subset=["year"])
    events["year"] = events["year"].astype(int)

    songs = pd.read_csv(SONGS_CSV, dtype=str).fillna("")
    songs["release_year"] = pd.to_numeric(songs["release_year"], errors="coerce")
    songs = songs.dropna(subset=["release_year"])
    songs["release_year"] = songs["release_year"].astype(int)

    year_min = int(songs["release_year"].min())
    year_max = int(songs["release_year"].max())
    all_years = np.arange(year_min, year_max + 1)

    artists = sorted(songs["artist"].dropna().unique().tolist()) + ["all"]
    axes = sorted(events["axis"].dropna().unique().tolist())

    method_data = load_method_data()
    if not method_data:
        print("No analysis files found. Run analyze_*.py scripts first.")
        return

    correlation_rows = []
    timeseries_export = {}

    for method_name, method_df in method_data.items():
        print(f"\n--- Method: {method_name} ---")

        if method_name == "keywords":
            topics = get_keyword_topics(method_df)
        elif method_name == "bertopic":
            topics = method_df["bertopic_topic_label"].dropna().unique().tolist()
            topics = [t for t in topics if t not in ("-1", "insufficient_lyrics")][:20]
        elif method_name == "hybrid":
            all_tags = method_df["topic_tags"].str.split("|").explode().dropna().unique()
            topics = [t for t in all_tags if t != "none"]
        else:
            topics = []

        for artist in artists:
            artist_label = artist if artist != "all" else "all_artists"

            for topic in topics:
                ts = yearly_topic_series(
                    method_df, topic, method_name,
                    artist=None if artist == "all" else artist
                )
                if ts.empty or ts.sum() == 0:
                    continue

                ts_full = ts.reindex(all_years, fill_value=0.0)

                ts_key = f"{method_name}|{artist_label}|{topic}"
                timeseries_export[ts_key] = {
                    "years": all_years.tolist(),
                    "values": ts_full.values.tolist(),
                }

                for axis in axes:
                    axis_events = events[events["axis"] == axis]
                    event_years = axis_events["year"].values

                    # Binary indicator: 1 in event-window years, 0 otherwise
                    indicator = np.zeros(len(all_years))
                    for ey in event_years:
                        for yi, yr in enumerate(all_years):
                            if abs(yr - ey) <= EVENT_WINDOW_YEARS:
                                indicator[yi] = 1.0

                    if indicator.sum() == 0 or indicator.sum() == len(indicator):
                        continue

                    ts_vals = ts_full.values.astype(float)

                    if np.std(ts_vals) == 0:
                        continue

                    pearson_r, pearson_p = stats.pearsonr(ts_vals, indicator)
                    spearman_r, spearman_p = stats.spearmanr(ts_vals, indicator)

                    perm_p = permutation_pvalue(ts_vals, indicator, pearson_r, N_PERMUTATIONS)

                    # Window effect: mean in-window vs baseline
                    baseline = ts_full.mean()
                    in_window_mean = ts_full[indicator == 1].mean() if (indicator == 1).any() else 0.0
                    window_effect = round(float(in_window_mean - baseline), 6)

                    correlation_rows.append({
                        "method": method_name,
                        "artist": artist_label,
                        "topic": topic,
                        "event_axis": axis,
                        "pearson_r": round(float(pearson_r), 4),
                        "pearson_p": round(float(pearson_p), 4),
                        "spearman_r": round(float(spearman_r), 4),
                        "spearman_p": round(float(spearman_p), 4),
                        "perm_p": round(float(perm_p), 4),
                        "window_effect": window_effect,
                        "n_years": len(all_years),
                        "event_window_years": EVENT_WINDOW_YEARS,
                    })

    if not correlation_rows:
        print("No correlations computed. Check that analysis CSVs are populated.")
        return

    result = pd.DataFrame(correlation_rows)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_CSV, index=False)
    print(f"\nWrote {len(result)} correlation rows to {OUTPUT_CSV}")

    TIMESERIES_JSON.write_text(json.dumps(timeseries_export, indent=2))
    print(f"Wrote time series data to {TIMESERIES_JSON}")

    # Top significant findings
    sig = result[result["perm_p"] < 0.05].sort_values("pearson_r", key=abs, ascending=False)
    if not sig.empty:
        print(f"\nTop 10 significant correlations (perm_p < 0.05):")
        print(sig.head(10)[["method", "artist", "topic", "event_axis", "pearson_r", "perm_p"]].to_string(index=False))
    else:
        print("\nNo correlations reached p < 0.05 — may need more data or wider windows.")


if __name__ == "__main__":
    run()
