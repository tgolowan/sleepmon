"""Sleep monitor cloud service: backup storage, online dashboard, Telegram bot."""

import csv
import hmac
import io
import logging
import os
import threading
import time
from functools import wraps

from flask import Flask, Response, abort, jsonify, request, send_from_directory

import alerts
import config
import store
import telegram_bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("app")

app = Flask(__name__)
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_BATCH = 5000


def _matches(given, expected):
    return bool(expected) and hmac.compare_digest((given or "").encode(), expected.encode())


def dashboard_auth(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not config.DASHBOARD_PASSWORD:
            abort(503, "DASHBOARD_PASSWORD is not set")
        auth = request.authorization
        if not auth or not _matches(auth.password, config.DASHBOARD_PASSWORD):
            return Response("Login required", 401, {"WWW-Authenticate": 'Basic realm="sleepmon"'})
        return view(*args, **kwargs)

    return wrapper


def _range():
    now = int(time.time())
    end = int(request.args.get("to", now))
    start = int(request.args.get("from", end - 12 * 3600))
    return start, end


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/ingest")
def ingest():
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not _matches(token, config.INGEST_TOKEN):
        abort(401)
    readings = (request.get_json(silent=True) or {}).get("readings") or []
    if len(readings) > MAX_BATCH:
        abort(413)
    rows = [(int(ts), int(co2), float(temp), float(rh)) for ts, co2, temp, rh in readings]
    stored_until = store.insert_readings(rows) if rows else None
    return {"received": len(rows), "stored_until": stored_until}


@app.post("/telegram/webhook")
def telegram_webhook():
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not _matches(secret, config.TELEGRAM_WEBHOOK_SECRET):
        abort(401)
    update = request.get_json(silent=True) or {}
    threading.Thread(target=_handle_update_safe, args=(update,), daemon=True).start()
    return {"ok": True}


def _handle_update_safe(update):
    try:
        telegram_bot.handle_update(update)
    except Exception:
        log.exception("failed to handle Telegram update")


@app.get("/")
@dashboard_auth
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/latest")
@dashboard_auth
def latest():
    return jsonify(store.latest())


@app.get("/api/co2")
@dashboard_auth
def co2_series():
    start, end = _range()
    bucket, points = store.series(start, end)
    return jsonify(
        {
            "from": start,
            "to": end,
            "bucket_s": bucket,
            "points": [[p["t"], p["co2"], p["temp"], p["rh"]] for p in points],
            "stats": store.stats(start, end),
        }
    )


@app.get("/api/co2.csv")
@dashboard_auth
def co2_csv():
    start, end = _range()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["timestamp_utc", "co2_ppm", "temp_c", "rh_pct"])
    for r in store.raw_rows(start, end):
        writer.writerow([time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r["ts"])), r["co2"], r["temp"], r["rh"]])
    return Response(
        out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=sleepmon_co2.csv"},
    )


store.init()
telegram_bot.setup_webhook()
alerts.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
