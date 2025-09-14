#!/usr/bin/env python3
import os
from datetime import datetime, timezone, timedelta
from google.cloud import firestore
from google.oauth2 import service_account

# ---- CONFIGURAZIONE ----
SENSOR_ID = os.environ.get("SID", "SCANDRIGLIA-01")
TTL_DAYS = int(os.environ.get("RAW_TTL_DAYS", "7"))         # retention desiderata
BATCH_LIMIT = int(os.environ.get("BATCH_LIMIT", "500"))     # doc per pagina

CFG_PATH = os.environ.get("UPLOADER_CFG", "/home/raffaello/spacewx_logs/uploader_config.yaml")

# --- loader YAML minimale (senza dipendere da uploader.py) ---
def _load_cfg(p):
    import yaml
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# --- parse ISO 8601 robusto (gestisce 'Z') ---
def _parse_ts_iso(ts_iso: str) -> datetime:
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

def _get_fs(creds_path, project_id):
    creds = service_account.Credentials.from_service_account_file(creds_path)
    return firestore.Client(project=project_id, credentials=creds)

def main():
    cfg = _load_cfg(CFG_PATH)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cfg["firestore"]["credentials_json"]
    fs = _get_fs(cfg["firestore"]["credentials_json"], cfg["project_id"])

    coll_path = f'{cfg["firestore"]["private_collection"]["raw"]}/{SENSOR_ID}/raw'
    coll = fs.collection(coll_path)

    total_updated = 0
    last_doc = None

    print(f"[BACKFILL] start on {coll_path} TTL={TTL_DAYS}d ...")

    while True:
        q = coll.order_by("__name__").limit(BATCH_LIMIT)
        if last_doc is not None:
            q = q.start_after(last_doc)

        docs = list(q.stream())
        if not docs:
            break

        batch = fs.batch()
        updated_this_page = 0

        for d in docs:
            data = d.to_dict() or {}
            # se già presente expiresAt, salta
            if "expiresAt" in data and data["expiresAt"] is not None:
                continue

            ts_iso = data.get("ts_iso")
            ts_dt = data.get("ts")
            if not isinstance(ts_dt, datetime):
                ts_dt = _parse_ts_iso(ts_iso) if ts_iso else datetime.now(timezone.utc)

            expires_at = ts_dt + timedelta(days=TTL_DAYS)

            batch.set(d.reference, {
                "ts": ts_dt,
                "expiresAt": expires_at,
            }, merge=True)

            updated_this_page += 1

        if updated_this_page > 0:
            batch.commit()
            total_updated += updated_this_page
            print(f"[BACKFILL] page: updated {updated_this_page} docs (total {total_updated})")

        last_doc = docs[-1]

    print(f"[BACKFILL] done. total updated docs: {total_updated}")

if __name__ == "__main__":
    main()
