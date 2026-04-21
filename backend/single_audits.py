from __future__ import annotations
import os
import sqlite3

from backend.database import DB_BASE

SINGLE_AUDITS_DB_PATH = os.path.join(DB_BASE, "single-audits.db")


def get_single_audits_db() -> sqlite3.Connection:
    conn = sqlite3.connect(SINGLE_AUDITS_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_single_audits_db() -> None:
    conn = get_single_audits_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS single_audits (
            id         TEXT PRIMARY KEY,
            url        TEXT NOT NULL,
            result     TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def cleanup_expired() -> None:
    conn = get_single_audits_db()
    try:
        conn.execute("DELETE FROM single_audits WHERE expires_at < datetime('now')")
        conn.commit()
    finally:
        conn.close()
