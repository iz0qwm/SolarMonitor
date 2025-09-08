#!/usr/bin/env python3
import os, json, sqlite3
from datetime import datetime, timezone, timedelta, date  
from flask import Flask, jsonify, render_template, request
import pandas as pd
import math
import traceback

# --- ENV / Path ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

TITLE     = os.environ.get("TITLE", "Space Weather QoS")
LOGDIR    = os.environ.get("LOGDIR", "/home/raffaello/spacewx_logs")
DB_PATH   = os.environ.get("DB_PATH", "/home/raffaello/spacewx_logs/spacewx.db")
BASE_NAME = os.environ.get("CSV_BASENAME", "wifi_gps_kp_qos")  # coerente con logger
TODAY_UTC = lambda: datetime.now(timezone.utc).date()

print(f"[APP] LOGDIR={LOGDIR}")
print(f"[APP] DB_PATH={DB_PATH} exists={os.path.exists(DB_PATH)}")

app = Flask(__name__)

def _read_db_range(start_iso, end_iso):
    if not os.path.exists(DB_PATH):
        print(f"[DB] not found: {DB_PATH}")
        return pd.DataFrame()
    try:
        con = sqlite3.connect(DB_PATH)
        q = """
        SELECT ts_iso, kp, kp_when, gps_fix, lat, lon, alt,
               pdop, hdop, vdop, sv_used, sv_tot, cn0_mean,
               mode, freq, noise_dbm, busy_ratio, scan_n, scan_p50, scan_p10, scan_p90, band,
               tec, tec_source
        FROM raw
        WHERE ts_iso >= ? AND ts_iso < ?
        ORDER BY ts_iso ASC
        """
        df_db = pd.read_sql_query(q, con, params=[start_iso, end_iso])
        con.close()
        print(f"[DB] rows={len(df_db)} from {start_iso} to {end_iso}")
        return df_db
    except Exception as e:
        print(f"[DB] ERROR reading {DB_PATH}: {e}")
        traceback.print_exc()
        try:
            con.close()
        except: pass
        return pd.DataFrame()


def none_if_nan(x):
    try:
        return None if (x is None or not math.isfinite(float(x))) else float(x)
    except (TypeError, ValueError):
        return None

def parse_day_param(day_str: str | None):
    if not day_str:
        return None
    try:
        d = datetime.strptime(day_str, "%Y-%m-%d").date()
        return d
    except Exception:
        return None

def daily_csv_path_for_date(d: date):
    y, m, dd = d.strftime("%Y"), d.strftime("%m"), d.strftime("%d")
    daydir = os.path.join(LOGDIR, "daily", y, m)
    return os.path.join(daydir, f"{BASE_NAME}_{y}{m}{dd}.csv")

# --- Normalizzazioni / util ---
def _normalize_band(s):
    if s is None: return None
    x = str(s).strip().lower().replace('ghz','').replace(' ','').replace('.','')
    if x in ('24','2400'): return '24'
    if x in ('58','5800'): return '58'
    return None

def safe_float(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except:
        return None


def _parse_ts(df):
    if "ts_iso" in df.columns:
        df["ts"] = pd.to_datetime(df["ts_iso"], utc=True, errors="coerce")
    else:
        df["ts"] = pd.NaT
    return df

# --- Loader composito: DB (storico) + CSV (oggi) ---
def load_df(minutes=None, max_rows=250_000, specific_day: date | None = None):
    """
    Se specific_day è valorizzato, carica solo [specific_day 00:00Z, specific_day+1 00:00Z).
    Altrimenti usa la finestra scorrevole 'minutes' (default 3 giorni).
    """
    now = datetime.now(timezone.utc)

    if specific_day:
        start = datetime.combine(specific_day, datetime.min.time(), tzinfo=timezone.utc)
        end   = start + timedelta(days=1)
        frames = []

        # --- DB storico per quel giorno
        df_db = _read_db_range(start.isoformat(), end.isoformat())
        if not df_db.empty:
            frames.append(df_db)

        # --- CSV del giorno (tipicamente solo oggi; ieri di solito è già nel DB)
        csv_path = daily_csv_path_for_date(specific_day)
        if os.path.exists(csv_path):
            try:
                frames.append(pd.read_csv(csv_path))
            except Exception as e:
                print(f"[CSV] ERROR reading {csv_path}: {e}")

        if not frames:
            print(f"[LOAD] no frames for day {specific_day}")
            return pd.DataFrame()

        df = pd.concat(frames, ignore_index=True)
        df = _parse_ts(df)
        mask = (df["ts"] >= pd.Timestamp(start)) & (df["ts"] < pd.Timestamp(end))
        df = df[mask]
        if "band" in df.columns:
            df["band"] = df["band"].astype(str)
        if len(df) > max_rows:
            df = df.tail(max_rows)
        return df.reset_index(drop=True)

    # -------- modalità finestra scorrevole --------
    if minutes is None:
        minutes = 3*24*60
    cutoff = now - timedelta(minutes=minutes)
    start_today = datetime.combine(TODAY_UTC(), datetime.min.time(), tzinfo=timezone.utc)
    frames = []

    # --- DB storico da cutoff fino a inizio oggi (se la finestra sconfina nel passato)
    if os.path.exists(DB_PATH) and cutoff < start_today:
        df_db = _read_db_range(cutoff.isoformat(), start_today.isoformat())
        if not df_db.empty:
            frames.append(df_db)

    # --- CSV odierno
    csv_today = daily_csv_path_for_date(now.date())
    if os.path.exists(csv_today):
        try:
            frames.append(pd.read_csv(csv_today))
        except Exception as e:
            print(f"[CSV] ERROR reading {csv_today}: {e}")

    if not frames:
        print("[LOAD] no frames in sliding window")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df = _parse_ts(df)

    # Finestra [cutoff, now]
    if "ts" in df.columns:
        mask = (df["ts"] >= pd.Timestamp(cutoff)) & (df["ts"] <= pd.Timestamp(now))
        df = df[mask]
    if "band" in df.columns:
        df["band"] = df["band"].astype(str)
    if len(df) > max_rows:
        df = df.tail(max_rows)
    return df.reset_index(drop=True)


# ---- Routes ----
@app.route("/")
def index():
    return render_template("index.html", title=TITLE)

@app.get("/api/summary")
def api_summary():
    # permette override finestra con ?minutes=...
    day = parse_day_param(request.args.get("day"))
    minutes = int(request.args.get("minutes", "4320"))
    df = load_df(minutes=minutes, specific_day=day)

    if df.empty:
        return jsonify({"ok": True, "points": []})

    # Se "day" è impostato, abbiamo già una finestra [day 00:00Z, day+1 00:00Z)
    # → NON applichiamo un secondo cutoff relativo a "now".
    if day is None:
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=minutes)
        df = df[df["ts"] >= cutoff]


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
    df = load_df(minutes=24*60)  # 24h bastano per l'ultimo
    if df.empty:
        return jsonify({"ok": True, "latest": None})

    r = df.iloc[-1].to_dict()
    fix = (r.get("gps_fix") or "NO").strip().upper()

    # lat/lon/alt solo se fix 3D; altrimenti None
    lat = safe_float(r.get("lat")) if fix == "3D" else None
    lon = safe_float(r.get("lon")) if fix == "3D" else None
    alt = safe_float(r.get("alt")) if fix == "3D" else None

    latest = {
        "ts_iso": r.get("ts_iso"),
        "kp":        safe_float(r.get("kp")),
        "tec":       safe_float(r.get("tec")),
        "tec_source": r.get("tec_source"),
        "gps_fix":    fix,
        "lat":        lat,
        "lon":        lon,
        "alt":        alt,
        "pdop":      safe_float(r.get("pdop")),
        "hdop":      safe_float(r.get("hdop")),
        "vdop":      safe_float(r.get("vdop")),
        "sv_used":   safe_float(r.get("sv_used")),
        "sv_tot":    safe_float(r.get("sv_tot")),
        "cn0_mean":  safe_float(r.get("cn0_mean")),
    }
    return jsonify({"ok": True, "latest": latest})


@app.get("/api/gps_track")
def api_gps_track():
    day = parse_day_param(request.args.get("day"))
    minutes = int(request.args.get("minutes", "180"))
    df = load_df(minutes=minutes, specific_day=day)

    if df.empty or "lat" not in df.columns or "lon" not in df.columns:
        return jsonify({"ok": True, "points": []})

    if day is not None:
        dd = df[df["lat"].notna() & df["lon"].notna()].copy()
    else:
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=minutes)
        dd = df[(df["ts"]>=cutoff) & df["lat"].notna() & df["lon"].notna()].copy()

    pts = [{"ts": str(t), "lat": float(a), "lon": float(b)} for t,a,b in zip(dd["ts"], dd["lat"], dd["lon"])]
    return jsonify({"ok": True, "points": pts})


@app.get("/api/series")
def api_series():
    day     = parse_day_param(request.args.get("day"))  # NEW
    metric  = (request.args.get("metric") or "noise_dbm").strip().lower()
    band    = _normalize_band(request.args.get("band"))
    minutes = int(request.args.get("minutes", "4320"))
    agg     = (request.args.get("agg") or "").strip().lower()
    window  = (request.args.get("window") or "").strip().lower()

    df = load_df(minutes=minutes, specific_day=day)     # NEW

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

    # fallback noise/busy → scan_p50 se tutto NaN
    if metric in ("noise_dbm", "busy_ratio") and (col not in df or df[col].isna().all()) and "scan_p50" in df.columns:
        df = df.copy()
        col = "scan_p50"

    dd = df[["ts", col]].dropna()
    if dd.empty:
        return jsonify({"ok": True, "points": []})

    if agg in ("median","mean") and window:
        dd = dd.set_index("ts")
        s = (dd[col].resample(window).median() if agg=="median" else dd[col].resample(window).mean()).dropna()
        out = [[t.isoformat(), float(v)] for t, v in s.items()]
    else:
        out = [[t.isoformat(), float(v)] for t, v in zip(dd["ts"], dd[col])]

    return jsonify({"ok": True, "points": out})

@app.get("/api/series_gps")
def api_series_gps():
    day     = parse_day_param(request.args.get("day"))  # NEW
    metric  = (request.args.get("metric") or "tec").strip().lower()
    minutes = int(request.args.get("minutes", "4320"))
    agg     = (request.args.get("agg") or "").strip().lower()
    window  = (request.args.get("window") or "").strip().lower()

    df = load_df(minutes=minutes, specific_day=day)

    if df.empty or metric not in df.columns:
        return jsonify({"ok": True, "points": []})

    if day is not None:
        dd = df[df[metric].notna()][["ts", metric]].copy()
    else:
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=minutes)
        dd = df[(df["ts"]>=cutoff) & df[metric].notna()][["ts", metric]].copy()

    if dd.empty:
        return jsonify({"ok": True, "points": []})


    if agg in ("median","mean") and window:
        dd = dd.set_index("ts")
        s = (dd[metric].resample(window).median() if agg=="median" else dd[metric].resample(window).mean()).dropna()
        out = [[t.isoformat(), float(v)] for t, v in s.items()]
    else:
        out = [[t.isoformat(), float(v)] for t, v in zip(dd["ts"], dd[metric])]

    return jsonify({"ok": True, "points": out})

@app.get("/api/glossary")
def api_glossary():
    G = [
        {"field":"ts_iso","label":"Timestamp (UTC)","desc":"Istante di misura in formato ISO 8601 (UTC)."},
        {"field":"kp","label":"Kp Index","desc":"Indice planetario di attività geomagnetica (0–9). Valori ≥5 indicano tempesta geomagnetica."},
        {"field":"kp_when","label":"Kp valid at","desc":"Orario a cui si riferisce il valore Kp (slot ufficiale)."},
        {"field":"gps_fix","label":"Fix GPS","desc":"Stato del fix del ricevitore (3D=buono)."},
        {"field":"lat/lon/alt","label":"Posizione","desc":"Coordinate geografiche e quota del ricevitore."},
        {"field":"pdop/hdop/vdop","label":"DOP","desc":"Dilution of Precision (Position/Horizontal/Vertical)."},
        {"field":"sv_used/sv_tot","label":"Satelliti","desc":"# usati nel fix / # totali visti."},
        {"field":"cn0_mean","label":"C/N₀ medio","desc":"Rapporto portante/rumore medio dei satelliti (dB-Hz)."},
        {"field":"mode","label":"Modo scan","desc":"Tipo misura radio (SCAN o SURVEY)."},
        {"field":"freq/band","label":"Frequenza / Banda","desc":"Canale misurato e banda (24=2.4 GHz, 58=5.8 GHz)."},
        {"field":"noise_dbm","label":"Rumore RF (dBm)","desc":"Più alto (meno negativo) = più rumore."},
        {"field":"busy_ratio","label":"Occupazione canale","desc":"Quota di tempo in cui il canale è occupato."},
        {"field":"scan_p50/p10/p90","label":"RSSI percentili","desc":"Distribuzione RSSI rilevata nello scan."},
        {"field":"tec","label":"TEC","desc":"Total Electron Content locale (TECU)."},
        {"field":"tec_source","label":"Sorgente TEC","desc":"Modello/servizio e timestamp del dato TEC."},
    ]
    return jsonify({"ok": True, "items": G})

if __name__ == "__main__":
    host = os.environ.get("HOST","0.0.0.0")
    port = int(os.environ.get("PORT","8088"))
    app.run(host=host, port=port, debug=False)
