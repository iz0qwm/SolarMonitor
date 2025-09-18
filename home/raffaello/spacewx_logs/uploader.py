#!/usr/bin/env python3
import os, json, time, queue, pathlib, requests, math
from datetime import datetime, timezone, timedelta
import yaml
from google.cloud import firestore
from google.oauth2 import service_account

#
# Magnetometro AK09916 (ICM-20948): ~0.15 µT per LSB
# Override con env MAG_UT_PER_COUNT se vuoi calibrare finemente.
#
AK09916_UT_PER_COUNT = float(os.environ.get("MAG_UT_PER_COUNT", "0.15"))

def _mag_norm_ut_from_latest(latest: dict) -> float | None:
    n = _to_num(latest.get("mag_norm_counts"))
    if n is None:
        return None
    return n * AK09916_UT_PER_COUNT

def _extract_radio_fields(latest: dict) -> tuple[dict, str | None, int | None]:
    """
    Ritorna (radio_fields, radio_mode, radio_band)
    - Se latest ha latest["rf"], popola noise/busy per 24 e 58.
    - Fallback: usa i campi piatti (compatibilità vecchio /api/latest).
    """
    radio = {}
    radio_mode = None
    radio_band = None

    rf = latest.get("rf")
    if isinstance(rf, dict):
        # Nuovo payload: prendi per ogni banda se presente
        for bkey, b in (("24", rf.get("24")), ("58", rf.get("58"))):
            if not isinstance(b, dict):
                continue
            # noise: preferisci noise_dbm; se assente e mode=SCAN usa scan_p50
            mode_b = (b.get("mode") or "").upper()
            noise = _to_num(b.get("noise_dbm"))
            if noise is None and mode_b == "SCAN":
                noise = _to_num(b.get("scan_p50"))
            if noise is not None:
                radio[f"noise_dbm_{bkey}"] = noise
            # busy: solo SURVEY
            busy = _to_num(b.get("busy_ratio"))
            if busy is not None and mode_b == "SURVEY":
                radio[f"busy_ratio_{bkey}"] = busy
        # non ha senso un singolo mode/band globale → li lasciamo None
        return radio, None, None

    # Fallback “flat”: vecchio /api/latest con mode/freq/band piatti
    mode = (latest.get("mode") or "").upper()
    band = _band_from_row(latest)
    if band in (24, 58):
        noise = _to_num(latest.get("noise_dbm"))
        if noise is None and mode == "SCAN":
            noise = _to_num(latest.get("scan_p50"))
        if noise is not None:
            radio[f"noise_dbm_{band}"] = noise
        busy = _to_num(latest.get("busy_ratio"))
        if busy is not None and mode == "SURVEY":
            radio[f"busy_ratio_{band}"] = busy
    return radio, mode or None, band

def _band_from(latest):
    """Ritorna 24 o 58 in base a 'band' o 'freq'."""
    b = latest.get("band")
    try:
        if b is not None:
            b = int(b)
            if b in (24, 58):
                return b
    except:
        pass
    f = latest.get("freq")
    try:
        f = float(f)
        if f < 3000:
            return 24
        else:
            return 58
    except:
        return None

def _to_num(v):
    try:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v) if math.isfinite(v) else None
        s = str(v).strip().lower()
        if s in ("", "n/a", "nan", "none", "null"):
            return None
        n = float(v)
        return n if math.isfinite(n) else None
    except Exception:
        return None

def _band_from_row(row: dict):
    """Ritorna 24 o 58 in base a band/freq, altrimenti None."""
    # 1) campo 'band' se esiste (24/58)
    b = row.get("band")
    try:
        if b is not None:
            b = int(b)
            if b in (24, 58):
                return b
    except Exception:
        pass
    # 2) deduci da 'freq' (MHz)
    f = _to_num(row.get("freq"))
    if f is not None:
        return 24 if f < 3000 else 58
    return None


def none_if_nan(x):
    try:
        f = float(x)
        return None if not math.isfinite(f) else f
    except:
        return None

def load_cfg(p):
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_fs(creds_path, project_id):
    creds = service_account.Credentials.from_service_account_file(creds_path)
    return firestore.Client(project=project_id, credentials=creds)

def now_ts():
    return datetime.now(timezone.utc)

# prima: r = requests.get(f"{api_base}/api/latest", timeout=5)
def fetch_latest(api_base):
    # UP_CONN_TIMEOUT=3.05  UP_READ_TIMEOUT=12  (override da env se vuoi)
    conn_to = float(os.environ.get("UP_CONN_TIMEOUT", "3.05"))
    read_to = float(os.environ.get("UP_READ_TIMEOUT", "20"))
    r = requests.get(f"{api_base}/api/latest", timeout=(conn_to, read_to))
    r.raise_for_status()
    j = r.json()
    if not j.get("ok"):
        return None
    return j.get("latest")


def ensure_dirs(p):
    pathlib.Path(p).mkdir(parents=True, exist_ok=True)


def write_status(fs, cfg, latest: dict):
    sid = cfg["sensor_id"]
    status_coll  = cfg["firestore"]["private_collection"]["status"]
    sensors_coll = cfg["firestore"]["private_collection"]["sensors"]

    radio, radio_mode, radio_band = _extract_radio_fields(latest)
    print(f"[UP] radio_fields={radio} (mode={radio_mode} band={radio_band})")

    fs.document(f"{sensors_coll}/{sid}").set({
        "displayName": sid,
        "caps": ["gps", "wifi", "sensehat"],
        "firmware": "node-1.0.0",
        "hardware": "rpi+hat",
        "public": cfg.get("privacy", {}).get("public", False),
        "location": {
            "lat": _to_num(latest.get("lat")),
            "lon": _to_num(latest.get("lon")),
        } if (latest.get("gps_fix") or "").upper() == "3D" else None,
        "updatedAt": firestore.SERVER_TIMESTAMP,
        "createdAt": firestore.SERVER_TIMESTAMP,
    }, merge=True)

    mag_ut = _mag_norm_ut_from_latest(latest)

    payload = {
        "online": True,
        "lastSeenAt": firestore.SERVER_TIMESTAMP,
        "gps_fix": latest.get("gps_fix"),
        "kp": _to_num(latest.get("kp")),
        "tec": _to_num(latest.get("tec")),
        "cn0_mean": _to_num(latest.get("cn0_mean")),
        "sv_used": _to_num(latest.get("sv_used")),
        "sv_tot": _to_num(latest.get("sv_tot")),
        "pdop": _to_num(latest.get("pdop")),
        "hdop": _to_num(latest.get("hdop")),
        "vdop": _to_num(latest.get("vdop")),
        **radio,
        "radio_mode": radio_mode,
        "radio_band": radio_band,
        # ambientali
        "t_c": _to_num(latest.get("t_c")),
        "rh_pct": _to_num(latest.get("rh_pct")),
        "p_hpa": _to_num(latest.get("p_hpa")),
        # magnetometro (counts; utili per delte/baseline)
        "mag_counts": {
            "x": _to_num(latest.get("mag_x_counts")),
            "y": _to_num(latest.get("mag_y_counts")),
            "z": _to_num(latest.get("mag_z_counts")),
            "norm": _to_num(latest.get("mag_norm_counts")),
        },
        # conversione in microtesla per uso diretto in grafici/alert
        # nuovo nome coerente
        "mag_ut": _to_num(mag_ut),
    }
    fs.document(f"{status_coll}/{sid}").set(payload, merge=True)
    print(f"[UP] wrote status to {status_coll}/{sid}")




def _to_num(v):
    try:
        if v is None: return None
        if str(v).lower() == "n/a": return None
        n = float(v)
        if math.isfinite(n): return n
        return None
    except Exception:
        return None


# --- aggiungi questo helper da qualche parte sopra write_raw ---
def _parse_ts_iso(ts_iso: str) -> datetime:
    """Parsa ISO 8601 anche con 'Z'. Ritorna datetime timezone-aware in UTC."""
    if not ts_iso:
        return datetime.now(timezone.utc)
    s = ts_iso.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)

# --- SOSTITUISCI interamente la funzione write_raw con questa ---
def write_raw(fs, cfg, latest):
    sid = cfg["sensor_id"]
    ts_iso = latest.get("ts_iso")
    if not ts_iso:
        return

    # 1) timestamp forte per range-query e partizioni esterne
    ts_dt = _parse_ts_iso(ts_iso)

    # 2) TTL: di default 10 giorni (override con env RAW_TTL_DAYS)
    ttl_days = int(os.environ.get("RAW_TTL_DAYS", "7"))
    expires_at = ts_dt + timedelta(days=ttl_days)

    # 3) path: measurements/{sensorId}/raw/{ts_iso} (idempotente sullo stesso ts)
    doc_path = f'{cfg["firestore"]["private_collection"]["raw"]}/{sid}/raw/{ts_iso}'

    # Enrich: aggiungi anche la conversione in µT dentro al documento raw
    mag_ut = _mag_norm_ut_from_latest(latest)

    payload = {
        **latest,                        # mantieni payload originale per massima tracciabilità
        # nuovo nome coerente
        "mag_norm_ut": _to_num(mag_ut),
        "ts": ts_dt,                     # datetime UTC (Firestore lo salva come Timestamp)
        "expiresAt": expires_at,         # campo su cui abiliteremo il TTL
        "ingestedAt": firestore.SERVER_TIMESTAMP,
    }
    fs.document(doc_path).set(payload, merge=True)

def main():
    cfg = load_cfg(os.environ.get("UPLOADER_CFG","/home/raffaello/spacewx_logs/uploader_config.yaml"))
    ensure_dirs(cfg["upload"]["buffer_dir"])
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cfg["firestore"]["credentials_json"]
    fs = get_fs(cfg["firestore"]["credentials_json"], cfg["project_id"])

    api_base = cfg["source"]["api_base"]
    period = cfg["upload"]["period_sec"]

    print("[UP] started; period:", period, "s")
    while True:
        try:
            latest = fetch_latest(api_base)
            # prima di write_status(...)
            if latest:
                print("[UP] latest row keys:", sorted(list(latest.keys())))
                # stampa rf se presente
                if isinstance(latest.get("rf"), dict):
                    print("[UP] rf.24:", latest["rf"].get("24"))
                    print("[UP] rf.58:", latest["rf"].get("58"))
                else:
                    print("[UP] flat sample:", {k: latest.get(k) for k in ("mode","freq","band","scan_p50","noise_dbm","busy_ratio")})

                write_status(fs, cfg, latest)
                write_raw(fs, cfg, latest)
                print("[UP] ok:", latest.get("ts_iso"))
            else:
                print("[UP] no latest")
        except Exception as e:
            print("[UP] ERROR:", e)
        time.sleep(period)

if __name__ == "__main__":
    main()
