// dashboard.js

let currentDay = null; // string "YYYY-MM-DD" oppure null per "finestra scorrevole"
const dayPicker = document.getElementById('dayPicker');
const prevDayBtn = document.getElementById('prevDayBtn');
const nextDayBtn = document.getElementById('nextDayBtn');
const dayLabel   = document.getElementById('dayLabel');

function colorForKp(kp){
  if (!Number.isFinite(kp)) return {bg:'#eef6ff', fg:'#111', label:'—'};
  // Mappa richiesta:
  // Kp < 5 → Verde
  // Kp = 5 (G1) → Giallo
  // Kp = 6 (G2) → Arancio chiaro
  // Kp = 7 (G3) → Arancione
  // Kp = 8, 9- (G4) → Rosso chiaro
  // Kp = 9o (G5) → Rosso (interpreto 9.0 pieno)
  if (kp < 5)           return {bg:'#C7F2C8', fg:'#0B3D0B', label:`${kp}`};       // verde
  if (kp === 5)         return {bg:'#FFF3B0', fg:'#5C4800', label:`${kp} (G1)`};  // giallo
  if (kp === 6)         return {bg:'#FFD8A8', fg:'#5A3A00', label:`${kp} (G2)`};  // arancio chiaro
  if (kp === 7)         return {bg:'#FFC078', fg:'#5A2A00', label:`${kp} (G3)`};  // arancione
  if (kp >= 8 && kp < 9)return {bg:'#FFA8A8', fg:'#5A0B0B', label:`${kp} (G4)`};  // rosso chiaro
  if (kp >= 9)          return {bg:'#FF6B6B', fg:'#fff',    label:`${kp} (G5)`};  // rosso pieno
  return {bg:'#eef6ff', fg:'#111', label:`${kp}`};
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

function setDay(dStr){ // dStr può essere null (modalità "live")
  currentDay = dStr;
  if (dayPicker) dayPicker.value = dStr || "";
  if (dayLabel){
    dayLabel.textContent = dStr ? `Giorno selezionato: ${dStr}` : "In tempo reale (ultima finestra)";
  }
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
  const minutesParam = currentDay ? 1440 : 4320; // 1 giorno se selezionato, 3 giorni se live
  const shortM       = currentDay ? 1440 : 180;  // per la traccia GPS
  const agg          = currentDay ? "median" : "";
  const win          = currentDay ? "5min"  : "";

  const [
    summary, latest, glossary,
    tecSeries, hdopSeries, pdopSeries, vdopSeries, cn0Series, svuSeries,
    noise24Series, noise58Series, scan24Series, scan58Series, kpSeries,
    track
  ] = await Promise.all([
    loadSummary(),
    fetchJSON('/api/latest'),
    fetchJSON('/api/glossary'),

    loadSeriesGps("tec",      { agg, window: win, minutes: minutesParam }),
    loadSeriesGps("hdop",     { agg, window: win, minutes: minutesParam }),
    loadSeriesGps("pdop",     { agg, window: win, minutes: minutesParam }),
    loadSeriesGps("vdop",     { agg, window: win, minutes: minutesParam }),
    loadSeriesGps("cn0_mean", { agg, window: win, minutes: minutesParam }),
    loadSeriesGps("sv_used",  { agg, window: win, minutes: minutesParam }),

    loadSeries("noise_dbm", { band:"24", agg, window: win, minutes: minutesParam }),
    loadSeries("noise_dbm", { band:"58", agg, window: win, minutes: minutesParam }),
    loadSeries("scan_p50",  { band:"24", agg, window: win, minutes: minutesParam }),
    loadSeries("scan_p50",  { band:"58", agg, window: win, minutes: minutesParam }),
    loadSeries("kp",        { minutes: minutesParam }),

    loadGpsTrack(shortM)
  ]);

  // Badge
  // Badge Kp
  const kpVal = summary?.summary?.kplast;
  const kpB = document.getElementById('kp-badge');
  if (kpB){
    const c = colorForKp(Number(kpVal));
    kpB.textContent = `Kp: ${c.label}`;
    kpB.style.background = c.bg;
    kpB.style.color = c.fg;
  }

  // Badge TEC
  const tecVal = Number(latest?.latest?.tec);
  const tecSrc = latest?.latest?.tec_source || "—";
  const tecB = document.getElementById('tec-badge');
  if (tecB){
    const c = colorForTEC(tecVal);
    tecB.textContent = Number.isFinite(tecVal) ? `TEC: ${c.label} (${tecSrc})` : `TEC: — (${tecSrc})`;
    tecB.style.background = c.bg;
    tecB.style.color = c.fg;
  }

  // Badge Posizione
  const lat = latest?.latest?.lat, lon = latest?.latest?.lon;
  const fix = latest?.latest?.gps_fix ?? "—";
  const hasPos = Number.isFinite(lat) && Number.isFinite(lon);
  const posB = document.getElementById('pos-badge');
  if (posB){
    posB.textContent = hasPos
      ? `Pos: ${lat.toFixed(5)}, ${lon.toFixed(5)} (${fix})`
      : `Pos: — (${fix})`;
  }



  // Help panel (riempi una sola volta il GLOSSARIO, senza toccare i badge)
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
  upsertLine('tec',   'TEC',          tecSeries?.points  || []);
  upsertLine('hdop',  'HDOP',         hdopSeries?.points || []);
  upsertLine('pdop',  'PDOP',         pdopSeries?.points || []);
  upsertLine('vdop',  'VDOP',         vdopSeries?.points || []);
  upsertLine('cn0',   'C/N0',         cn0Series?.points  || []);
  upsertLine('svused','SV used',      svuSeries?.points  || []);

  // Grafici RF
  upsertLine('noise24', 'noise dBm',     noise24Series?.points || []);
  upsertLine('noise58', 'noise dBm',     noise58Series?.points || []);
  upsertLine('scan24',  'scan p50 RSSI', scan24Series?.points  || []);
  upsertLine('scan58',  'scan p50 RSSI', scan58Series?.points  || []);
  upsertLine('kp',      'Kp',            kpSeries?.points       || []);

  // Mappa + trail
  ensureMap();
  const coords = (track?.points || []).map(p => [p.lat, p.lon]).filter(a => a[0] && a[1]);
  if (coords.length){
    marker.setLatLng(coords.at(-1));
    trail.setLatLngs(coords);
    map.fitBounds(trail.getBounds(), { padding: [20,20] });
  } else if (lat && lon) {
    marker.setLatLng([lat,lon]);
    trail.setLatLngs([[lat,lon]]);
    map.setView([lat,lon], 16);
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