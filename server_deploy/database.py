"""Database initialization & connection management"""
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
    last_heartbeat TEXT DEFAULT '',
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

CREATE TABLE IF NOT EXISTS trial_cards (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    card_key      TEXT UNIQUE NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    used_by       TEXT DEFAULT '',
    used_at       TEXT DEFAULT '',
    expires_at    TEXT NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1
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
CREATE INDEX IF NOT EXISTS idx_trial_cards_key ON trial_cards(card_key);

CREATE TABLE IF NOT EXISTS prompts_audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_code  TEXT NOT NULL,
    ip_address    TEXT DEFAULT '',
    token_hash    TEXT DEFAULT '',
    mode_count    INTEGER DEFAULT 0,
    success       INTEGER NOT NULL DEFAULT 1,
    timestamp     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_prompts_audit_time ON prompts_audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_prompts_audit_machine ON prompts_audit_log(machine_code);

CREATE TABLE IF NOT EXISTS recording_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_code        TEXT NOT NULL,
    client_record_id    INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT '',
    duration            REAL NOT NULL DEFAULT 0.0,
    engines             TEXT NOT NULL DEFAULT '[]',
    mode                TEXT NOT NULL DEFAULT '',
    mode_name           TEXT NOT NULL DEFAULT '',
    transcripts         TEXT NOT NULL DEFAULT '{}',
    result              TEXT NOT NULL DEFAULT '',
    model_used          TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'success',
    stt_engine          TEXT NOT NULL DEFAULT '',
    llm_prompt_tokens   INTEGER NOT NULL DEFAULT 0,
    llm_completion_tokens INTEGER NOT NULL DEFAULT 0,
    uploaded_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_history_machine ON recording_history(machine_code);
CREATE INDEX IF NOT EXISTS idx_history_uploaded ON recording_history(uploaded_at);
CREATE INDEX IF NOT EXISTS idx_history_client_id ON recording_history(machine_code, client_record_id);
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
    # Add last_heartbeat column if missing (migration for existing DB)
    try:
        conn.execute("SELECT last_heartbeat FROM machines LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE machines ADD COLUMN last_heartbeat TEXT DEFAULT ''")
    # Add system_info column if missing
    try:
        conn.execute("SELECT system_info FROM machines LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE machines ADD COLUMN system_info TEXT DEFAULT ''")
    conn.commit()
    conn.close()
