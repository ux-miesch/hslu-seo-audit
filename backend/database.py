from __future__ import annotations
import os
import sqlite3

DB_PATH = os.environ.get("DB_PATH", "hslu_seo.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            slug          TEXT    NOT NULL UNIQUE,
            root_url      TEXT    NOT NULL,
            page_type     TEXT,
            language      TEXT,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            last_crawled_at TEXT
        );

        CREATE TABLE IF NOT EXISTS pages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            url        TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_results (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id      INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            crawled_at   TEXT    NOT NULL DEFAULT (datetime('now')),
            score        REAL,
            results_json TEXT
        );
    """)
    conn.commit()
    conn.close()
