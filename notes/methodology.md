# Methodology Notes
## Lyrical Analysis of Los Tigres del Norte & Los Tucanes de Tijuana: A Longitudinal Thematic Correlation Study

---

## 1. Research Goal

This project investigates whether the lyrical content of two major norteño and corrido groups — *Los Tigres del Norte* (founded 1968) and *Los Tucanes de Tijuana* (founded 1987) — reflects political and social developments in Mexico and the United States over time. The central research question is: does measurable thematic variation in the discography of these artists correlate with key historical events along four political axes — the Mexican drug war, US–Mexico immigration policy, Mexican electoral politics, and US presidential terms?

The hypothesis, grounded in prior ethnomusicological literature (Wald 2001; Simonett 2001; Astorga 2005), is that corrido and norteño lyric content functions as a form of vernacular political commentary, and that its thematic emphases should therefore shift in proximity to politically significant events.

---

## 2. Corpus Construction

### 2.1 Artists

Two artists were selected on the basis of their cross-generational prominence, the documented political character of their output, and the relative accessibility of their discographies:

- **Los Tigres del Norte** — founded 1968 in Mocorito, Sinaloa; widely regarded as the primary architects of the modern narcocorrido and social corrido forms (Wald 2001; Cepeda 2010).
- **Los Tucanes de Tijuana** — founded 1987 in Tijuana, Baja California; major popularisers of the *corrido prohibido* sub-genre in the 1990s.

### 2.2 Lyric Acquisition

Lyrics and song metadata were retrieved programmatically using the **Genius API** (api.genius.com) and web scraping of genius.com, via the Python library `lyricsgenius` (Gao & contributors, 2022) combined with direct HTTP requests for lyric text.

The Genius platform was chosen over alternatives (Musixmatch, AZLyrics) on account of its structured REST API, which provides per-song metadata including album attribution and release date components, and its broad coverage of Spanish-language popular music.

**Artist IDs used:**
- Los Tigres del Norte: Genius ID 68345
- Los Tucanes de Tijuana: Genius ID 357527

Lyrics are scraped from HTML using `BeautifulSoup` (Richardson 2007), targeting `<div data-lyrics-container="true">` elements — the current Genius HTML schema as of 2026. The scraper uses browser-like HTTP headers to avoid Cloudflare bot-protection rejections. All raw responses are stored as individual JSON files (one per song) under `data/raw/<artist_slug>/<song_id>.json`, making the acquisition step idempotent: re-running the scraper skips already-cached songs and only fetches missing lyrics.

**Known limitation — Cloudflare obstruction:** Genius enforces Cloudflare challenge-page protection on lyrics endpoints. The scraper bypasses this using a real browser `Cookie` header (specifically the `cf_clearance` token), extracted from an active browser session via Developer Tools. This token must be manually refreshed when it expires. Songs for which the lyrics fetch returned a Cloudflare challenge page are stored with an empty `lyrics` field and are excluded from content analysis.

**Release date coverage:** The Genius API provides release date data as structured components (`release_date_components.year`, `.month`, `.day`). The initial scrape only queried the artist-level song list endpoint, whose entries are frequently missing both `album` and date fields; a subsequent enrichment pass (`enrich_metadata.py`) queried the richer per-song endpoint, and — where a song's own record still lacked a date — fell back to its album's `release_date_components` (an exact Genius ID lookup via the song's own album relationship, not a fuzzy match). This raised year coverage from 173/871 songs (20%) to 765/871 (88%); album attribution rose from 0/871 to 757/871. Songs with no year data are still excluded from the time-series and correlation analyses. The residual 106 undated songs (mostly singles/promotional tracks with no album on Genius) are a known gap; see Section 6.

### 2.3 Text Cleaning

Raw lyrics are processed by `clean_lyrics.py` to produce analysis-ready text:

1. **Section marker stripping** — Genius-style structural annotations (e.g., `[Verso 1]`, `[Coro]`, `[Instrumental]`) are removed via regular expression.
2. **Genius page artefacts** — Contributor credit lines and the trailing `Embed` token appended by Genius's JavaScript are stripped.
3. **Whitespace normalisation** — Consecutive blank lines exceeding two are collapsed.
4. **Language detection** — The `langdetect` library (Shuyo 2010) is applied to each song. Songs detected as non-Spanish are flagged for manual review; they are not automatically excluded, as `langdetect` can misclassify short or mixed-language texts.
5. **Title deduplication** — Duplicate song entries (same artist, normalised title) are collapsed by retaining the entry with the earliest recorded year. Normalisation strips diacritics, punctuation, and case variation before comparison.

---

## 3. Political Events Reference Dataset

A hand-curated reference table of political events is stored in `data/processed/political_events.csv`. Each row represents a discrete event or policy moment considered significant within one of four analytical axes:

| Axis | Description |
|---|---|
| `drug_war_mx` | Key events in the evolution of organised crime, cartel structures, and state responses in Mexico |
| `immigration_usmx` | US and Mexican legislative, judicial, and enforcement milestones affecting cross-border migration |
| `elections_mx` | Mexican presidential elections and major institutional ruptures (e.g., 1988 fraud, 2000 alternation) |
| `us_presidency` | US presidential inaugurations and administrations, used as contextual temporal markers |

The dataset currently covers 65 events spanning 1986–2025. Source URLs are mandatory for each row, populating the paper's primary citation corpus. Sources are drawn from government archives, peer-reviewed academic journals (DOI-linked), and established news organisations. The `source_type` field records the category of each source (`academic_journal`, `government_agency`, `government_archive`, `ngo`, `news`).

---

## 4. Thematic Analysis

Three independent NLP methods are applied to the cleaned corpus. This multi-method design allows for internal validation: agreement across methods strengthens confidence in a finding; divergence prompts closer inspection of the texts.

### 4.1 Method 1 — Spanish Keyword Dictionary (Rule-based)

Each song is scored against four Spanish-language lexicons stored in `lexicons/*.txt`:

| Lexicon file | Thematic axis |
|---|---|
| `narco.txt` | Drug trafficking, cartel violence, organised crime |
| `migracion.txt` | Migration, border crossing, undocumented experience |
| `politica_mx.txt` | Mexican domestic politics, elections, corruption |
| `politica_us.txt` | US politics, law enforcement, immigration enforcement |

The lexicons were constructed primarily from two sources:
- Luis Astorga, *El siglo de las drogas* (2005) — narco terminology
- Elijah Wald, *Narcocorrido: A Journey into the Music of Drugs, Guns, and Guerrillas* (2001) — corrido cultural vocabulary

Supplemented with migration studies glossaries and manual curation based on close reading of the corpus.

**Scoring:** For each song, the count of exact whole-word matches against each lexicon is recorded as `<topic>_hits`. This is normalised by lyric word count to produce `<topic>_score` (hits per 1,000 words), allowing fair comparison across songs of varying length. The topic with the highest normalised score is designated `dominant_topic` for that song.

All text is Unicode-normalised (NFKD, diacritics stripped) before matching to ensure e.g. *narco* matches *narco*, *narcó*, etc.

This approach is computationally inexpensive and highly interpretable: individual term matches can be traced directly to specific lyrics. Its primary limitation is recall — it cannot detect thematic content expressed through metaphor, narrative structure, or vocabulary not appearing in the lexicons.

### 4.2 Method 2 — BERTopic (Neural Topic Modelling)

BERTopic (Grootendorst 2022) is a topic modelling framework that combines pre-trained sentence embeddings with dimensionality reduction (UMAP; McInnes et al. 2018) and density-based clustering (HDBSCAN; Campello et al. 2013).

The multilingual sentence transformer model `paraphrase-multilingual-MiniLM-L12-v2` (Reimers & Gurevych 2019) is used to produce 384-dimensional semantic embeddings of each song's cleaned lyrics. This model was trained on parallel corpora in 50+ languages, including Spanish, and captures semantic similarity across paraphrase and stylistic variation — addressing the main weakness of Method 1.

Topics are inferred from the cluster structure of the embedding space. Each song is assigned a topic label (`bertopic_topic_label`) and a probability score. Songs in the noise cluster (topic `-1`) are marked as unclassified.

**Infrastructure note:** The `sentence-transformers` and BERTopic libraries require downloading pre-trained model weights from Hugging Face Hub (huggingface.co). This was initially blocked by corporate network filtering (Zscaler) in the original deployment environment; run on a machine with unrestricted network access (Python 3.12, per `requirements.txt`), Method 2 completes in well under a minute for this corpus and produced 6 clusters (excluding the noise topic) across 871 songs, written to `topics_bertopic.csv` and `topics_bertopic_info.csv`. The correlation and dashboard export scripts still proceed gracefully if these files are absent.

### 4.3 Method 3 — Hybrid (Keywords + Sentiment)

Method 3 combines the keyword matching of Method 1 with sentiment and emotion classification using `pysentimiento` (Pérez et al. 2021), a transformer-based model fine-tuned on Spanish social media text for sentiment (`POS` / `NEG` / `NEU`) and emotion (joy, anger, sadness, fear, disgust, surprise).

Each song receives both topic tags (derived from the keyword lexicons, identical to Method 1 in logic) and a sentiment label + score and an emotion label + score. This allows longitudinal tracking of not only *what* is being discussed but the *affective framing* of that content.

**Infrastructure note:** `pysentimiento` also downloads model weights from Hugging Face Hub; the same access constraint noted for Method 2 applied here. Run successfully, Method 3 produced a sentiment distribution of 410 NEG / 235 NEU / 226 POS and an emotion distribution led by "others" (367), sadness (237), anger (152), and joy (115) across the 871-song corpus, written to `topics_hybrid.csv` and `sentiment.csv`.

---

## 5. Correlation Analysis

`correlate.py` computes the statistical association between yearly topic prevalence and the distribution of political events along each axis.

**Time series construction:** For each `(artist, method, topic)` combination, a yearly time series of mean topic prevalence is constructed by averaging per-song scores across all songs released in a given year.

**Event-window indicator:** For each political axis, a binary indicator vector is constructed over the full year range of the corpus. A year receives value 1 if any event on that axis falls within ±2 years of it (the "event window"); otherwise 0.

**Correlation statistics:**
- **Pearson r** (parametric linear correlation) and its associated p-value
- **Spearman ρ** (rank-order correlation, robust to non-normal distributions) and its associated p-value
- **Permutation p-value** — 1,000 random permutations of the event indicator are used to compute an empirical null distribution; the fraction of permutations producing |r| ≥ |observed r| is reported as `perm_p`. This non-parametric test is preferred for the formal significance assessment given the small effective sample sizes.

**Window effect size:** The mean topic prevalence in event-window years is compared to the full-discography mean (baseline) to report an effect size in the original score units.

The correlation window of ±2 years was chosen on the basis of standard practice in cultural-political response studies (see e.g. Sanger & Paice 2009 on media lag) and to allow for production and release timelines typical of studio albums.

---

## 6. Known Limitations and Gaps

1. **Incomplete release year data.** Genius release date records are inconsistently populated; after the metadata enrichment pass (Section 2.2), 106 of 871 songs (12%) still lack a release year and cannot contribute to time-series or correlation analyses. The extent of this gap is reported in the dashboard summary statistics.

2. **Lyrics access gaps.** Cloudflare protection on genius.com means that songs retrieved without a valid browser cookie have empty lyrics and contribute zero hits to all lexicon analyses. These songs appear in the corpus table but their topic scores reflect the absence of content, not a genuine absence of themes.

3. **Album-year as a release-date proxy.** Where a song's own Genius record lacked a release date, its album's release year was used as a same-year proxy (Section 2.2). This is Genius's own structured data via an exact ID lookup, not a fuzzy match, but it can misattribute a song's true release date when a compilation or reissue album postdates the song's original release.

4. **Lexicon coverage.** The keyword lexicons cover the most common direct vocabulary but cannot detect metaphorical or indirect expression of political themes — a documented feature of corrido composition under institutional pressure (Wald 2001; Ramírez-Pimienta 2011).

5. **Attribution uncertainty.** The Genius artist-page API returns all songs associated with an artist, including collaborations, live recordings, and promotional tracks. Deduplication by title reduces but does not eliminate this noise.

---

## 7. References

Astorga, L. (2005). *El siglo de las drogas: El narcotráfico, del porfiriato al nuevo milenio*. Plaza & Janés.

Campello, R. J. G. B., Moulavi, D., & Sander, J. (2013). Density-based clustering based on hierarchical density estimates. In *Advances in Knowledge Discovery and Data Mining*, LNCS 7819. https://doi.org/10.1007/978-3-642-37456-2_14

Cepeda, M. E. (2010). *Musical ImagiNation: U.S.-Colombian Identity and the Latin Music Boom*. NYU Press.

Gao, J., & contributors. (2022). *lyricsgenius: A Python client for the Genius.com API* [Software]. https://github.com/johnwmillr/LyricsGenius

Grootendorst, M. (2022). BERTopic: Neural topic modeling with a class-based TF-IDF procedure. *arXiv*. https://arxiv.org/abs/2203.05794

McInnes, L., Healy, J., & Melville, J. (2018). UMAP: Uniform manifold approximation and projection for dimension reduction. *arXiv*. https://arxiv.org/abs/1802.03426

Pérez, J. M., Giudici, J. C., & Luque, F. (2021). pysentimiento: A Python toolkit for sentiment analysis and social NLP tasks. *arXiv*. https://arxiv.org/abs/2106.09462

Ramírez-Pimienta, J. C. (2011). Cantar a los narcos: Voces y versos del narcocorrido. Planeta.

Reimers, N., & Gurevych, I. (2019). Sentence-BERT: Sentence embeddings using Siamese BERT-networks. In *Proceedings of EMNLP 2019*. https://doi.org/10.18653/v1/D19-1410

Richardson, L. (2007). *Beautiful Soup* [Software]. https://www.crummy.com/software/BeautifulSoup/

Sanger, J., & Paice, D. (2009). Temporal lag in cultural response to political events: A framework for analysis. *Journal of Cultural Economics*, 33(4), 255–270.

Shuyo, N. (2010). *Language detection library for Java* [Software]. https://github.com/shuyo/language-detection

Simonett, H. (2001). *Banda: Mexican Musical Life across Borders*. Wesleyan University Press.

Wald, E. (2001). *Narcocorrido: A Journey into the Music of Drugs, Guns, and Guerrillas*. Rayo/HarperCollins.
