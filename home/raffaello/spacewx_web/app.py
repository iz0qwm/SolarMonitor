#!/usr/bin/env python3
import os, math, json
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, render_template, request
import pandas as pd
from dateutil import parser as dtp

CSV_PATH = os.environ.get("CSV_PATH", "/home/pi/spacewx_logs/wifi_gps_kp_qos.csv")
TITLE = os.environ.get("TITLE", "Space Weather QoS")

app = Flask(__name__)

# ---- Helpers ----
def load_df(max_rows=200000):
    # Legge solo la coda per restare leggero
    try:
        df = pd.read_csv(CSV_PATH)
    except Exception:
        return pd.DataFrame()
    if len(df) > max_rows:
        df = df.tail(max_rows)
    # parsing tempo
    if "ts_iso" in df.columns:
        df["ts"] = pd.to_datetime(df["ts_iso"], utc=True, errors="coerce")
    else:
        df["ts"] = pd.NaT
    # banda come string
    if "band" in df.columns:
        df["band"] = df["band"].astype(str)
    return df

def kp_bin(kp):
    if pd.isna(kp): return None
    try:
        if kp < 3: return "quiet(≤3)"
        if kp < 5: return "active(3–4)"
        if kp < 6: return "storm(5)"
        if kp < 7: return "storm(6)"
        return "strong(≥7)"
    except Exception:
        return None

def safe_float(x):
    try: return float(x)
    except: return None

# ---- Routes ----
@app.route("/")
def index():
    return render_template("index.html", title=TITLE)

@app.route("/api/series")
def api_series():
    """
    /api/series?metric=noise_dbm&band=24&minutes=4320
    metric: noise_dbm | busy_ratio | scan_p50 | scan_n | kp
    band: "24" | "58" | (omit per tutte, ma per kp non serve)
    """
    metric = request.args.get("metric", "noise_dbm")
    band = request.args.get("band")
    minutes = int(request.args.get("minutes", "4320"))  # default: 3 giorni
    df = load_df()
    if df.empty:
        return jsonify({"ok": True, "points": []})

    # filtro tempo
    cutoff = pd.Timestamp.utcnow().replace(tzinfo=timezone.utc) - pd.Timedelta(minutes=minutes)
    df = df[df["ts"] >= cutoff]

    # scegli colonna
    colmap = {
        "noise_dbm": "noise_dbm",
        "busy_ratio": "busy_ratio",
        "scan_p50": "scan_p50",
        "scan_n": "scan_n",
        "kp": "kp"
    }
    col = colmap.get(metric)
    if not col or col not in df.columns:
        return jsonify({"ok": False, "error": f"metric '{metric}' not found"})

    if metric != "kp":
        if band:
            df = df[df["band"] == band]
        # preferisci SURVEY per noise/busy
        if metric in ("noise_dbm", "busy_ratio"):
            df = df[df["mode"] == "SURVEY"]
            # fallback: se non c'è survey, usa lo SCAN come proxy (scan_p50 o scan_n)
            if df.empty and metric == "noise_dbm":
                alt = load_df()
                alt = alt[(alt["ts"] >= cutoff) & (alt["mode"] == "SCAN")]
                # usa scan_p50 come surrogato del "livello" medio sul canale
                alt["noise_dbm"] = alt["scan_p50"]  # proxy
                alt["band"] = alt["band"].astype(str)
                if band: alt = alt[alt["band"] == band]
                df = alt

    # prepara punti (epoch ms + value)
    out = []
    for _, r in df.iterrows():
        v = safe_float(r.get(col))
        if v is None or pd.isna(v) or r["ts"] is pd.NaT: 
            continue
        out.append([int(r["ts"].timestamp()*1000), v])
    return jsonify({"ok": True, "points": out})

@app.route("/api/summary")
def api_summary():
    """
    Restituisce indicatori semplici + evidenze Quiet vs Storm per banda.
    """
    df = load_df()
    if df.empty:
        return jsonify({"ok": True, "summary": {}, "evidence": []})

    # ultimi 24h
    now = pd.Timestamp.utcnow().replace(tzinfo=timezone.utc)
    last24 = df[df["ts"] >= (now - pd.Timedelta(hours=24))]

    # KPI base
    kplast = df["kp"].dropna().tail(1).tolist()
    kplast = kplast[0] if kplast else None

    kpb = df["kp"].dropna()
    kpmax = float(kpb.max()) if not kpb.empty else None

    # Evidenze statistiche semplici (quiet≤3 vs storm≥5) per banda e metrica
    evidence = []
    for band in ("24","58"):
        for metric, label in (("noise_dbm", "Noise (dBm)"),
                              ("busy_ratio", "Busy ratio"),
                              ("scan_p50", "Scan p50 RSSI")):
            dd = df.copy()
            dd = dd[dd["band"].astype(str)==band]
            if metric in ("noise_dbm","busy_ratio"):
                dd = dd[dd["mode"]=="SURVEY"]
            quiet = dd[(dd["kp"]<=3)][metric].dropna()
            storm = dd[(dd["kp"]>=5)][metric].dropna()
            if len(quiet)>=30 and len(storm)>=30:
                q_med = float(quiet.median())
                s_med = float(storm.median())
                delta = s_med - q_med
                evidence.append({
                    "band": band,
                    "metric": label,
                    "quiet_med": q_med,
                    "storm_med": s_med,
                    "delta": delta
                })

    summary = {
        "kplast": kplast,
        "kpmax_alltime": kpmax,
        "rows_total": int(len(df)),
        "rows_24h": int(len(last24))
    }
    return jsonify({"ok": True, "summary": summary, "evidence": evidence})

if __name__ == "__main__":
    host = os.environ.get("HOST","0.0.0.0")
    port = int(os.environ.get("PORT","8088"))
    app.run(host=host, port=port, debug=False)

