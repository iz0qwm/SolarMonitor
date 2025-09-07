// dashboard.js

async function fetchJSON(url){ const r=await fetch(url); return await r.json(); }

// cache grafici
const charts = {};

function upsertLine(canvasId, label, points){
  const ctx = document.getElementById(canvasId).getContext('2d');
  const dataPoints = (points || []).map(([t,v]) => ({ x: new Date(t), y: v }));

  if (charts[canvasId]) {
    charts[canvasId].data.datasets[0].data = dataPoints;
    charts[canvasId].data.datasets[0].label = label;
    charts[canvasId].update();
    return charts[canvasId];
  }

  charts[canvasId] = new Chart(ctx, {
    type: 'line',
    data: {
      datasets: [{
        label,
        data: dataPoints,
        pointRadius: 0,
        borderWidth: 1.5,
        tension: 0.2
      }]
    },
    options: {
      parsing: false,
      scales: {
        x: { type: 'time', time: { unit: 'hour' } },
        y: { beginAtZero: false }
      },
      plugins: { legend: { display: false } },
      animation: false
    }
  });
  return charts[canvasId];
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
    fetchJSON(`/api/series_gps?metric=tec&minutes=${minutes}`),
    fetchJSON(`/api/series_gps?metric=hdop&minutes=${minutes}`),
    fetchJSON(`/api/series_gps?metric=pdop&minutes=${minutes}`),
    fetchJSON(`/api/series_gps?metric=vdop&minutes=${minutes}`),
    fetchJSON(`/api/series_gps?metric=cn0_mean&minutes=${minutes}`),
    fetchJSON(`/api/series_gps?metric=sv_used&minutes=${minutes}`),
  ]);

  upsertLine('tec',   'TEC', tec.points || []);
  upsertLine('hdop',  'HDOP', hdop.points || []);
  upsertLine('pdop',  'PDOP', pdop.points || []);
  upsertLine('vdop',  'VDOP', vdop.points || []);
  upsertLine('cn0',   'C/N0', cn0.points || []);
  upsertLine('svused','SV used', svu.points || []);

  // Charts: RF
  const [n24, n58, s24, s58, kp] = await Promise.all([
    fetchJSON(`/api/series?metric=noise_dbm&band=24&minutes=${minutes}`),
    fetchJSON(`/api/series?metric=noise_dbm&band=58&minutes=${minutes}`),
    fetchJSON(`/api/series?metric=scan_p50&band=24&minutes=${minutes}`),
    fetchJSON(`/api/series?metric=scan_p50&band=58&minutes=${minutes}`),
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