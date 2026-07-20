/* Lyric Analysis Dashboard — app.js */

// ── Plotly lazy loader ────────────────────────────────────────────────────────
// Plotly is NOT loaded in <head> — it is injected only when the Analysis tab
// is first opened. This keeps all other tabs working even if the network
// cannot reach the CDN or if the local file load is slow.

let _plotlyReady = false;
let _plotlyCallbacks = [];

function loadPlotly(cb) {
  if (_plotlyReady) { cb(); return; }
  _plotlyCallbacks.push(cb);
  if (document.getElementById('plotly-script')) return; // already injecting
  const s = document.createElement('script');
  s.id = 'plotly-script';
  s.src = 'plotly-2.32.0.min.js';
  s.onload = () => {
    _plotlyReady = true;
    _plotlyCallbacks.forEach(f => f());
    _plotlyCallbacks = [];
  };
  s.onerror = () => {
    const el = document.getElementById('chart-timeline');
    if (el) el.innerHTML = '<div class="loading" style="color:#e74c6a">Plotly failed to load — charts unavailable.<br><span style="font-size:11px;color:var(--muted)">Other tabs (Lyrics, Events, Session Log) still work.</span></div>';
  };
  document.head.appendChild(s);
}

// ── Constants ────────────────────────────────────────────────────────────────

const AXIS_COLORS = {
  drug_war_mx:      '#e74c6a',
  immigration_usmx: '#5b8dee',
  elections_mx:     '#4ecb88',
  us_presidency:    '#f0a940',
};
const AXIS_LABELS = {
  drug_war_mx:      'Drug War MX',
  immigration_usmx: 'Immigration US-MX',
  elections_mx:     'Elections MX',
  us_presidency:    'US Presidency',
};
const TOPIC_COLORS = ['#5b8dee','#e74c6a','#4ecb88','#f0a940','#c97ef0','#e8a23a','#3acce8'];

const PLY = {
  paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
  font: { color: '#e8eaf0', size: 11 },
  margin: { t: 16, b: 48, l: 58, r: 18 },
  legend: { bgcolor: 'rgba(26,29,39,.9)', bordercolor: '#2e3350', borderwidth: 1 },
  xaxis: { gridcolor: '#2e3350', linecolor: '#2e3350', zerolinecolor: '#2e3350' },
  yaxis: { gridcolor: '#2e3350', linecolor: '#2e3350', zerolinecolor: '#2e3350' },
};
const PLY_CFG = { responsive: true, displayModeBar: true, modeBarButtonsToRemove: ['select2d','lasso2d'] };

// ── State ─────────────────────────────────────────────────────────────────────

let DATA = null;

const state = {
  artists: new Set(),
  method:  'keywords',
  axes:    new Set(['drug_war_mx','immigration_usmx','elections_mx','us_presidency']),
  yearMin: 1960,
  yearMax: 2026,
  search:  '',
  sortCol: 'release_year',
  sortDir: 'asc',
};

const lyricsState = {
  search:   '',
  artist:   '',
  topic:    '',
  sort:     'year_asc',
  selected: null,
  list:     [],          // filtered + sorted
};

const eventsState = {
  search: '',
  axis:   '',
  type:   '',
  sort:   'date_asc',
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function filteredSongs() {
  if (!DATA?.songs) return [];
  return DATA.songs.filter(s => {
    const yr = parseInt(s.release_year, 10) || 0;
    if (state.artists.size && !state.artists.has(s.artist)) return false;
    if (yr && (yr < state.yearMin || yr > state.yearMax)) return false;
    if (state.search) {
      const q = state.search.toLowerCase();
      const kw = getTopics(s.song_id, 'keywords').join(' ');
      if (![s.title, s.artist, String(yr), kw].some(v => v.toLowerCase().includes(q))) return false;
    }
    return true;
  });
}

function filteredEvents() {
  if (!DATA?.events) return [];
  return DATA.events.filter(e => {
    if (!state.axes.has(e.axis)) return false;
    const yr = new Date(e.date).getFullYear();
    return yr >= state.yearMin && yr <= state.yearMax;
  });
}

function getTopics(songId, method) {
  const m = DATA?.topics?.[method];
  if (!m) return [];
  if (method === 'keywords') {
    const rec = m.records.find(r => r.song_id === songId);
    if (!rec) return [];
    return (m.topic_names || []).filter(t => parseInt(rec[`${t}_hits`] || '0', 10) > 0);
  }
  if (method === 'bertopic') {
    const rec = m.records.find(r => r.song_id === songId);
    return (!rec || rec.bertopic_topic_id === '-1') ? [] : [rec.bertopic_topic_label];
  }
  if (method === 'hybrid') {
    const rec = m.records.find(r => r.song_id === songId);
    if (!rec || rec.topic_tags === 'none') return [];
    return rec.topic_tags.split('|').filter(Boolean);
  }
  return [];
}

function getKeywordHits(songId) {
  const m = DATA?.topics?.keywords;
  if (!m) return {};
  const rec = m.records.find(r => r.song_id === songId);
  if (!rec) return {};
  return Object.fromEntries(
    (m.topic_names || []).map(t => [t, { hits: parseInt(rec[`${t}_hits`]||'0',10), score: parseFloat(rec[`${t}_score`]||'0') }])
  );
}

function getSentiment(songId) {
  const m = DATA?.topics?.hybrid;
  if (!m) return null;
  return m.records.find(r => r.song_id === songId) || null;
}

function nearbyEvents(year, win = 2) {
  if (!DATA?.events) return [];
  return DATA.events
    .filter(e => Math.abs(new Date(e.date).getFullYear() - year) <= win)
    .sort((a, b) => Math.abs(new Date(a.date).getFullYear() - year) - Math.abs(new Date(b.date).getFullYear() - year));
}

function tagHTML(topics) {
  return topics.length
    ? topics.map(t => `<span class="tag tag-${t}">${t}</span>`).join('')
    : '<span class="tag tag-none">—</span>';
}

function axisHTML(axis) {
  return `<span class="ev-axis-pill axis-${axis}">${AXIS_LABELS[axis] || axis}</span>`;
}

// ── Page routing ──────────────────────────────────────────────────────────────

document.querySelectorAll('.nav-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.page;
    document.querySelectorAll('.nav-tab').forEach(b => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === target));
    if (target === 'analysis-page' && DATA) renderAnalysisWithCharts();
    if (target === 'lyrics-page' && DATA) renderLyricsList();
    if (target === 'events-page' && DATA) renderEventsTable();
    if (target === 'session-page') loadSession(document.getElementById('session-file-select').value);
  });
});

// ── Analysis page: controls ───────────────────────────────────────────────────

function initControls() {
  const artists = DATA?.meta?.artists || [];
  state.artists = new Set(artists);

  const artistPills = document.getElementById('artist-pills');
  artists.forEach(a => {
    const btn = document.createElement('button');
    btn.className = 'pill-btn active';
    btn.textContent = a.replace('Los ', '');
    btn.dataset.artist = a;
    btn.title = a;
    btn.addEventListener('click', () => {
      btn.classList.toggle('active');
      state.artists[btn.classList.contains('active') ? 'add' : 'delete'](a);
      renderAnalysisWithCharts();
    });
    artistPills.appendChild(btn);
  });

  document.getElementById('method-select').addEventListener('change', e => {
    state.method = e.target.value;
    renderAnalysisWithCharts();
  });

  const axisPills = document.getElementById('axis-pills');
  Object.entries(AXIS_LABELS).forEach(([key, label]) => {
    const btn = document.createElement('button');
    btn.className = 'pill-btn active';
    btn.textContent = label;
    btn.dataset.axis = key;
    btn.addEventListener('click', () => {
      btn.classList.toggle('active');
      state.axes[btn.classList.contains('active') ? 'add' : 'delete'](key);
      renderAnalysisWithCharts();
    });
    axisPills.appendChild(btn);
  });

  const yMin = document.getElementById('year-min');
  const yMax = document.getElementById('year-max');
  const yLbl = document.getElementById('year-range-label');
  const meta = DATA?.meta || {};
  const gMin = meta.year_min || 1968, gMax = meta.year_max || 2025;
  [yMin, yMax].forEach(el => { el.min = gMin; el.max = gMax; });
  yMin.value = gMin; yMax.value = gMax;
  state.yearMin = gMin; state.yearMax = gMax;
  yLbl.textContent = `${gMin}–${gMax}`;

  function syncYears() {
    let lo = +yMin.value, hi = +yMax.value;
    if (lo > hi) [lo, hi] = [hi, lo];
    yMin.value = lo; yMax.value = hi;
    state.yearMin = lo; state.yearMax = hi;
    yLbl.textContent = `${lo}–${hi}`;
    renderAnalysisWithCharts();
  }
  yMin.addEventListener('input', syncYears);
  yMax.addEventListener('input', syncYears);

  document.getElementById('search-box').addEventListener('input', e => {
    state.search = e.target.value;
    renderSongsTable();
  });

  // Sort on column header click
  document.querySelectorAll('#panel-songs thead th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (state.sortCol === col) state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
      else { state.sortCol = col; state.sortDir = 'asc'; }
      document.querySelectorAll('#panel-songs thead th').forEach(h => {
        h.classList.remove('sort-asc', 'sort-desc');
      });
      th.classList.add(state.sortDir === 'asc' ? 'sort-asc' : 'sort-desc');
      renderSongsTable();
    });
  });
}

// ── Analysis: stats ───────────────────────────────────────────────────────────

function renderStats() {
  const songs = filteredSongs(), events = filteredEvents();
  const yrs = songs.map(s => parseInt(s.release_year,10)).filter(Boolean);
  const noYear = DATA?.meta?.songs_no_year || 0;
  document.getElementById('stat-songs').textContent   = songs.length.toLocaleString();
  document.getElementById('stat-events').textContent  = events.length.toLocaleString();
  document.getElementById('stat-years').textContent   = yrs.length ? `${Math.min(...yrs)}–${Math.max(...yrs)}` : '—';
  document.getElementById('stat-artists').textContent = new Set(songs.map(s=>s.artist)).size;
  const noYearEl = document.getElementById('stat-no-year');
  if (noYearEl) noYearEl.textContent = noYear ? `${noYear} undated` : '0 undated';
}

// ── Analysis: Panel A ─────────────────────────────────────────────────────────

function renderTimeline() {
  const songs = filteredSongs(), events = filteredEvents();
  const artists = [...new Set(songs.map(s=>s.artist))].sort();
  const allYears = [...new Set(songs.map(s=>s.release_year).filter(Boolean))].sort();
  const ycnt = {};
  artists.forEach(a => ycnt[a] = {});
  songs.forEach(s => { if (s.release_year) ycnt[s.artist][s.release_year] = (ycnt[s.artist][s.release_year]||0)+1; });

  const traces = artists.map((a,i) => ({
    x: allYears, y: allYears.map(yr => ycnt[a][yr]||0),
    name: a, type: 'bar',
    marker: { color: i===0 ? '#5b8dee' : '#e86b3a', opacity: .85 },
  }));

  const shapes = events.map(ev => ({
    type:'line', x0: new Date(ev.date).getFullYear(), x1: new Date(ev.date).getFullYear(),
    y0:0, y1:1, xref:'x', yref:'paper',
    line: { color: AXIS_COLORS[ev.axis]||'#888', width:1.2, dash:'dot' },
  }));

  Plotly.react('chart-timeline', traces, {
    ...PLY, barmode:'stack', shapes,
    xaxis: { ...PLY.xaxis, title:'Year', dtick:5 },
    yaxis: { ...PLY.yaxis, title:'Songs' },
    height: 260,
  }, PLY_CFG);
}

// ── Analysis: Panel B ─────────────────────────────────────────────────────────

function renderTopics() {
  const songs = filteredSongs();
  const method = state.method;
  const songIds = new Set(songs.map(s=>s.song_id));
  const allYears = [...new Set(songs.map(s=>s.release_year).filter(Boolean))].sort();
  const topicsData = DATA?.topics?.[method];

  if (!topicsData) {
    Plotly.react('chart-topics', [], { ...PLY, height:280 }, PLY_CFG);
    return;
  }

  let topicNames = [];
  if (method === 'keywords') topicNames = topicsData.topic_names || [];
  else if (method === 'bertopic') {
    const labels = [...new Set(topicsData.records.filter(r=>songIds.has(r.song_id)).map(r=>r.bertopic_topic_label))];
    topicNames = labels.filter(l=>l!=='-1'&&l!=='insufficient_lyrics').slice(0,8);
  } else {
    const freq = {};
    topicsData.records.filter(r=>songIds.has(r.song_id))
      .flatMap(r=>(r.topic_tags||'').split('|'))
      .forEach(t=>{ if(t&&t!=='none') freq[t]=(freq[t]||0)+1; });
    topicNames = Object.entries(freq).sort((a,b)=>b[1]-a[1]).slice(0,6).map(([t])=>t);
  }

  const traces = topicNames.map((topic,i) => {
    const yrScores = {};
    allYears.forEach(yr => yrScores[yr]=[]);
    songs.forEach(s => {
      if (!yrScores[s.release_year]) return;
      if (method==='keywords') {
        const rec = topicsData.records.find(r=>r.song_id===s.song_id);
        yrScores[s.release_year].push(rec ? parseFloat(rec[`${topic}_score`]||'0') : 0);
      } else {
        yrScores[s.release_year].push(getTopics(s.song_id,method).includes(topic) ? 1 : 0);
      }
    });
    return {
      x: allYears,
      y: allYears.map(yr => { const v=yrScores[yr]; return v.length ? v.reduce((a,b)=>a+b,0)/v.length : null; }),
      name: topic, mode:'lines+markers',
      line: { color: TOPIC_COLORS[i%TOPIC_COLORS.length], width:2 },
      marker: { size:4 }, connectgaps: true,
    };
  });

  Plotly.react('chart-topics', traces, {
    ...PLY,
    xaxis: { ...PLY.xaxis, title:'Year', dtick:5 },
    yaxis: { ...PLY.yaxis, title: method==='keywords' ? 'Score (hits/1000 words)' : 'Fraction of songs' },
    height: 280,
  }, PLY_CFG);
}

// ── Analysis: Panel C ─────────────────────────────────────────────────────────

function renderHeatmap() {
  const songs = filteredSongs();
  const method = state.method;
  const td = DATA?.topics?.[method];
  if (!td) return;

  const decades = [...new Set(songs.map(s=>{ const y=parseInt(s.release_year,10); return isNaN(y)?null:Math.floor(y/10)*10; }).filter(Boolean))].sort();
  let topicNames = [];
  if (method==='keywords') topicNames = td.topic_names||[];
  else if (method==='hybrid') {
    const freq={};
    td.records.flatMap(r=>(r.topic_tags||'').split('|')).forEach(t=>{ if(t&&t!=='none') freq[t]=(freq[t]||0)+1; });
    topicNames = Object.entries(freq).sort((a,b)=>b[1]-a[1]).slice(0,6).map(([t])=>t);
  } else topicNames = [...new Set(td.records.map(r=>r.bertopic_topic_label))].filter(l=>l&&l!=='-1'&&l!=='insufficient_lyrics').slice(0,8);

  const z = topicNames.map(topic =>
    decades.map(dec => {
      const ds = songs.filter(s => Math.floor(parseInt(s.release_year,10)/10)*10===dec);
      if (!ds.length) return 0;
      const scores = ds.map(s => {
        if (method==='keywords') {
          const rec = td.records.find(r=>r.song_id===s.song_id);
          return rec ? parseFloat(rec[`${topic}_score`]||'0') : 0;
        }
        return getTopics(s.song_id,method).includes(topic) ? 1 : 0;
      });
      return scores.reduce((a,b)=>a+b,0)/scores.length;
    })
  );

  Plotly.react('chart-heatmap', [{
    type:'heatmap', z, x: decades.map(d=>`${d}s`), y: topicNames,
    colorscale: [[0,'rgba(91,141,238,.05)'],[.3,'rgba(91,141,238,.4)'],[.7,'rgba(91,141,238,.7)'],[1,'#5b8dee']],
    showscale:true,
    hovertemplate:'Decade: %{x}<br>Topic: %{y}<br>Score: %{z:.4f}<extra></extra>',
  }], { ...PLY, height:260, margin:{...PLY.margin,l:120}, xaxis:{...PLY.xaxis,title:'Decade'}, yaxis:{...PLY.yaxis,title:''} }, PLY_CFG);
}

// ── Analysis: Panel D ─────────────────────────────────────────────────────────

function renderSentiment() {
  const songs = filteredSongs();
  const hd = DATA?.topics?.hybrid;
  if (!hd) return;

  const allYears = [...new Set(songs.map(s=>s.release_year).filter(Boolean))].sort();
  const by = {};
  allYears.forEach(yr => by[yr]={POS:0,NEG:0,NEU:0,total:0});
  songs.forEach(s => {
    const rec = hd.records.find(r=>r.song_id===s.song_id);
    if (!rec||!by[s.release_year]) return;
    by[s.release_year][rec.sentiment_label] = (by[s.release_year][rec.sentiment_label]||0)+1;
    by[s.release_year].total++;
  });

  const traces = [{name:'Positive',color:'#4ecb88',key:'POS'},{name:'Negative',color:'#e74c6a',key:'NEG'},{name:'Neutral',color:'#7b80a0',key:'NEU'}]
    .map(({name,color,key}) => ({
      x:allYears, y:allYears.map(yr => by[yr].total ? by[yr][key]/by[yr].total*100 : null),
      name, mode:'lines', line:{color,width:2}, connectgaps:true,
    }));

  Plotly.react('chart-sentiment', traces, {
    ...PLY, height:260,
    xaxis:{...PLY.xaxis,title:'Year',dtick:5},
    yaxis:{...PLY.yaxis,title:'% songs',ticksuffix:'%'},
  }, PLY_CFG);
}

// ── Analysis: Panel E (song table) ───────────────────────────────────────────

function renderSongsTable() {
  let songs = filteredSongs();

  // sort
  songs = songs.slice().sort((a,b) => {
    let av = a[state.sortCol] || '', bv = b[state.sortCol] || '';
    if (state.sortCol === 'release_year') { av = parseInt(av)||0; bv = parseInt(bv)||0; }
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return state.sortDir === 'asc' ? cmp : -cmp;
  });

  const tbody = document.getElementById('songs-tbody');
  tbody.innerHTML = '';
  const frag = document.createDocumentFragment();

  songs.slice(0,500).forEach(song => {
    const topics = getTopics(song.song_id, 'keywords');
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${song.release_year||'—'}</td>
      <td style="color:var(--muted)">${song.artist.replace('Los ','')}</td>
      <td title="${song.title}">${song.title}</td>
      <td>${tagHTML(topics)}</td>
      <td style="color:var(--muted)">${song.word_count||'—'}</td>
      <td>${song.genius_url ? `<a href="${song.genius_url}" target="_blank" style="color:var(--accent);font-size:11px" onclick="event.stopPropagation()">Genius ↗</a>` : '—'}</td>
    `;
    tr.addEventListener('click', () => openModal(song));
    frag.appendChild(tr);
  });

  if (songs.length > 500) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td colspan="6" style="text-align:center;color:var(--muted);padding:10px;font-size:11px">Showing 500 of ${songs.length} — refine search or year range.</td>`;
    frag.appendChild(tr);
  }
  tbody.appendChild(frag);
}

// ── Analysis modal ────────────────────────────────────────────────────────────

function openModal(song) {
  document.getElementById('modal-title').textContent = song.title;
  document.getElementById('modal-meta').innerHTML =
    `${song.artist} &mdash; ${song.release_year||'?'} &mdash; ${song.album||'No album'}
     ${song.genius_url ? ` &mdash; <a href="${song.genius_url}" target="_blank" style="color:var(--accent)">Genius ↗</a>` : ''}
     ${song.retrieved_at ? `<br><span style="color:var(--muted)">Retrieved ${song.retrieved_at.slice(0,10)}</span>` : ''}`;

  const topicsKW = getTopics(song.song_id,'keywords');
  const topicsBT = getTopics(song.song_id,'bertopic');
  const topicsHY = getTopics(song.song_id,'hybrid');
  const sent = getSentiment(song.song_id);
  const nearby = nearbyEvents(parseInt(song.release_year,10)||0, 2);
  const kwHits = getKeywordHits(song.song_id);

  const body = document.getElementById('modal-body');
  body.innerHTML = '';

  // Topics
  const topicSec = document.createElement('div');
  topicSec.className = 'modal-section';
  topicSec.innerHTML = `<h4>Topic Tags</h4>
  <div class="modal-method-row">
    <div class="modal-method">
      <div class="method-name">Keywords (M1)</div>
      <div>${topicsKW.length ? topicsKW.map(t=>`<span class="tag tag-${t}">${t}</span>`).join('') : '<span style="color:var(--muted)">none</span>'}</div>
    </div>
    <div class="modal-method">
      <div class="method-name">BERTopic (M2)</div>
      <div>${topicsBT.length ? topicsBT.map(t=>`<span class="tag" style="background:rgba(201,126,240,.15);color:#c97ef0">${t}</span>`).join('') : '<span style="color:var(--muted)">—</span>'}</div>
    </div>
    <div class="modal-method">
      <div class="method-name">Hybrid (M3)</div>
      <div>${topicsHY.length ? topicsHY.map(t=>`<span class="tag tag-${t}">${t}</span>`).join('') : '<span style="color:var(--muted)">—</span>'}
        ${sent ? `<div style="margin-top:6px;font-size:12px">Sentiment: <b class="sent-${sent.sentiment_label}">${sent.sentiment_label}</b> · Emotion: <b>${sent.emotion_label}</b></div>` : ''}
      </div>
    </div>
  </div>`;
  body.appendChild(topicSec);

  // Keyword hit breakdown
  const hitEntries = Object.entries(kwHits).filter(([,v])=>v.hits>0);
  if (hitEntries.length) {
    const kSec = document.createElement('div');
    kSec.className = 'modal-section';
    kSec.innerHTML = `<h4>Keyword Hits</h4>
    <div style="display:flex;gap:12px;flex-wrap:wrap">
      ${hitEntries.map(([t,v])=>`
        <div style="background:var(--surface2);border-radius:6px;padding:8px 12px;min-width:120px">
          <div style="font-size:10px;text-transform:uppercase;color:var(--muted);margin-bottom:4px">${t}</div>
          <div style="font-size:18px;font-weight:700">${v.hits} <span style="font-size:11px;color:var(--muted)">hits</span></div>
          <div style="font-size:11px;color:var(--muted)">${v.score.toFixed(3)} / 1k words</div>
        </div>`).join('')}
    </div>`;
    body.appendChild(kSec);
  }

  // Lyrics
  const lyrText = song.lyrics || song.lyrics_preview || '';
  if (lyrText) {
    const lSec = document.createElement('div');
    lSec.className = 'modal-section';
    lSec.innerHTML = `<h4>Lyrics${song.lyrics ? '' : ' (excerpt)'}</h4>
    <div class="lyrics-box">${lyrText}</div>`;
    body.appendChild(lSec);
  }

  // Nearby events
  if (nearby.length) {
    const eSec = document.createElement('div');
    eSec.className = 'modal-section';
    eSec.innerHTML = `<h4>Nearby Political Events (±2 years)</h4>
    <div class="modal-events-list">
      ${nearby.slice(0,6).map(ev=>`
        <div class="modal-event ev-${ev.axis}">
          <div class="ev-title">${ev.date.slice(0,7)} — ${ev.title}</div>
          <div class="ev-meta">${ev.description||''}${ev.source_url?`<br><a href="${ev.source_url}" target="_blank">source ↗</a>`:''}</div>
        </div>`).join('')}
    </div>`;
    body.appendChild(eSec);
  }

  document.getElementById('modal-overlay').classList.add('open');
}

document.getElementById('modal-close').addEventListener('click', () => document.getElementById('modal-overlay').classList.remove('open'));
document.getElementById('modal-overlay').addEventListener('click', e => { if (e.target.id==='modal-overlay') document.getElementById('modal-overlay').classList.remove('open'); });
document.addEventListener('keydown', e => { if (e.key==='Escape') document.getElementById('modal-overlay').classList.remove('open'); });

function renderAnalysis() {
  renderStats();
  renderSongsTable();
  if (typeof Plotly === 'undefined') return; // charts wait for Plotly
  renderTimeline();
  renderTopics();
  renderHeatmap();
  renderSentiment();
}

function renderAnalysisWithCharts() {
  loadPlotly(() => renderAnalysis());
}

// ── Lyrics Browser page ───────────────────────────────────────────────────────

function buildLyricsList() {
  let songs = DATA?.songs ? [...DATA.songs] : [];

  // populate filters once
  const af = document.getElementById('lyrics-artist-filter');
  if (af.options.length === 1) {
    [...new Set(songs.map(s=>s.artist))].sort().forEach(a => {
      const o = document.createElement('option'); o.value=a; o.textContent=a; af.appendChild(o);
    });
  }
  const tf = document.getElementById('lyrics-topic-filter');
  if (tf.options.length === 1) {
    const topicNames = DATA?.topics?.keywords?.topic_names || [];
    topicNames.forEach(t => {
      const o = document.createElement('option'); o.value=t; o.textContent=t; tf.appendChild(o);
    });
  }

  // filter
  const q = lyricsState.search.toLowerCase();
  if (lyricsState.artist) songs = songs.filter(s=>s.artist===lyricsState.artist);
  if (lyricsState.topic)  songs = songs.filter(s=>getTopics(s.song_id,'keywords').includes(lyricsState.topic));
  if (q) songs = songs.filter(s => {
    const lyrics = (s.lyrics||s.lyrics_preview||'').toLowerCase();
    return s.title.toLowerCase().includes(q) || (s.album||'').toLowerCase().includes(q)
      || (s.release_year||'').includes(q) || lyrics.includes(q);
  });

  // sort
  const sorters = {
    year_asc:   (a,b) => (parseInt(a.release_year)||0)-(parseInt(b.release_year)||0),
    year_desc:  (a,b) => (parseInt(b.release_year)||0)-(parseInt(a.release_year)||0),
    title_asc:  (a,b) => a.title.localeCompare(b.title),
    words_desc: (a,b) => (parseInt(b.word_count)||0)-(parseInt(a.word_count)||0),
  };
  songs.sort(sorters[lyricsState.sort] || sorters.year_asc);

  lyricsState.list = songs;
  return songs;
}

function renderLyricsList() {
  const songs = buildLyricsList();
  document.getElementById('lyrics-count').textContent = `${songs.length} song${songs.length!==1?'s':''}`;

  const container = document.getElementById('lyrics-list');
  container.innerHTML = '';
  const frag = document.createDocumentFragment();

  songs.forEach(song => {
    const topics = getTopics(song.song_id, 'keywords');
    const div = document.createElement('div');
    div.className = 'lyric-item' + (lyricsState.selected?.song_id===song.song_id?' selected':'');
    div.innerHTML = `
      <div class="li-title">${song.title}</div>
      <div class="li-meta">
        <span>${song.artist.replace('Los ','')}</span>
        <span>${song.release_year||'?'}</span>
        ${song.album ? `<span style="color:var(--muted)">${song.album}</span>` : ''}
        <span>${song.word_count||'0'} words</span>
      </div>
      ${topics.length ? `<div class="li-tags">${tagHTML(topics)}</div>` : ''}
    `;
    div.addEventListener('click', () => {
      lyricsState.selected = song;
      document.querySelectorAll('.lyric-item').forEach(el => el.classList.remove('selected'));
      div.classList.add('selected');
      renderSongDetail(song);
    });
    frag.appendChild(div);
  });

  container.appendChild(frag);

  // restore selection if still in list
  if (lyricsState.selected) {
    const still = songs.find(s=>s.song_id===lyricsState.selected?.song_id);
    if (still) renderSongDetail(still);
  }
}

function renderSongDetail(song) {
  const panel = document.getElementById('lyrics-right');
  panel.classList.remove('empty');

  const topics = getTopics(song.song_id, 'keywords');
  const kwHits = getKeywordHits(song.song_id);
  const sent   = getSentiment(song.song_id);
  const nearby = nearbyEvents(parseInt(song.release_year,10)||0, 2);
  const hitEntries = Object.entries(kwHits).filter(([,v])=>v.hits>0);
  const fullLyrics = song.lyrics || '';
  const preview    = song.lyrics_preview || '';

  panel.innerHTML = `<div id="song-detail">
    <div class="song-title">${song.title}</div>

    <div class="song-meta-row">
      <div class="song-meta-item">
        <div class="smk">Artist</div>
        <div class="smv">${song.artist}</div>
      </div>
      <div class="song-meta-item">
        <div class="smk">Year</div>
        <div class="smv">${song.release_year||'Unknown'}</div>
      </div>
      ${song.release_date&&song.release_date!==song.release_year ? `<div class="song-meta-item"><div class="smk">Date</div><div class="smv">${song.release_date}</div></div>` : ''}
      ${song.album ? `<div class="song-meta-item"><div class="smk">Album</div><div class="smv">${song.album}</div></div>` : ''}
      <div class="song-meta-item">
        <div class="smk">Word count</div>
        <div class="smv">${song.word_count||'0'}</div>
      </div>
      <div class="song-meta-item">
        <div class="smk">Language</div>
        <div class="smv">${song.language||'es'}</div>
      </div>
      <div class="song-meta-item">
        <div class="smk">Song ID</div>
        <div class="smv" style="color:var(--muted)">${song.song_id}</div>
      </div>
      ${song.genius_url ? `<div class="song-meta-item"><div class="smk">Source</div><div class="smv"><a href="${song.genius_url}" target="_blank">Genius ↗</a></div></div>` : ''}
      ${song.retrieved_at ? `<div class="song-meta-item"><div class="smk">Retrieved</div><div class="smv" style="color:var(--muted)">${song.retrieved_at.slice(0,10)}</div></div>` : ''}
    </div>

    ${topics.length||sent ? `
    <div>
      <div class="section-label">Topic Tags</div>
      <div class="topic-row">${tagHTML(topics)}</div>
      ${sent ? `<div style="margin-top:8px;font-size:12px;color:var(--muted)">Sentiment: <b class="sent-${sent.sentiment_label}">${sent.sentiment_label}</b> (${sent.sentiment_score}) &nbsp;·&nbsp; Emotion: <b>${sent.emotion_label}</b> (${sent.emotion_score})</div>` : ''}
    </div>` : ''}

    ${hitEntries.length ? `
    <div>
      <div class="section-label">Keyword Hit Breakdown</div>
      <div class="keyword-detail">
        <table>
          <thead><tr><th style="color:var(--muted);padding-bottom:4px">Lexicon</th><th style="color:var(--muted);text-align:right">Hits</th><th style="color:var(--muted);text-align:right">Score/1k</th></tr></thead>
          <tbody>
            ${hitEntries.map(([t,v])=>`<tr><td><span class="tag tag-${t}">${t}</span></td><td style="text-align:right;color:var(--text)">${v.hits}</td><td style="text-align:right;color:var(--accent)">${v.score.toFixed(4)}</td></tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>` : ''}

    ${nearby.length ? `
    <div>
      <div class="section-label">Political Context (±2 years from ${song.release_year||'?'})</div>
      <div class="nearby-events">
        ${nearby.slice(0,8).map(ev=>`
          <div class="ev-card ev-${ev.axis}">
            <div class="ev-title">${ev.date.slice(0,7)} &mdash; ${ev.title}</div>
            <div class="ev-desc">${ev.description||''}</div>
            ${ev.source_url ? `<div class="ev-src"><a href="${ev.source_url}" target="_blank">${ev.source_type||'source'} ↗</a></div>` : ''}
          </div>`).join('')}
      </div>
    </div>` : ''}

    ${fullLyrics||preview ? `
    <div>
      <div class="section-label">Full Lyrics${fullLyrics?'':' (preview)'}</div>
      <div class="lyrics-full">${(fullLyrics||preview)}</div>
    </div>` : '<div style="color:var(--muted);font-size:13px">No lyrics available for this song.</div>'}
  </div>`;
}

// Lyrics page wiring
document.getElementById('lyrics-search').addEventListener('input', e => {
  lyricsState.search = e.target.value;
  renderLyricsList();
});
document.getElementById('lyrics-artist-filter').addEventListener('change', e => {
  lyricsState.artist = e.target.value;
  renderLyricsList();
});
document.getElementById('lyrics-topic-filter').addEventListener('change', e => {
  lyricsState.topic = e.target.value;
  renderLyricsList();
});
document.getElementById('lyrics-sort').addEventListener('change', e => {
  lyricsState.sort = e.target.value;
  renderLyricsList();
});

// ── Political Events page ─────────────────────────────────────────────────────

function renderEventsTable() {
  let events = DATA?.events ? [...DATA.events] : [];

  // populate type filter once
  const tf = document.getElementById('events-type-filter');
  if (tf.options.length === 1) {
    [...new Set(events.map(e=>e.subtype).filter(Boolean))].sort().forEach(t => {
      const o = document.createElement('option'); o.value=t; o.textContent=t; tf.appendChild(o);
    });
  }

  const q = eventsState.search.toLowerCase();
  if (eventsState.axis) events = events.filter(e=>e.axis===eventsState.axis);
  if (eventsState.type) events = events.filter(e=>e.subtype===eventsState.type);
  if (q) events = events.filter(e =>
    (e.title||'').toLowerCase().includes(q) ||
    (e.description||'').toLowerCase().includes(q) ||
    (e.notes||'').toLowerCase().includes(q)
  );

  const sorters = {
    date_asc:  (a,b) => a.date.localeCompare(b.date),
    date_desc: (a,b) => b.date.localeCompare(a.date),
    axis:      (a,b) => a.axis.localeCompare(b.axis) || a.date.localeCompare(b.date),
  };
  events.sort(sorters[eventsState.sort] || sorters.date_asc);

  document.getElementById('ev-count').textContent = `${events.length} event${events.length!==1?'s':''}`;

  const tbody = document.getElementById('events-tbody');
  tbody.innerHTML = '';
  const frag = document.createDocumentFragment();
  events.forEach(ev => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="color:var(--muted);white-space:nowrap">${ev.date||'—'}</td>
      <td>${axisHTML(ev.axis)}</td>
      <td style="color:var(--muted)">${ev.subtype||'—'}</td>
      <td style="font-weight:500;white-space:normal;max-width:260px">${ev.title||'—'}</td>
      <td style="color:var(--muted);white-space:normal;max-width:360px;font-size:11px;line-height:1.5">${ev.description||''}</td>
      <td>${ev.source_url ? `<a href="${ev.source_url}" target="_blank" style="color:var(--accent);font-size:11px" onclick="event.stopPropagation()">${ev.source_type||'link'} ↗</a>` : '—'}</td>
      <td style="color:var(--muted);white-space:normal;font-size:11px">${ev.notes||''}</td>
    `;
    frag.appendChild(tr);
  });
  tbody.appendChild(frag);
}

// Events page wiring
document.getElementById('events-search').addEventListener('input', e => { eventsState.search=e.target.value; renderEventsTable(); });
document.getElementById('events-axis-filter').addEventListener('change', e => { eventsState.axis=e.target.value; renderEventsTable(); });
document.getElementById('events-type-filter').addEventListener('change', e => { eventsState.type=e.target.value; renderEventsTable(); });
document.getElementById('events-sort').addEventListener('change', e => { eventsState.sort=e.target.value; renderEventsTable(); });

// ── Session Log page ─────────────────────────────────────────────────────────

async function loadSession(filename) {
  const container = document.getElementById('session-messages');
  container.innerHTML = '<div class="loading">Loading…</div>';
  try {
    const res = await fetch(`prompts/${filename}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const messages = await res.json();
    renderSession(messages, container);
  } catch(e) {
    container.innerHTML = `<div style="color:var(--muted);font-size:13px;padding:20px 0">Could not load session file: ${e.message}<br><br>Make sure you are serving from the <code style="color:var(--accent)">dashboard/</code> directory and <code style="color:var(--accent)">prompts/session_01.json</code> exists.</div>`;
  }
}

function renderSession(messages, container) {
  container.innerHTML = '';
  const frag = document.createDocumentFragment();
  messages.forEach(msg => {
    const div = document.createElement('div');
    div.className = `msg ${msg.role}`;

    const avatarText = msg.role === 'user' ? 'JN' : 'AI';
    const roleLabel  = msg.role === 'user' ? 'Jin' : 'Claude';

    div.innerHTML = `
      <div class="msg-avatar">${avatarText}</div>
      <div>
        <div class="msg-id">#${msg.id}</div>
        <div class="msg-bubble">
          <div class="msg-role">${roleLabel}</div>
          <div>${msg.content}</div>
          ${msg.note ? `<div class="msg-note">${msg.note}</div>` : ''}
        </div>
      </div>
    `;
    frag.appendChild(div);
  });
  container.appendChild(frag);
}

document.getElementById('session-file-select').addEventListener('change', e => {
  loadSession(e.target.value);
});

// ── Boot ──────────────────────────────────────────────────────────────────────

async function boot() {
  try {
    const res = await fetch('data.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    DATA = await res.json();
  } catch(e) {
    document.getElementById('chart-timeline').innerHTML =
      `<div class="loading" style="flex-direction:column;gap:8px">
        <div style="color:#e74c6a">data.json not found</div>
        <div style="font-size:11px;color:var(--muted)">Run <code style="color:#f0a940">python src/export_dashboard.py</code> then serve with <code style="color:#f0a940">python -m http.server 8000 -d dashboard</code></div>
      </div>`;
    return;
  }
  initControls();
  // Stats and song table render immediately; charts load Plotly first
  renderStats();
  renderSongsTable();
  loadPlotly(() => renderAnalysis());
}

boot();
