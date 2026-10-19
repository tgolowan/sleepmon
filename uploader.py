"""Pushes new readings from the local SQLite DB to the cloud service."""

import json
import logging
import os
import signal
import time
import urllib.error
import urllib.request

import db

CLOUD_URL = os.environ["SLEEPMON_CLOUD_URL"].rstrip("/")
TOKEN = os.environ["SLEEPMON_INGEST_TOKEN"]
INTERVAL_S = int(os.environ.get("SLEEPMON_UPLOAD_INTERVAL_S", 60))
BATCH = 1000
MAX_BACKOFF_S = 600

log = logging.getLogger("uploader")
running = True


def _stop(*_):
    global running
    running = False


def _sleep(seconds):
    end = time.time() + seconds
    while running and time.time() < end:
        time.sleep(1)


def get_last_uploaded(conn):
    row = conn.execute("SELECT value FROM upload_state WHERE key = 'last_ts'").fetchone()
    return int(row["value"]) if row else 0


def set_last_uploaded(conn, ts):
    conn.execute(
        "INSERT INTO upload_state (key, value) VALUES ('last_ts', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(ts),),
    )
    conn.commit()


def post(rows):
    body = json.dumps({"readings": rows}).encode()
    req = urllib.request.Request(
        f"{CLOUD_URL}/api/ingest",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main():
    logging.basicConfig(level=os.environ.get("SLEEPMON_LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    conn = db.connect()
    conn.execute("CREATE TABLE IF NOT EXISTS upload_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    log.info("Uploading to %s every %d s", CLOUD_URL, INTERVAL_S)

    backoff = INTERVAL_S
    while running:
        last = get_last_uploaded(conn)
        rows = [list(r) for r in conn.execute(
            "SELECT ts, co2, temp, rh FROM co2 WHERE ts > ? ORDER BY ts LIMIT ?", (last, BATCH)
        )]
        if not rows:
            _sleep(INTERVAL_S)
            continue
        try:
            post(rows)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            log.warning("upload failed (%d rows pending, retry in %d s): %s", len(rows), backoff, e)
            _sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_S)
            continue

        backoff = INTERVAL_S
        set_last_uploaded(conn, rows[-1][0])
        log.info("uploaded %d rows (up to %s)", len(rows),
                 time.strftime("%H:%M:%S", time.localtime(rows[-1][0])))
        if len(rows) < BATCH:
            _sleep(INTERVAL_S)

    conn.close()


if __name__ == "__main__":
    main()
