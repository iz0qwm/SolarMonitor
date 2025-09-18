// dashboard.js

// ---- Overlay caricamento (autoiniettato se manca) ----
let loadingEl, loadingLog, loadingTitle, loadingSub;
let _loadingTimer = null;
let _loadingShown = false;

function ensureOverlay() {
  if (loadingEl && loadingLog && loadingTitle && loadingSub) return;

  // prova a prenderli se esistono già
  loadingEl    = document.getElementById('loading');
  loadingLog   = document.getElementById('loading-log');
  loadingTitle = document.getElementById('loading-title');
  loadingSub   = document.getElementById('loading-sub');

  // altrimenti crea tutto
  if (!loadingEl) {
    loadingEl = document.createElement('div');
    loadingEl.id = 'loading';
    loadingEl.setAttribute('role', 'dialog');
    loadingEl.setAttribute('aria-live', 'polite');
    loadingEl.style.cssText = 'position:fixed;inset:0;display:none;z-index:5000;align-items:center;justify-content:center;background:rgba(255,255,255,.9)';

    const box = document.createElement('div');
    box.className = 'loading-box';
    box.style.cssText = 'width:min(720px,92vw);background:#fff;border:1px solid #ddd;border-radius:12px;box-shadow:0 18px 50px rgba(0,0,0,.15);padding:14px;';

    const head = document.createElement('div');
    head.className = 'loading-head';
    head.style.cssText = 'display:flex;align-items:center;gap:.6rem;margin-bottom:.5rem;';

    const dot = document.createElement('div');
    dot.className = 'loading-dot';
    dot.style.cssText = 'width:10px;height:10px;border-radius:50%;background:#6aa0ff;animation:pulse 1s infinite';

    const keyframes = document.createElement('style');
    keyframes.textContent = '@keyframes pulse{0%{opacity:.3}50%{opacity:1}100%{opacity:.3}}';
    document.head.appendChild(keyframes);

    loadingTitle = document.createElement('strong');
    loadingTitle.id = 'loading-title';
    loadingSub = document.createElement('span');
    loadingSub.id = 'loading-sub';
    loadingSub.style.cssText = 'margin-left:.25rem;color:#666;font-size:12px';

    head.appendChild(dot);
    head.appendChild(loadingTitle);
    head.appendChild(loadingSub);

    loadingLog = document.createElement('div');
    loadingLog.id = 'loading-log';
    loadingLog.style.cssText = 'font:12px/1.4 ui-monospace,Menlo,Consolas,monospace;background:#f7f8fa;border:1px solid #e6eaf2;padding:8px;border-radius:8px;max-height:45vh;overflow:auto;white-space:pre-wrap;';

    box.appendChild(head);
    box.appendChild(loadingLog);
    loadingEl.appendChild(box);
    document.body.appendChild(loadingEl);
  }
}

function showLoading(title, sub){
  ensureOverlay();
  if (_loadingShown) return;
  loadingTitle.textContent = title || 'Caricamento…';
  loadingSub.textContent   = sub || '';
  loadingLog.textContent   = 'Avvio…';
  _loadingTimer = setTimeout(()=>{
    loadingEl.style.display = 'flex';
    _loadingShown = true;
  }, 400);
}
function logLoading(line){
  if (!_loadingShown && _loadingTimer === null) return; // niente log se non visibile o mai aperto
  ensureOverlay();
  loadingLog.textContent += '\n' + line;
  loadingLog.scrollTop = loadingLog.scrollHeight;
}
function hideLoading(){
  if (_loadingTimer){ clearTimeout(_loadingTimer); _loadingTimer = null; }
  if (_loadingShown){
    loadingEl.style.display = 'none';
    _loadingShown = false;
  }
}

// ---- fine overlay ----




let currentDay = null; // string "YYYY-MM-DD" oppure null per "finestra scorrevole"
const dayPicker = document.getElementById('dayPicker');
const prevDayBtn = document.getElementById('prevDayBtn');
const nextDayBtn = document.getElementById('nextDayBtn');
const dayLabel   = document.getElementById('dayLabel');


// Colorazione badges

function colorForKp(kp){
  if (!Number.isFinite(kp)) return {bg:'#eef6ff', fg:'#111', label:'—'};
  // Mappa richiesta:
  // Kp < 5 → Verde
  // Kp = 5 (G1) → Giallo
  // Kp = 6 (G2) → Arancio chiaro
  // Kp = 7 (G3) → Arancione
  // Kp = 8, 9- (G4) → Rosso chiaro
  // Kp = 9o (G5) → Rosso (interpreto 9.0 pieno)
  if (kp < 4)                  return {bg:'#C7F2C8', fg:'#0B3D0B', label:`${kp.toFixed(2)}`};        // verde
  if (kp >= 4 && kp < 5)       return {bg:'#FFF3B0', fg:'#5C4800', label:`${kp.toFixed(2)} (G1)`};   // giallo
  if (kp >= 5 && kp < 6)       return {bg:'#FFD8A8', fg:'#5A3A00', label:`${kp.toFixed(2)} (G2)`};   // arancio chiaro
  if (kp >= 6 && kp < 7)       return {bg:'#FFC078', fg:'#5A2A00', label:`${kp.toFixed(2)} (G3)`};   // arancione
  if (kp >= 7 && kp < 9)       return {bg:'#FFA8A8', fg:'#5A0B0B', label:`${kp.toFixed(2)} (G4)`};   // rosso chiaro
  if (kp >= 9)                 return {bg:'#FF6B6B', fg:'#fff',    label:`${kp.toFixed(2)} (G5)`};   // rosso pieno

  return {bg:'#eef6ff', fg:'#111', label:`${kp.toFixed(2)}`};
}

function colorForTEC(tec){
  // TECu:
  // Quiet: <125 → Verde
  // Moderate: >=125 → Arancione
  // Severe: >=175 → Rosso
  if (!Number.isFinite(tec)) return {bg:'#f6efff', fg:'#111', label:'—'};
  if (tec < 125)  return {bg:'#C7F2C8', fg:'#0B3D0B', label:`${tec.toFixed(0)} TECu (Quiet)`};
  if (tec < 175)  return {bg:'#FFC078', fg:'#5A2A00', label:`${tec.toFixed(0)} TECu (Moderate)`};
  return            {bg:'#FF6B6B', fg:'#fff',          label:`${tec.toFixed(0)} TECu (Severe)`};
}

function setDay(dStr){
  currentDay = dStr;
  if (dayPicker) dayPicker.value = dStr || "";
  if (dayLabel){
    dayLabel.textContent = dStr ? `Giorno selezionato: ${dStr}` : "In tempo reale (ultima finestra)";
  }
  // Overlay informativo
  showLoading(dStr ? `Caricamento storico ${dStr}` : 'Caricamento dati live',
              dStr ? 'Lettura da database…' : 'Lettura da CSV + DB…');
  refreshAll();
}


function shiftDay(delta){ // delta = ±1 giorni
  let d = currentDay ? new Date(currentDay) : new Date();
  d.setUTCDate(d.getUTCDate() + delta);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth()+1).padStart(2,'0');
  const dd= String(d.getUTCDate()).padStart(2,'0');
  setDay(`${y}-${m}-${dd}`);
}

// init day controls
if (dayPicker){
  dayPicker.addEventListener('change', e => {
    setDay(e.target.value || null);
  });
}
if (prevDayBtn){ prevDayBtn.addEventListener('click', () => shiftDay(-1)); }
if (nextDayBtn){ nextDayBtn.addEventListener('click', () => shiftDay(+1)); }
// all’avvio mostra “oggi” come default navigabile
(function initDay(){
  const now = new Date();
  const y = now.getUTCFullYear();
  const m = String(now.getUTCMonth()+1).padStart(2,'0');
  const dd= String(now.getUTCDate()).padStart(2,'0');
  setDay(`${y}-${m}-${dd}`);
})();



async function fetchJSON(url){
  const r = await fetch(url);
  const txt = await r.text();
  try {
    return JSON.parse(txt);
  } catch (e) {
    const fixed = txt
      .replace(/\bNaN\b/g, 'null')
      .replace(/\b-?Infinity\b/g, 'null');
    return JSON.parse(fixed);
  }
}


function q(params){
  // helper per serializzare query
  return Object.entries(params).filter(([,v]) => v !== undefined && v !== null && v !== "")
    .map(([k,v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&");
}

async function loadSummary(){
  const url = `/api/summary?` + q({
    day: currentDay || undefined,
    minutes: currentDay ? 1440 : 4320
  });
  const r = await fetch(url);
  return r.json();
}

async function loadSeries(metric, opts={}){
  const url = `/api/series?` + q({
    metric,
    band: opts.band,
    agg:  opts.agg,
    window: opts.window,
    day: currentDay || undefined,
    minutes: currentDay ? 1440 : (opts.minutes || 4320)
  });
  const r = await fetch(url);
  return r.json();
}

async function loadSeriesGps(metric, opts={}){
  const url = `/api/series_gps?` + q({
    metric,
    agg:  opts.agg,
    window: opts.window,
    day: currentDay || undefined,
    minutes: currentDay ? 1440 : (opts.minutes || 4320)
  });
  const r = await fetch(url);
  return r.json();
}

async function loadGpsTrack(minutes=180){
  const url = `/api/gps_track?` + q({
    day: currentDay || undefined,
    minutes: currentDay ? 1440 : minutes
  });
  const r = await fetch(url);
  return r.json();
}

// cache grafici
const charts = {};

function upsertLine(canvasId, label, points) {
  const ctx = document.getElementById(canvasId).getContext('2d');

  // Convertiamo timestamp ISO → millisecondi
  const dataPoints = (points || []).map(([t, v]) => {
    const ms = Date.parse(t);
    return { x: isNaN(ms) ? null : ms, y: v };
  }).filter(p => p.x !== null);

  if (!window._charts) window._charts = {};
  const existing = window._charts[canvasId];

  if (existing) {
    // aggiorna dati
    existing.data.datasets[0].data = dataPoints;
    existing.update();
  } else {
    // crea grafico nuovo
    window._charts[canvasId] = new Chart(ctx, {
      type: 'line',
      data: {
        datasets: [{
          label: label,
          data: dataPoints,
          borderColor: 'blue',
          fill: false,
          pointRadius: 2
        }]
      },
      options: {
        parsing: false, // importante per usare {x,y}
        scales: {
          x: {
            type: 'linear',
            ticks: {
              callback: (val) => {
                // val = ms, convertiamo a HH:mm
                const d = new Date(val);
                return d.toLocaleTimeString('it-IT', {
                  hour: '2-digit',
                  minute: '2-digit'
                });
              },
              autoSkip: true,
              maxRotation: 0
            }
          },
          y: {
            beginAtZero: false
          }
        }
      }
    });
  }
}


// Leaflet map
let map, marker, trail;
function ensureMap(){
  if (map) return;
  map = L.map('map', { zoomControl: true });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap'
  }).addTo(map);
  marker = L.circleMarker([0,0], { radius: 6 }).addTo(map);
  trail  = L.polyline([], { weight: 3, opacity: .8 }).addTo(map);
}

async function refreshAll(){
  try{
    const minutesParam = currentDay ? 1440 : 4320;
    const shortM       = currentDay ? 1440 : 180;
    const agg          = currentDay ? "median" : "";
    const win          = currentDay ? "5min"  : "";

    const tasks = [
      ['summary',     loadSummary()],
      ['latest',      fetchJSON('/api/latest')],
      ['glossary',    fetchJSON('/api/glossary')],
      ['tec',         loadSeriesGps("tec",      { agg, window: win, minutes: minutesParam })],
      ['hdop',        loadSeriesGps("hdop",     { agg, window: win, minutes: minutesParam })],
      ['pdop',        loadSeriesGps("pdop",     { agg, window: win, minutes: minutesParam })],
      ['vdop',        loadSeriesGps("vdop",     { agg, window: win, minutes: minutesParam })],
      ['cn0',         loadSeriesGps("cn0_mean", { agg, window: win, minutes: minutesParam })],
      ['sv_used',     loadSeriesGps("sv_used",  { agg, window: win, minutes: minutesParam })],
      ['noise24',     loadSeries("noise_dbm", { band:"24", agg, window: win, minutes: minutesParam })],
      ['noise58',     loadSeries("noise_dbm", { band:"58", agg, window: win, minutes: minutesParam })],
      ['scan24',      loadSeries("scan_p50",  { band:"24", agg, window: win, minutes: minutesParam })],
      ['scan58',      loadSeries("scan_p50",  { band:"58", agg, window: win, minutes: minutesParam })],
      ['busy24',      loadSeries("busy_ratio", { band:"24", agg, window: win, minutes: minutesParam })],
      ['busy58',      loadSeries("busy_ratio", { band:"58", agg, window: win, minutes: minutesParam })],
      ['kp',          loadSeries("kp",        { minutes: minutesParam })],
      ['track',       loadGpsTrack(shortM)],
      ['temp',   loadSeriesGps("t_c",   { agg, window: win, minutes: minutesParam })],
      ['hum',    loadSeriesGps("rh_pct",{ agg, window: win, minutes: minutesParam })],
      ['press',  loadSeriesGps("p_hpa",{ agg, window: win, minutes: minutesParam })],
      ['mag',    loadSeriesGps("mag_norm_ut",{ agg, window: win, minutes: minutesParam })],

    ];

    logLoading('Richieste inviate…');

    // Esegui e logga ogni step
    const results = await Promise.all(tasks.map(async ([name, p])=>{
      try{
        const r = await p;
        logLoading(`✓ ${name}`);
        return [name, r];
      } catch(e){
        logLoading(`✗ ${name} — ${e?.message || e}`);
        return [name, null];
      }
    }));

    // Index rapido dei risultati
    const R = Object.fromEntries(results);

    // ---- Evidenze Quiet vs Storm → tabella ----
    const evTbody = document.querySelector('#ev-table tbody');
    if (evTbody) {
      const ev = R.summary?.evidence || [];
      evTbody.innerHTML = '';

      const fmt = (v, metr) => {
        if (v === null || v === undefined || Number.isNaN(v)) return '—';
        // Formattazioni leggere per metrica
        if (metr === 'busy_ratio') return (v*100).toFixed(1) + '%';
        if (metr.startsWith('scan_') || metr === 'noise_dbm') return v.toFixed(1) + ' dBm';
        if (metr === 'cn0_mean') return v.toFixed(1) + ' dB-Hz';
        if (metr.endsWith('dop')) return v.toFixed(2);
        if (metr === 'sv_used') return v.toFixed(0);
        if (metr === 'tec') return v.toFixed(0) + ' TECu';
        if (metr === 'mag_norm_ut') return v.toFixed(1) + ' µT';
        if (metr === 't_c') return v.toFixed(1) + ' °C';
        if (metr === 'rh_pct') return v.toFixed(1) + ' %';
        if (metr === 'p_hpa') return v.toFixed(1) + ' hPa';
        return typeof v === 'number' ? v.toFixed(2) : String(v);
      };

      const labelBand = (b) => b ? (b === '24' ? '2.4 GHz' : (b === '58' ? '5.8 GHz' : b)) : 'GPS';
      const labelMetr = (m) => ({
        noise_dbm:'Rumore',
        busy_ratio:'Occupazione',
        scan_p50:'RSSI p50',
        scan_p90:'RSSI p90',
        scan_p10:'RSSI p10',
        hdop:'HDOP', vdop:'VDOP', pdop:'PDOP',
        cn0_mean:'C/N₀',
        sv_used:'SV usati',
        tec:'TEC',
        t_c:'Temperatura',
        rh_pct:'Umidità',
        p_hpa:'Pressione',
        mag_norm_ut:'Magnetometro (µT)'
      }[m] || m);

      ev.forEach(row => {
        const tr = document.createElement('tr');
        const band = labelBand(row.band);
        const metr = labelMetr(row.metric);

        const delta = row.delta;
        const deltaTxt = fmt(delta, row.metric);
        const deltaCell = document.createElement('td');
        deltaCell.textContent = deltaTxt;

        // Colora Δ: peggio se >0 per noise/busy/DOP, meglio se >0 per C/N0/SV_used
        const worseIfHigher = [
          'noise_dbm','busy_ratio','scan_p50','scan_p90','scan_p10',
          'hdop','vdop','pdop','tec',
          // per condizioni avverse spesso il campo magnetico aumenta (µT) → peggio
          'mag_norm_uT'
        ];
        const betterIfHigher = ['cn0_mean','sv_used'];
        let severity = '';
        if (typeof delta === 'number') {
          const mag = Math.abs(delta);
          if (worseIfHigher.includes(row.metric)) {
            severity = delta > 0 ? (mag > 3 ? 'bad' : 'warn') : '';
          } else if (betterIfHigher.includes(row.metric)) {
            severity = delta < 0 ? (mag > 3 ? 'bad' : 'warn') : '';
          }
        }
        if (severity === 'bad')   deltaCell.style.color = '#B00020';
        if (severity === 'warn')  deltaCell.style.color = '#C77700';

        tr.innerHTML = `
          <td>${band}</td>
          <td>${metr}</td>
          <td>${fmt(row.quiet_med, row.metric)}</td>
          <td>${fmt(row.storm_med, row.metric)}</td>
        `;
        tr.appendChild(deltaCell);
        evTbody.appendChild(tr);
      });

      if (ev.length === 0) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td colspan="5"><em>Nessuna evidenza (dati insufficienti in uno dei due regimi).</em></td>`;
        evTbody.appendChild(tr);
      }
    }

    // Badge Kp
    const kpVal = R.summary?.summary?.kplast;
    const kpB = document.getElementById('kp-badge');
    if (kpB){
      const c = colorForKp(Number(kpVal));
      kpB.textContent = `Kp: ${c.label}`;
      kpB.style.background = c.bg; kpB.style.color = c.fg;
    }

    // Badge TEC
    const tecVal = Number(R.latest?.latest?.tec);
    const tecSrc = R.latest?.latest?.tec_source || "—";
    const tecB = document.getElementById('tec-badge');
    if (tecB){
      const c = colorForTEC(tecVal);
      tecB.textContent = Number.isFinite(tecVal) ? `TEC: ${c.label} (${tecSrc})` : `TEC: — (${tecSrc})`;
      tecB.style.background = c.bg; tecB.style.color = c.fg;
    }

    // Badge Posizione
    const lat = R.latest?.latest?.lat, lon = R.latest?.latest?.lon;
    const fix = R.latest?.latest?.gps_fix ?? "—";
    const posB = document.getElementById('pos-badge');
    if (posB){
      posB.textContent = (Number.isFinite(lat) && Number.isFinite(lon))
        ? `Pos: ${lat.toFixed(5)}, ${lon.toFixed(5)} (${fix})`
        : `Pos: — (${fix})`;
    }

    // Glossario (una sola volta)
    const glossary = R.glossary;
    const helpGloss = document.getElementById('help-glossary') || document.getElementById('help-body');
    if (helpGloss && !helpGloss.dataset.filled && glossary?.items) {
      helpGloss.innerHTML = glossary.items.map(item =>
        `<div style="margin:6px 0;">
          <b>${item.label}</b> <code style="color:#667">${item.field}</code><br/>
          <span style="color:#333">${item.desc}</span>
        </div>`
      ).join('');
      helpGloss.dataset.filled = "1";
    }

    // Grafici GPS
    upsertLine('tec',   'TEC',          R.tec?.points  || []);
    upsertLine('hdop',  'HDOP',         R.hdop?.points || []);
    upsertLine('pdop',  'PDOP',         R.pdop?.points || []);
    upsertLine('vdop',  'VDOP',         R.vdop?.points || []);
    upsertLine('cn0',   'C/N0',         R.cn0?.points  || []);
    upsertLine('svused','SV used',      R.sv_used?.points || []);

    // Grafici RF
    upsertLine('noise24', 'noise dBm',     R.noise24?.points || []);
    upsertLine('noise58', 'noise dBm',     R.noise58?.points || []);
    upsertLine('scan24',  'scan p50 RSSI', R.scan24?.points  || []);
    upsertLine('scan58',  'scan p50 RSSI', R.scan58?.points  || []);
    upsertLine('busy24', 'busy ratio', R.busy24?.points || []);
    upsertLine('busy58', 'busy ratio', R.busy58?.points || []);
    upsertLine('kp',      'Kp',            R.kp?.points       || []);

    // Grafici Meteo
    upsertLine('temp',  'Temperatura °C',  R.temp?.points  || []);
    upsertLine('hum',   'Umidità %',       R.hum?.points   || []);
    upsertLine('press', 'Pressione hPa',   R.press?.points || []);
    upsertLine('mag',   'Campo magnetico µT', R.mag?.points || []);

    // Mappa + trail
    ensureMap();
    const coords = (R.track?.points || []).map(p => [p.lat, p.lon]).filter(a => a[0] && a[1]);
    if (coords.length){
      marker.setLatLng(coords.at(-1));
      trail.setLatLngs(coords);
      map.fitBounds(trail.getBounds(), { padding: [20,20] });
    } else if (Number.isFinite(lat) && Number.isFinite(lon)) {
      marker.setLatLng([lat,lon]);
      trail.setLatLngs([[lat,lon]]);
      map.setView([lat,lon], 16);
    }

  } finally {
    hideLoading();
  }
}



// Help panel toggle (unico listener)
document.getElementById('help-btn')?.addEventListener('click', ()=>{
  const el = document.getElementById('help');
  if (!el) return;
  const visible = getComputedStyle(el).display !== 'none';
  el.style.display = visible ? 'none' : 'block';
});

// Chiudi dalla 'X'
document.getElementById('help-close')?.addEventListener('click', () => {
  const el = document.getElementById('help');
  if (el) el.style.display = 'none';
});

// Chiudi con ESC
document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape') {
    const el = document.getElementById('help');
    if (el && getComputedStyle(el).display !== 'none') el.style.display = 'none';
  }
});


refreshAll();
setInterval(refreshAll, 60_000); // refresh ogni minuto