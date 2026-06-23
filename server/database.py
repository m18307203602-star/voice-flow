"""数据库初始化 + 连接管理"""
import sqlite3
import os
from pathlib import Path

DB_DIR = Path(os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "data")))
DB_PATH = DB_DIR / "licenses.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS machines (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_code  TEXT UNIQUE NOT NULL,
    license_key   TEXT UNIQUE NOT NULL,
    first_seen    TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen     TEXT NOT NULL DEFAULT (datetime('now')),
    banned        INTEGER NOT NULL DEFAULT 0,
    notes         TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS activations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_code  TEXT NOT NULL,
    license_key   TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    activated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (machine_code) REFERENCES machines(machine_code)
);

CREATE TABLE IF NOT EXISTS validation_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_code  TEXT NOT NULL,
    ip_address    TEXT DEFAULT '',
    timestamp     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS admin_sessions (
    token         TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_machines_code ON machines(machine_code);
CREATE INDEX IF NOT EXISTS idx_activations_machine ON activations(machine_code);
CREATE INDEX IF NOT EXISTS idx_log_machine ON validation_log(machine_code);
"""


def get_db() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
