import os
import sqlite3

DB_PATH = os.environ.get("SLEEPMON_DB", os.path.expanduser("~/sleepmon/sleepmon.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS co2 (
    ts   INTEGER PRIMARY KEY,  -- unix seconds, UTC
    co2  INTEGER NOT NULL,     -- ppm
    temp REAL    NOT NULL,     -- °C
    rh   REAL    NOT NULL      -- %
);
"""


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.row_factory = sqlite3.Row
    return conn
