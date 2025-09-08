#!/usr/bin/env python3
import os, json, re
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, render_template, request
import pandas as pd

# --- env ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

CSV_PATH = os.environ.get("CSV_PATH", "/home/raffaello/spacewx_logs/wifi_gps_kp_qos.csv")
TITLE    = os.environ.get("TITLE", "Space Weather QoS")

app = Flask(__name__)

# --- helpers ---
def _normalize_band(s):
    if s is None: return None
    x = str(s).strip().lower().replace('ghz','').replace(' ','').replace('.','')
    if x in ('24','2400'): return '24'
    if x in ('58','5800'): return '58'
    return None

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

def safe_float(x):
    try: return float(x)
    except: return None

# ---- Routes ----
@app.route("/")
def index():
    return render_template("index.html", title=TITLE)

@app.get("/api/summary")
def api_summary():
    df = load_df()
    if df.empty:
        return jsonify({"ok": True, "summary": {
            "kplast": None,
            "kpmax_alltime": None,
            "rows_total": 0,
            "rows_24h": 0
        }, "evidence": []})

    # Kp last + max
    kps = df["kp"].dropna() if "kp" in df.columns else pd.Series([], dtype=float)
    kplast = float(kps.iloc[-1]) if not kps.empty else None
    kpmax  = float(kps.max()) if not kps.empty else None

    now_utc = pd.Timestamp.now(tz="UTC")
    rows_24h = int((df["ts"] >= (now_utc - pd.Timedelta(days=1))).sum())

    summary = {
        "kplast": kplast,
        "kpmax_alltime": kpmax,
        "rows_total": int(len(df)),
        "rows_24h": rows_24h
    }
    return jsonify({"ok": True, "summary": summary, "evidence": []})

@app.get("/api/latest")
def api_latest():
    # Restituisce l'ultimo record utile per header badges e mappa
    df = load_df()
    if df.empty:
        return jsonify({"ok": True, "latest": None})
    r = df.iloc[-1].to_dict()
    latest = {
        "ts_iso": r.get("ts_iso"),
        "kp": safe_float(r.get("kp")),
        "tec": safe_float(r.get("tec")),
        "tec_source": r.get("tec_source"),
        "gps_fix": r.get("gps_fix"),
        "lat": safe_float(r.get("lat")),
        "lon": safe_float(r.get("lon")),
        "alt": safe_float(r.get("alt")),
        "pdop": safe_float(r.get("pdop")),
        "hdop": safe_float(r.get("hdop")),
        "vdop": safe_float(r.get("vdop")),
        "sv_used": safe_float(r.get("sv_used")),
        "sv_tot": safe_float(r.get("sv_tot")),
        "cn0_mean": safe_float(r.get("cn0_mean"))
    }
    return jsonify({"ok": True, "latest": latest})

@app.get("/api/gps_track")
def api_gps_track():
    # Restituisce la traccia GPS degli ultimi N minuti
    minutes = int(request.args.get("minutes", "180"))
    df = load_df()
    if df.empty or "lat" not in df.columns or "lon" not in df.columns:
        return jsonify({"ok": True, "points": []})

    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=minutes)
    dd = df[(df["ts"]>=cutoff) & df["lat"].notna() & df["lon"].notna()].copy()
    pts = [{"ts": str(t), "lat": float(a), "lon": float(b)} for t,a,b in zip(dd["ts"], dd["lat"], dd["lon"])]
    return jsonify({"ok": True, "points": pts})


@app.get("/api/series")
def api_series():
    # Serie temporali per metriche RF e Kp, con opzionale aggregazione temporale
    metric  = request.args.get("metric", "noise_dbm").strip().lower()
    band    = _normalize_band(request.args.get("band"))
    minutes = int(request.args.get("minutes", "4320"))
    agg     = (request.args.get("agg") or "").strip().lower()   # "median" | "mean" | ""
    window  = (request.args.get("window") or "").strip().lower() # es. "5min", "10min"

    df = load_df()
    if df.empty:
        return jsonify({"ok": True, "points": []})

    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=minutes)
    df = df[df["ts"] >= cutoff]

    colmap = {
        "noise_dbm": "noise_dbm",
        "busy_ratio": "busy_ratio",
        "scan_p50": "scan_p50",
        "scan_n": "scan_n",
        "kp": "kp",
    }
    col = colmap.get(metric)
    if not col or col not in df.columns:
        return jsonify({"ok": False, "error": f"metric '{metric}' not found", "points": []})

    if metric != "kp" and band is not None:
        df = df[df["band"].astype(str) == band]

    # fallback: se noise/busy sono NaN, usa scan_p50
    if metric in ("noise_dbm", "busy_ratio") and (col not in df or df[col].isna().all()) and "scan_p50" in df.columns:
        df = df.copy()
        col = "scan_p50"

    dd = df[["ts", col]].dropna()
    if dd.empty:
        return jsonify({"ok": True, "points": []})

    # Aggregazione temporale opzionale (resample con median/mean)
    if agg in ("median","mean") and window:
        dd = dd.set_index("ts")
        if agg == "median":
            s = dd[col].resample(window).median().dropna()
        else:
            s = dd[col].resample(window).mean().dropna()
        out = [[t.isoformat(), float(v)] for t, v in s.items()]
    else:
        out = [[t.isoformat(), float(v)] for t, v in zip(dd["ts"], dd[col])]

    return jsonify({"ok": True, "points": out})


@app.get("/api/series_gps")
def api_series_gps():
    # Serie per metriche GPS/IONO con aggregazione opzionale
    # metric: tec | pdop | hdop | vdop | cn0_mean | sv_used | alt
    metric  = request.args.get("metric", "tec").strip().lower()
    minutes = int(request.args.get("minutes", "4320"))
    agg     = (request.args.get("agg") or "").strip().lower()   # "median" | "mean" | ""
    window  = (request.args.get("window") or "").strip().lower() # es. "5min"

    df = load_df()
    if df.empty or metric not in df.columns:
        return jsonify({"ok": True, "points": []})

    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=minutes)
    dd = df[(df["ts"]>=cutoff) & df[metric].notna()][["ts", metric]].copy()
    if dd.empty:
        return jsonify({"ok": True, "points": []})

    if agg in ("median","mean") and window:
        dd = dd.set_index("ts")
        if agg == "median":
            s = dd[metric].resample(window).median().dropna()
        else:
            s = dd[metric].resample(window).mean().dropna()
        out = [[t.isoformat(), float(v)] for t, v in s.items()]
    else:
        out = [[t.isoformat(), float(v)] for t, v in zip(dd["ts"], dd[metric])]

    return jsonify({"ok": True, "points": out})

@app.get("/api/glossary")
def api_glossary():
    # Piccolo glossario dei campi mostrati nell'interfaccia
    G = [
        {"field":"ts_iso","label":"Timestamp (UTC)","desc":"Istante di misura in formato ISO 8601 (UTC)."},
        {"field":"kp","label":"Kp Index","desc":"Indice planetario di attività geomagnetica (0–9). Valori ≥5 indicano tempesta geomagnetica."},
        {"field":"kp_when","label":"Kp valid at","desc":"Orario a cui si riferisce il valore Kp (slot ufficiale)."},
        {"field":"gps_fix","label":"Fix GPS","desc":"Stato del fix del ricevitore (3D=buono)."},
        {"field":"lat/lon/alt","label":"Posizione","desc":"Coordinate geografiche e quota del ricevitore."},
        {"field":"pdop/hdop/vdop","label":"DOP","desc":"Dilution of Precision (Position/Horizontal/Vertical): valori più bassi indicano geometria satellitare migliore."},
        {"field":"sv_used/sv_tot","label":"Satelliti","desc":"Numero di satelliti usati nel fix e totale visibili."},
        {"field":"cn0_mean","label":"C/N₀ medio","desc":"Rapporto portante/rumore medio dei satelliti tracciati (dB‑Hz)."},
        {"field":"mode","label":"Modo scan","desc":"Tipo di misura radio (SCAN o SURVEY)."},
        {"field":"freq/band","label":"Frequenza / Banda","desc":"Canale misurato e banda (24=2.4 GHz, 58=5.8 GHz)."},
        {"field":"noise_dbm","label":"Rumore RF (dBm)","desc":"Livello medio di rumore in dBm; più alto (meno negativo) = più rumore."},
        {"field":"busy_ratio","label":"Occupazione canale","desc":"Stima percentuale del tempo in cui il canale è occupato."},
        {"field":"scan_p50/p10/p90","label":"RSSI percentili","desc":"Distribuzione del livello di segnale rilevato nello scan."},
        {"field":"tec","label":"TEC","desc":"Total Electron Content stimato sulla cella ionosferica locale (unità TECU)."},
        {"field":"tec_source","label":"Sorgente TEC","desc":"Modello/servizio e timestamp del dato TEC (es. INGV WSNC)."},
    ]
    return jsonify({"ok": True, "items": G})

if __name__ == "__main__":
    host = os.environ.get("HOST","0.0.0.0")
    port = int(os.environ.get("PORT","8088"))
    app.run(host=host, port=port, debug=False)