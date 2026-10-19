"""Web dashboard: http://sleepmon.local:8000"""

import csv
import io
import os
import time
from contextlib import closing

from flask import Flask, Response, jsonify, request, send_from_directory

import db

SAMPLE_INTERVAL_S = 5
MAX_POINTS = 1500

app = Flask(__name__)
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def _range():
    now = int(time.time())
    end = int(request.args.get("to", now))
    start = int(request.args.get("from", end - 12 * 3600))
    return start, end


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/latest")
def latest():
    with closing(db.connect()) as conn:
        row = conn.execute("SELECT ts, co2, temp, rh FROM co2 ORDER BY ts DESC LIMIT 1").fetchone()
    return jsonify(dict(row) if row else None)


@app.get("/api/co2")
def co2_series():
    start, end = _range()
    bucket = max(SAMPLE_INTERVAL_S, (end - start) // MAX_POINTS)
    with closing(db.connect()) as conn:
        points = conn.execute(
            """
            SELECT (ts / :b) * :b AS t,
                   ROUND(AVG(co2)) AS co2, ROUND(AVG(temp), 2) AS temp, ROUND(AVG(rh), 2) AS rh
            FROM co2 WHERE ts BETWEEN :s AND :e
            GROUP BY t ORDER BY t
            """,
            {"b": bucket, "s": start, "e": end},
        ).fetchall()
        stats = conn.execute(
            """
            SELECT COUNT(*) AS samples,
                   ROUND(AVG(co2)) AS co2_avg, MIN(co2) AS co2_min, MAX(co2) AS co2_max,
                   SUM(co2 > 1000) AS n_over_1000, SUM(co2 > 1400) AS n_over_1400,
                   ROUND(AVG(temp), 1) AS temp_avg, ROUND(AVG(rh), 1) AS rh_avg
            FROM co2 WHERE ts BETWEEN :s AND :e
            """,
            {"s": start, "e": end},
        ).fetchone()
    stats = dict(stats)
    for key in ("n_over_1000", "n_over_1400"):
        stats[key.replace("n_", "min_")] = round((stats.pop(key) or 0) * SAMPLE_INTERVAL_S / 60)
    return jsonify(
        {
            "from": start,
            "to": end,
            "bucket_s": bucket,
            "points": [[p["t"], p["co2"], p["temp"], p["rh"]] for p in points],
            "stats": stats,
        }
    )


@app.get("/api/co2.csv")
def co2_csv():
    start, end = _range()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["timestamp_utc", "co2_ppm", "temp_c", "rh_pct"])
    with closing(db.connect()) as conn:
        for row in conn.execute(
            "SELECT ts, co2, temp, rh FROM co2 WHERE ts BETWEEN ? AND ? ORDER BY ts", (start, end)
        ):
            writer.writerow([time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(row["ts"])), *list(row)[1:]])
    return Response(
        out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=sleepmon_co2.csv"},
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("SLEEPMON_PORT", 8000)))
