#!/usr/bin/env python3
import csv, os, time, json, subprocess, urllib.request
from datetime import datetime, timezone, timedelta
from gps3 import gps3
import math
from collections import deque, defaultdict  # se già non presenti
from urllib.parse import quote  # in testa, vicino agli import
from bisect import bisect_right

# Endpoint INGV (puoi sovrascriverlo via env se cambia)
TEC_INGV_URL_TEMPLATE = os.environ.get(
    "TEC_INGV_URL_TEMPLATE",
    #"http://ws-eswua.rm.ingv.it/tecdb.php/records/wsnc_med?filter=dt,eq,{dt}"
    "http://ws-eswua.rm.ingv.it/tecdb.php/records/wsnc_eu?filter=dt,eq,{dt}"
)

LOGDIR = os.path.expanduser("~/spacewx_logs"); os.makedirs(LOGDIR, exist_ok=True)
CSV = os.path.join(LOGDIR, "wifi_gps_kp_qos.csv")
KP_CACHE = os.path.join(LOGDIR, ".kp_cache.json")

GPSD_HOST = os.environ.get("GPSD_HOST","127.0.0.1")
GPSD_PORT = int(os.environ.get("GPSD_PORT","2947"))
WLAN = os.environ.get("WLAN_IF","wlan1")
KP_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"

def now_iso(): return datetime.now(timezone.utc).isoformat()



def floor_to_10min(dt_utc):
    m = (dt_utc.minute // 10) * 10
    return dt_utc.replace(minute=m, second=0, microsecond=0)

def fmt_slot(dt_utc):
    return dt_utc.strftime("%Y-%m-%d %H:%M:%S")


_INGV_TRIES = int(os.environ.get("TEC_INGV_TRIES", "3"))  # slot da provare: t-0, t-10, t-20...
_ingv_cache = {}  # rimane

def _fetch_one_slot(dt_str):
    # cache per singolo slot
    if dt_str in _ingv_cache:
        return _ingv_cache[dt_str]

    url = TEC_INGV_URL_TEMPLATE.format(dt=quote(dt_str))
    # log URL interrogato
    print(f"[TEC] GET {url}")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "spacewx-logger/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            payload = json.loads(r.read().decode())
    except Exception as e:
        print(f"[TEC] ERROR fetch {dt_str}: {e}")
        return None

    recs = payload.get("records") or []
    print(f"[TEC] slot {dt_str} → records={len(recs)}")

    if not recs:
        return None

    jfile = recs[0].get("jfile")
    if not jfile:
        print(f"[TEC] slot {dt_str} has empty jfile")
        return None

    try:
        points = json.loads(jfile)
    except Exception as e:
        print(f"[TEC] JSON error in jfile: {e}")
        return None

    grid = {}
    lats = set()
    lons = set()
    for p in points:
        try:
            la = round(float(p["lat"]), 2)
            lo = round(float(p["lon"]), 2)
            tec = float(p["tec"])
        except Exception:
            continue
        grid[(la, lo)] = tec
        lats.add(la); lons.add(lo)

    if not grid:
        print(f"[TEC] slot {dt_str} parsed but grid is empty")
        return None

    obj = {"grid": grid, "lats": sorted(lats), "lons": sorted(lons)}

    def _approx_step(vals):
        if len(vals) < 2: return None
        diffs = [round(vals[i+1] - vals[i], 6) for i in range(len(vals)-1)]
        diffs = [d for d in diffs if d > 0]
        diffs.sort()
        return diffs[len(diffs)//2] if diffs else None

    la0, la1 = obj["lats"][0], obj["lats"][-1]
    lo0, lo1 = obj["lons"][0], obj["lons"][-1]
    step_lat = _approx_step(obj["lats"])
    step_lon = _approx_step(obj["lons"])
    print(f"[TEC] grid lat[{la0}..{la1}] lon[{lo0}..{lo1}] step≈{step_lat}°×{step_lon}° (n={len(obj['lats'])}x{len(obj['lons'])})")

    _ingv_cache[dt_str] = obj

    # log bounds e step
    la0, la1 = obj["lats"][0], obj["lats"][-1]
    lo0, lo1 = obj["lons"][0], obj["lons"][-1]
    print(f"[TEC] grid lat[{la0}..{la1}] lon[{lo0}..{lo1}] step≈0.1° (n={len(obj['lats'])}x{len(obj['lons'])})")
    return obj

def fetch_ingv_grid_multi(dt_utc):
    # prova lo slot corrente (floored), poi indietro di 10 e 20 minuti
    tried = 0
    dt_try = floor_to_10min(dt_utc)
    while tried < _INGV_TRIES:
        dt_str = fmt_slot(dt_try)
        obj = _fetch_one_slot(dt_str)
        if obj:
            return obj, dt_str
        # fallback di 10 minuti
        dt_try = dt_try - timedelta(minutes=10)
        tried += 1
    return None, None

def bilinear_tec(grid_obj, lat, lon):
    if not grid_obj or lat is None or lon is None:
        return None

    lats = grid_obj["lats"]
    lons = grid_obj["lons"]
    grid = grid_obj["grid"]

    # fuori dai bounds
    if not (lats[0] <= lat <= lats[-1] and lons[0] <= lon <= lons[-1]):
        print(f"[TEC] point lat={lat:.6f} lon={lon:.6f} OUTSIDE grid bounds")
        return None

    # trova gli indici inferiori (i,j) tali che lats[i] <= lat < lats[i+1]
    i = bisect_right(lats, lat) - 1
    j = bisect_right(lons, lon) - 1
    # clamp agli estremi
    if i < 0: i = 0
    if i >= len(lats)-1: i = len(lats)-2
    if j < 0: j = 0
    if j >= len(lons)-1: j = len(lons)-2

    lat0, lat1 = lats[i], lats[i+1]
    lon0, lon1 = lons[j], lons[j+1]

    # prova i 4 vicini
    q = {}
    for (la, lo) in ((lat0,lon0),(lat1,lon0),(lat0,lon1),(lat1,lon1)):
        if (round(la,2), round(lo,2)) in grid:
            q[(la,lo)] = grid[(round(la,2), round(lo,2))]

    if len(q) == 4:
        print(f"[TEC] bilinear neighbors: ({lat0},{lon0})={q[(lat0,lon0)]}  "
              f"({lat1},{lon0})={q[(lat1,lon0)]}  "
              f"({lat0},{lon1})={q[(lat0,lon1)]}  "
              f"({lat1},{lon1})={q[(lat1,lon1)]}")
        tx = 0.0 if lat1 == lat0 else (lat - lat0) / (lat1 - lat0)
        ty = 0.0 if lon1 == lon0 else (lon - lon0) / (lon1 - lon0)
        tec = (q[(lat0,lon0)]*(1-tx)*(1-ty) +
               q[(lat1,lon0)]*tx*(1-ty) +
               q[(lat0,lon1)]*(1-tx)*ty +
               q[(lat1,lon1)]*tx*ty)
        return round(tec, 2)

    # fallback: se manca qualcosa, usa il nearest neighbor tra i 4 previsti (o tra tutti se serve)
    candidates = []
    # prima prova i 4 "ideali"
    for (la, lo) in ((lat0,lon0),(lat1,lon0),(lat0,lon1),(lat1,lon1)):
        key = (round(la,2), round(lo,2))
        if key in grid:
            d2 = (la - lat)**2 + (lo - lon)**2
            candidates.append((d2, la, lo, grid[key]))

    # se nessuno dei 4 c’è, scegli NN su tutta la griglia (è raro, ma robusto)
    if not candidates:
        for (la, lo), val in grid.items():
            d2 = (la - lat)**2 + (lo - lon)**2
            candidates.append((d2, la, lo, val))

    candidates.sort(key=lambda x: x[0])
    _, la, lo, val = candidates[0]
    print(f"[TEC] NN fallback → ({la},{lo}) tec={val}")
    return round(val, 2)



def get_tec_for(lat, lon, ts_iso):
    if lat is None or lon is None or not ts_iso:
        return (None, None)
    try:
        dt = datetime.fromisoformat(ts_iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        dt = datetime.now(timezone.utc)

    print(f"[TEC] request lat={float(lat):.6f} lon={float(lon):.6f} at {fmt_slot(dt)}Z")
    obj, dt_str = fetch_ingv_grid_multi(dt)
    if not obj:
        print(f"[TEC] no grid available for {fmt_slot(floor_to_10min(dt))}Z (tried {_INGV_TRIES} slots back)")
        return (None, None)

    tec = bilinear_tec(obj, round(float(lat), 6), round(float(lon), 6))
    if tec is None:
        return (None, None)

    return (tec, f"ingv-wsnc_med@{dt_str}")


# FIX: Kp caching + resilienza
def load_kp_cache():
    try:
        with open(KP_CACHE,"r") as f: return json.load(f)
    except Exception:
        return {"kp": None, "when": None, "ts": None}

def save_kp_cache(kp, when):
    try:
        with open(KP_CACHE,"w") as f:
            json.dump({"kp": kp, "when": when, "ts": now_iso()}, f)
    except Exception:
        pass

def get_kp():
    try:
        req = urllib.request.Request(KP_URL, headers={"User-Agent":"spacewx-logger/1.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data=json.loads(r.read().decode())
        last=data[-1]
        kp = float(last[1]); when = last[0]
        save_kp_cache(kp, when)
        return kp, when
    except Exception:
        cache = load_kp_cache()
        return cache.get("kp"), cache.get("when")

def run(cmd, timeout=8):
    return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=timeout).decode(errors="ignore")

def survey_sample(wlan):
    try:
        out = run(["/sbin/iw","dev",wlan,"survey","dump"])
    except Exception:
        return None
    freq=noise=active=busy=None
    for L in out.splitlines():
        L=L.strip()
        if L.startswith("frequency:"):
            freq=int(L.split()[1])
        elif "noise:" in L:
            try: noise=int(L.split()[-2])
            except: noise=None
        elif "channel active time:" in L:
            try: active=int(L.split()[-2])
            except: active=None
        elif "channel busy time:" in L:
            try: busy=int(L.split()[-2])
            except: busy=None
    if freq:
        busy_ratio = (busy/active) if (busy and active and active>0) else None
        return dict(freq=freq, noise_dbm=noise, busy_ratio=busy_ratio)
    return None

def scan_stats(wlan):
    try:
        out = run(["/sbin/iw","dev",wlan,"scan"])
    except Exception:
        return []
    stats = {}  # freq -> [RSSI...]
    curf=None
    for line in out.splitlines():
        L=line.strip()
        if L.startswith("freq:"):
            curf=int(L.split()[1]); stats.setdefault(curf, [])
        elif L.startswith("signal:") and curf:
            try: stats[curf].append(float(L.split()[1]))
            except: pass
    rows=[]
    for f, arr in stats.items():
        arr=sorted([x for x in arr if x is not None])
        if not arr:
            rows.append(dict(freq=f, n=0, p50=None, p10=None, p90=None))
            continue
        def pct(p):
            i=int((p/100)*(len(arr)-1)); return arr[i]
        rows.append(dict(freq=f, n=len(arr), p50=pct(50), p10=pct(10), p90=pct(90)))
    return rows

def band_of(freq):
    if not freq: return "?"
    if 2400 <= freq <= 2500: return "24"
    if 5150 <= freq <= 5950: return "58"
    return "?"

def main():
    newfile = not os.path.exists(CSV)
    with open(CSV, "a", newline="") as f:
        w=csv.writer(f)
        if newfile:
            w.writerow(["ts_iso","kp","kp_when",
                        "gps_fix","lat","lon","alt","pdop","hdop","vdop","sv_used","sv_tot","cn0_mean",
                        "mode","freq","noise_dbm","busy_ratio","scan_n","scan_p50","scan_p10","scan_p90","band",
                        "tec","tec_source"])
        # gpsd
        gps_socket = gps3.GPSDSocket()
        data_stream = gps3.DataStream()
        gps_socket.connect(GPSD_HOST, GPSD_PORT)
        gps_socket.watch()

        kp=kp_when=None; last_kp=0
        last_sky = dict(pdop=None, hdop=None, vdop=None, sv_used=None, sv_tot=None, cn0_mean=None)

        while True:
            now=time.time()
            # FIX: refresh Kp ogni 5 minuti ma con cache di fallback
            if now-last_kp > 300:
                kp, kp_when = get_kp(); last_kp = now

            # FIX: raccogli TPV e SKY per ~1.2s per evitare "buchi"
            gps_fix="NO"; lat=lon=alt=None
            got_tpv=False; got_sky=False
            t_end = now + 1.2
            while time.time() < t_end:
                try:
                    raw = next(gps_socket)
                except StopIteration:
                    break
                if not raw:
                    continue
                data_stream.unpack(raw)

                # TPV (posizione)
                if data_stream.TPV:
                    tpv = data_stream.TPV
                    if isinstance(tpv, str):
                        try: tpv = json.loads(tpv)
                        except Exception: tpv = {}
                    mode = tpv.get('mode')
                    lat  = tpv.get('lat')
                    lon  = tpv.get('lon')
                    alt  = tpv.get('alt')
                    gps_fix = "3D" if mode == 3 else ("2D" if mode == 2 else "NO")
                    got_tpv=True

                # SKY (sats/DOP)
                if data_stream.SKY:
                    sky = data_stream.SKY
                    if isinstance(sky, str):
                        try: sky = json.loads(sky)
                        except Exception: sky = {}

                    pdop = sky.get('pdop')
                    hdop = sky.get('hdop')
                    vdop = sky.get('vdop')

                    sats = sky.get('satellites') or []
                    norm_sats = []
                    if isinstance(sats, list):
                        for s in sats:
                            if isinstance(s, str):
                                try: s = json.loads(s)
                                except Exception: s = None
                            if isinstance(s, dict): norm_sats.append(s)

                    sv_tot  = len(norm_sats)
                    sv_used = sum(1 for s in norm_sats if s.get('used') in (True, 1, 'true', 'True'))

                    cn_vals = []
                    for s in norm_sats:
                        v = s.get('ss') or s.get('cn0') or s.get('cn') or s.get('snr')
                        if v is None: continue
                        try: cn_vals.append(float(v))
                        except Exception: pass

                    cn0_mean = round(sum(cn_vals)/len(cn_vals), 1) if cn_vals else None

                    last_sky.update(dict(
                        pdop=pdop, hdop=hdop, vdop=vdop,
                        sv_used=sv_used, sv_tot=sv_tot, cn0_mean=cn0_mean
                    ))
                    got_sky=True

            # Prendiamo i dati TEC
            ts = now_iso()
            tec_val, tec_src = get_tec_for(lat, lon, ts)
            print(f"[TEC] value={tec_val} source={tec_src}")

            # SURVEY: se supportato
            surv = survey_sample(WLAN)
            if surv:
                w.writerow([ts, kp, kp_when,
                            gps_fix, lat, lon, alt,
                            last_sky["pdop"], last_sky["hdop"], last_sky["vdop"],
                            last_sky["sv_used"], last_sky["sv_tot"], last_sky["cn0_mean"],
                            "SURVEY", surv["freq"], surv["noise_dbm"], surv["busy_ratio"],
                            None, None, None, None, band_of(surv["freq"]),
                            tec_val, tec_src])
                f.flush()

            # SCAN a banda larga
            for row in scan_stats(WLAN):
                w.writerow([ts, kp, kp_when,
                            gps_fix, lat, lon, alt,
                            last_sky["pdop"], last_sky["hdop"], last_sky["vdop"],
                            last_sky["sv_used"], last_sky["sv_tot"], last_sky["cn0_mean"],
                            "SCAN", row["freq"], None, None,
                            row["n"], row["p50"], row["p10"], row["p90"], band_of(row["freq"]),
                            tec_val, tec_src])
            f.flush()

            time.sleep(60)

if __name__ == "__main__":
    main()
