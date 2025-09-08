// dashboard.js

async function fetchJSON(url){ const r=await fetch(url); return await r.json(); }

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
  const minutes = 24*60*3; // ultimi 3 giorni
  const shortM  = 180;     // 3 ore per la traccia

  // Summary + latest + glossary
  const [sum, latest, glossary] = await Promise.all([
    fetchJSON(`/api/summary`),
    fetchJSON(`/api/latest`),
    fetchJSON(`/api/glossary`),
  ]);

  // Badges
  document.getElementById('kp-badge').textContent  = `Kp: ${sum?.summary?.kplast ?? "—"}`;
  document.getElementById('tec-badge').textContent = `TEC: ${latest?.latest?.tec ?? "—"} (${latest?.latest?.tec_source || "—"})`;
  const lat = latest?.latest?.lat, lon = latest?.latest?.lon;
  const fix = latest?.latest?.gps_fix ?? "—";
  document.getElementById('pos-badge').textContent = (lat && lon)
      ? `Pos: ${lat.toFixed(5)}, ${lon.toFixed(5)} (${fix})`
      : `Pos: — (${fix})`;

  // Help panel fill (lazy, only once)
  const helpBody = document.getElementById('help-body');
  if (helpBody && !helpBody.dataset.filled) {
    helpBody.innerHTML = (glossary.items || []).map(item =>
      `<div style="margin:6px 0;">
         <b>${item.label}</b> <code style="color:#667">${item.field}</code><br/>
         <span style="color:#333">${item.desc}</span>
       </div>`
    ).join('');
    helpBody.dataset.filled = "1";
  }

  // Charts: TEC + GPS
  const [tec, hdop, pdop, vdop, cn0, svu] = await Promise.all([
    fetchJSON(`/api/series_gps?metric=tec&minutes=${minutes}&agg=median&window=5min`),
    fetchJSON(`/api/series_gps?metric=hdop&minutes=${minutes}&agg=median&window=5min`),
    fetchJSON(`/api/series_gps?metric=pdop&minutes=${minutes}&agg=median&window=5min`),
    fetchJSON(`/api/series_gps?metric=vdop&minutes=${minutes}&agg=median&window=5min`),
    fetchJSON(`/api/series_gps?metric=cn0_mean&minutes=${minutes}&agg=median&window=5min`),
    fetchJSON(`/api/series_gps?metric=sv_used&minutes=${minutes}&agg=median&window=5min`),
  ]);

  upsertLine('tec',   'TEC', tec.points || []);
  upsertLine('hdop',  'HDOP', hdop.points || []);
  upsertLine('pdop',  'PDOP', pdop.points || []);
  upsertLine('vdop',  'VDOP', vdop.points || []);
  upsertLine('cn0',   'C/N0', cn0.points || []);
  upsertLine('svused','SV used', svu.points || []);

  // Charts: RF
  const [n24, n58, s24, s58, kp] = await Promise.all([
    fetchJSON(`/api/series?metric=noise_dbm&band=24&minutes=${minutes}&agg=median&window=5min`),
    fetchJSON(`/api/series?metric=noise_dbm&band=58&minutes=${minutes}&agg=median&window=5min`),
    fetchJSON(`/api/series?metric=scan_p50&band=24&minutes=${minutes}&agg=median&window=5min`),
    fetchJSON(`/api/series?metric=scan_p50&band=58&minutes=${minutes}&agg=median&window=5min`),
    fetchJSON(`/api/series?metric=kp&minutes=${minutes}`),
  ]);

  upsertLine('noise24', 'noise dBm',     n24.points || []);
  upsertLine('noise58', 'noise dBm',     n58.points || []);
  upsertLine('scan24',  'scan p50 RSSI', s24.points || []);
  upsertLine('scan58',  'scan p50 RSSI', s58.points || []);
  upsertLine('kp',      'Kp',            kp.points  || []);

  // Map + trail
  ensureMap();
  const track = await fetchJSON(`/api/gps_track?minutes=${shortM}`);
  const coords = (track.points || []).map(p => [p.lat, p.lon]).filter(a => a[0] && a[1]);
  if (coords.length){
    marker.setLatLng(coords[coords.length-1]);
    trail.setLatLngs(coords);
    map.fitBounds(trail.getBounds(), { padding: [20,20] });
  } else if (lat && lon) {
    marker.setLatLng([lat,lon]);
    trail.setLatLngs([[lat,lon]]);
    map.setView([lat,lon], 16);
  }
}

// Help panel toggle
document.getElementById('help-btn')?.addEventListener('click', ()=>{
  const el = document.getElementById('help');
  if (!el) return;
  el.style.display = (el.style.display === 'none' || !el.style.display) ? 'block' : 'none';
});

refreshAll();
setInterval(refreshAll, 60_000); // refresh ogni minuto