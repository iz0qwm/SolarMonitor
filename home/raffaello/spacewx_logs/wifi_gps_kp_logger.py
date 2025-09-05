#!/usr/bin/env python3
import csv, os, time, json, subprocess, urllib.request
from datetime import datetime, timezone
from gps3 import gps3

LOGDIR = os.path.expanduser("~/spacewx_logs"); os.makedirs(LOGDIR, exist_ok=True)
CSV = os.path.join(LOGDIR, "wifi_gps_kp_qos.csv")

GPSD_HOST = os.environ.get("GPSD_HOST","127.0.0.1")
GPSD_PORT = int(os.environ.get("GPSD_PORT","2947"))
WLAN = os.environ.get("WLAN_IF","wlan1")
KP_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"

def now_iso(): return datetime.now(timezone.utc).isoformat()

def get_kp():
    try:
        with urllib.request.urlopen(KP_URL, timeout=10) as r:
            data=json.loads(r.read().decode())
        last=data[-1]; return float(last[1]), last[0]
    except Exception:
        return None, None

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
    # scan banda intera (può richiedere qualche secondo)
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
            if not arr: return None
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
                        "mode","freq","noise_dbm","busy_ratio","scan_n","scan_p50","scan_p10","scan_p90","band"])
        # gpsd remoto
        gps_socket = gps3.GPSDSocket(host=GPSD_HOST, port=GPSD_PORT)
        data_stream = gps3.DataStream()
        gps_socket.connect(); gps_socket.watch(json=True)
        kp=kp_when=None; last_kp=0
        last_sky = dict(pdop=None, hdop=None, vdop=None, sv_used=None, sv_tot=None, cn0_mean=None)
        while True:
            now=time.time()
            if now-last_kp > 300:
                kp, kp_when = get_kp(); last_kp = now
            # leggi gpsd (grab pochi messaggi ogni giro)
            gps_fix="NO"; lat=lon=alt=None
            for _ in range(3):
                try:
                    raw = next(gps_socket)
                except StopIteration:
                    break
                if not raw: break
                data_stream.unpack(raw)
                if data_stream.TPV:
                    mode = data_stream.TPV.get('mode')
                    lat  = data_stream.TPV.get('lat'); lon = data_stream.TPV.get('lon'); alt = data_stream.TPV.get('alt')
                    gps_fix = "3D" if mode==3 else ("2D" if mode==2 else "NO")
                if data_stream.SKY:
                    pdop = data_stream.SKY.get('pdop'); hdop=data_stream.SKY.get('hdop'); vdop=data_stream.SKY.get('vdop')
                    sats = data_stream.SKY.get('satellites') or []
                    sv_tot=len(sats); sv_used=len([s for s in sats if s.get('used')])
                    cn = [s.get('ss') for s in sats if s.get('used') and s.get('ss') is not None]
                    cn0_mean = round(sum(cn)/len(cn),1) if cn else None
                    last_sky.update(dict(pdop=pdop,hdop=hdop,vdop=vdop,sv_used=sv_used,sv_tot=sv_tot,cn0_mean=cn0_mean))
            # Wi-Fi: prova SURVEY sul canale corrente
            surv = survey_sample(WLAN)
            if surv:
                w.writerow([now_iso(), kp, kp_when,
                            gps_fix, lat, lon, alt,
                            last_sky["pdop"], last_sky["hdop"], last_sky["vdop"],
                            last_sky["sv_used"], last_sky["sv_tot"], last_sky["cn0_mean"],
                            "SURVEY", surv["freq"], surv["noise_dbm"], surv["busy_ratio"],
                            None, None, None, None, band_of(surv["freq"])])
                f.flush()
            # Poi fai uno scan a banda larga (statistiche per molti canali)
            for row in scan_stats(WLAN):
                w.writerow([now_iso(), kp, kp_when,
                            gps_fix, lat, lon, alt,
                            last_sky["pdop"], last_sky["hdop"], last_sky["vdop"],
                            last_sky["sv_used"], last_sky["sv_tot"], last_sky["cn0_mean"],
                            "SCAN", row["freq"], None, None,
                            row["n"], row["p50"], row["p10"], row["p90"], band_of(row["freq"])])
            f.flush()
            time.sleep(60)

if __name__ == "__main__":
    main()

