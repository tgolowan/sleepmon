"""Postgres storage for readings uploaded from the Pi."""

import os

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

SAMPLE_INTERVAL_S = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS co2 (
    ts   BIGINT PRIMARY KEY,
    co2  INTEGER NOT NULL,
    temp DOUBLE PRECISION NOT NULL,
    rh   DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if not DATABASE_URL.startswith(("postgres://", "postgresql://")):
    raise RuntimeError(
        "DATABASE_URL is missing or empty. On Railway set it to ${{Postgres.DATABASE_URL}} "
        "(the name must match your Postgres service) and check that Postgres is running."
    )

pool = ConnectionPool(
    DATABASE_URL,
    min_size=1,
    max_size=5,
    kwargs={"row_factory": dict_row, "autocommit": True},
    open=False,
)


def init():
    pool.open(wait=True)
    with pool.connection() as conn:
        conn.execute(SCHEMA)


def insert_readings(rows):
    """rows: iterable of (ts, co2, temp, rh). Duplicates are ignored."""
    with pool.connection() as conn, conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO co2 (ts, co2, temp, rh) VALUES (%s, %s, %s, %s) ON CONFLICT (ts) DO NOTHING",
            rows,
        )
    with pool.connection() as conn:
        return conn.execute("SELECT MAX(ts) AS ts FROM co2").fetchone()["ts"]


def latest():
    with pool.connection() as conn:
        return conn.execute("SELECT ts, co2, temp, rh FROM co2 ORDER BY ts DESC LIMIT 1").fetchone()


def series(start, end, max_points=1500):
    bucket = max(SAMPLE_INTERVAL_S, (end - start) // max_points)
    with pool.connection() as conn:
        points = conn.execute(
            """
            SELECT (ts / %(b)s) * %(b)s AS t,
                   ROUND(AVG(co2))::int AS co2,
                   ROUND(AVG(temp)::numeric, 2)::float AS temp,
                   ROUND(AVG(rh)::numeric, 2)::float AS rh
            FROM co2 WHERE ts BETWEEN %(s)s AND %(e)s
            GROUP BY t ORDER BY t
            """,
            {"b": bucket, "s": start, "e": end},
        ).fetchall()
    return bucket, points


def stats(start, end):
    with pool.connection() as conn:
        s = conn.execute(
            """
            SELECT COUNT(*) AS samples,
                   ROUND(AVG(co2))::int AS co2_avg, MIN(co2) AS co2_min, MAX(co2) AS co2_max,
                   COUNT(*) FILTER (WHERE co2 > 1000) AS n_over_1000,
                   COUNT(*) FILTER (WHERE co2 > 1400) AS n_over_1400,
                   ROUND(AVG(temp)::numeric, 1)::float AS temp_avg,
                   ROUND(AVG(rh)::numeric, 1)::float AS rh_avg
            FROM co2 WHERE ts BETWEEN %(s)s AND %(e)s
            """,
            {"s": start, "e": end},
        ).fetchone()
    for key in ("n_over_1000", "n_over_1400"):
        s[key.replace("n_", "min_")] = round(s.pop(key) * SAMPLE_INTERVAL_S / 60)
    return s


def avg_co2_since(since):
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT AVG(co2)::float AS avg, COUNT(*) AS n FROM co2 WHERE ts >= %s", (since,)
        ).fetchone()
    return row["avg"] if row["n"] else None


def raw_rows(start, end):
    with pool.connection() as conn:
        return conn.execute(
            "SELECT ts, co2, temp, rh FROM co2 WHERE ts BETWEEN %s AND %s ORDER BY ts", (start, end)
        ).fetchall()


def get_setting(key, default=None):
    with pool.connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = %s", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (%s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (key, str(value)),
        )
