#!/usr/bin/env python3
import os, gzip, sqlite3, csv
from datetime import datetime, timezone, timedelta

LOGDIR = os.environ.get("LOGDIR", "/home/raffaello/spacewx_logs")
DB = os.path.join(LOGDIR, "spacewx.db")
BASE = "wifi_gps_kp_qos"

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS raw (
  ts_iso TEXT, kp REAL, kp_when TEXT,
  gps_fix TEXT, lat REAL, lon REAL, alt REAL,
  pdop REAL, hdop REAL, vdop REAL, sv_used INTEGER, sv_tot INTEGER, cn0_mean REAL,
  mode TEXT, freq INTEGER, noise_dbm REAL, busy_ratio REAL, 
  scan_n INTEGER, scan_p50 REAL, scan_p10 REAL, scan_p90 REAL, band TEXT,
  tec REAL, tec_source TEXT
);
CREATE INDEX IF NOT EXISTS idx_raw_ts ON raw(ts_iso);
CREATE INDEX IF NOT EXISTS idx_raw_freq ON raw(freq);
CREATE TABLE IF NOT EXISTS rollup_hourly (
  hour_utc TEXT PRIMARY KEY,
  kp_avg REAL, kp_max REAL,
  tec_avg REAL, tec_max REAL,
  noise_dbm_avg REAL, busy_ratio_avg REAL
);
CREATE TABLE IF NOT EXISTS rollup_daily (
  day_utc TEXT PRIMARY KEY,
  kp_avg REAL, kp_max REAL,
  tec_avg REAL, tec_max REAL,
  noise_dbm_avg REAL, busy_ratio_avg REAL
);
"""

def connect():
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)
    return conn

def import_yesterday(conn):
    COLS = [
        "ts_iso","kp","kp_when",
        "gps_fix","lat","lon","alt",
        "pdop","hdop","vdop","sv_used","sv_tot","cn0_mean",
        "mode","freq","noise_dbm","busy_ratio",
        "scan_n","scan_p50","scan_p10","scan_p90","band",
        "tec","tec_source"
    ]
    y = datetime.now(timezone.utc) - timedelta(days=1)
    ypath = os.path.join(LOGDIR, "daily", y.strftime("%Y"), y.strftime("%m"),
                         f"{BASE}_{y.strftime('%Y%m%d')}.csv.gz")
    if not os.path.exists(ypath):
        print(f"[ARCH] missing {ypath}")
        return 0

    placeholders = ",".join(["?"]*len(COLS))
    ins = f"INSERT INTO raw({','.join(COLS)}) VALUES ({placeholders})"

    rows = 0
    with gzip.open(ypath, "rt", newline="") as f, conn:
        rdr = csv.reader(f)
        header = next(rdr, None)  # scarta header del file
        for r in rdr:
            # Normalizza lunghezza: taglia extra o aggiunge None se mancano campi
            if len(r) > len(COLS):
                r = r[:len(COLS)]
            elif len(r) < len(COLS):
                r = r + [None]*(len(COLS)-len(r))
            # Converti "" o "NaN" in None per coerenza col JSON/DB
            r = [None if (x == "" or x == "NaN") else x for x in r]
            conn.execute(ins, r)
            rows += 1
    print(f"[ARCH] imported {rows} rows from {ypath}")
    return rows


def rollup(conn):
    # hourly
    conn.execute("""
    INSERT OR REPLACE INTO rollup_hourly
    SELECT substr(replace(ts_iso, '+00:00','Z'),1,13)||':00Z' AS hour_utc,
        AVG(kp), MAX(kp),
        AVG(tec), MAX(tec),
        AVG(noise_dbm), AVG(busy_ratio)
    FROM raw
    WHERE ts_iso >= datetime('now','-40 days')
    GROUP BY 1
    """)
    # daily
    conn.execute("""
    INSERT OR REPLACE INTO rollup_daily
    SELECT substr(replace(ts_iso, '+00:00','Z'),1,10) AS day_utc,
        AVG(kp), MAX(kp),
        AVG(tec), MAX(tec),
        AVG(noise_dbm), AVG(busy_ratio)
    FROM raw
    GROUP BY 1
    """)


def main():
    conn = connect()
    n = import_yesterday(conn)
    if n > 0:
        rollup(conn)
        conn.commit()
        print("[ARCH] rollups updated")

if __name__ == "__main__":
    main()
