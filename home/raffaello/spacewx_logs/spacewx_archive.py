#!/usr/bin/env python3
import os, gzip, sqlite3, csv
from datetime import datetime, timezone, timedelta

LOGDIR = os.path.expanduser("~/spacewx_logs")
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
    y = datetime.now(timezone.utc) - timedelta(days=1)
    ypath = os.path.join(LOGDIR, "daily", y.strftime("%Y"), y.strftime("%m"),
                         f"{BASE}_{y.strftime('%Y%m%d')}.csv.gz")
    if not os.path.exists(ypath):
        print(f"[ARCH] missing {ypath}")
        return 0
    rows = 0
    with gzip.open(ypath, "rt", newline="") as f, conn:
        rdr = csv.reader(f)
        header = next(rdr, None)
        ins = """INSERT INTO raw VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
        for r in rdr:
            conn.execute(ins, r)
            rows += 1
    print(f"[ARCH] imported {rows} rows from {ypath}")
    return rows

def rollup(conn):
    # hourly
    conn.execute("""
    INSERT OR REPLACE INTO rollup_hourly
    SELECT substr(ts_iso,1,13)||':00Z' AS hour_utc,
           AVG(kp), MAX(kp),
           AVG(tec), MAX(tec),
           AVG(noise_dbm), AVG(busy_ratio)
    FROM raw
    WHERE ts_iso >= datetime('now','-40 days')           -- limita finestra di ricalcolo
    GROUP BY 1
    """)
    # daily
    conn.execute("""
    INSERT OR REPLACE INTO rollup_daily
    SELECT substr(ts_iso,1,10) AS day_utc,
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
