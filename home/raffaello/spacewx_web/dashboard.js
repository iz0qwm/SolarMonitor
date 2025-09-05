async function fetchJSON(url){ const r=await fetch(url); return await r.json(); }

function makeLine(ctx, label, points){
  return new Chart(ctx, {
    type: 'line',
    data: {
      datasets: [{
        label, data: points.map(([t,v])=>({x:new Date(t), y:v})),
        pointRadius: 0, borderWidth: 1.5, tension: 0.2
      }]
    },
    options: {
      parsing:false,
      scales:{ x:{type:'time', time:{unit:'hour'}}, y:{beginAtZero:false}},
      plugins:{ legend:{display:false}}
    }
  });
}

async function init(){
  const minutes = 24*60*3; // ultimi 3 giorni

  const [s24, s58, b24, b58, p24, p58, kp, sum] = await Promise.all([
    fetchJSON(`/api/series?metric=noise_dbm&band=24&minutes=${minutes}`),
    fetchJSON(`/api/series?metric=noise_dbm&band=58&minutes=${minutes}`),
    fetchJSON(`/api/series?metric=busy_ratio&band=24&minutes=${minutes}`),
    fetchJSON(`/api/series?metric=busy_ratio&band=58&minutes=${minutes}`),
    fetchJSON(`/api/series?metric=scan_p50&band=24&minutes=${minutes}`),
    fetchJSON(`/api/series?metric=scan_p50&band=58&minutes=${minutes}`),
    fetchJSON(`/api/series?metric=kp&minutes=${minutes}`),
    fetchJSON(`/api/summary`)
  ]);

  document.getElementById('kp-badge').textContent = `Kp: ${sum?.summary?.kplast ?? "—"}`;
  document.getElementById('rows-badge').textContent = `rows: ${sum?.summary?.rows_total ?? "—"}`;

  makeLine(document.getElementById('noise24'), 'noise dBm', s24.points || []);
  makeLine(document.getElementById('noise58'), 'noise dBm', s58.points || []);
  makeLine(document.getElementById('busy24'), 'busy ratio', b24.points || []);
  makeLine(document.getElementById('busy58'), 'busy ratio', b58.points || []);
  makeLine(document.getElementById('scan24'), 'scan p50 RSSI', p24.points || []);
  makeLine(document.getElementById('scan58'), 'scan p50 RSSI', p58.points || []);
  makeLine(document.getElementById('kp'), 'Kp', kp.points || []);

  const tbody = document.querySelector('#ev-table tbody');
  (sum.evidence || []).forEach(ev=>{
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${ev.band}</td><td>${ev.metric}</td>
                    <td>${ev.quiet_med?.toFixed?.(2) ?? '—'}</td>
                    <td>${ev.storm_med?.toFixed?.(2) ?? '—'}</td>
                    <td>${(ev.delta>=0?'+':'')}${ev.delta?.toFixed?.(2) ?? '—'}</td>`;
    tbody.appendChild(tr);
  });
}

init();
setInterval(init, 60_000); // refresh ogni minuto

