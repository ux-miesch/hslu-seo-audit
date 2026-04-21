from __future__ import annotations
import os
import sqlite3

_DIR = os.path.dirname(os.path.abspath(__file__))
DB_BASE = os.environ.get("DB_PATH", _DIR)
PROJECTS_DIR = os.path.join(DB_BASE, "projects")


def db_path(slug: str) -> str:
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    return os.path.join(PROJECTS_DIR, f"{slug}.db")


def get_db(slug: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(slug))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(slug: str) -> None:
    conn = get_db(slug)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            name               TEXT    NOT NULL,
            slug               TEXT    NOT NULL UNIQUE,
            root_url           TEXT    NOT NULL,
            page_type          TEXT,
            language           TEXT,
            created_at         TEXT    NOT NULL DEFAULT (datetime('now')),
            last_crawled_at    TEXT,
            schedule           TEXT,
            notification_email TEXT,
            max_pages          INTEGER NOT NULL DEFAULT 20,
            project_type       TEXT    NOT NULL DEFAULT 'website'
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


def migrate_db(slug: str) -> None:
    """Fügt fehlende Spalten zu bestehenden Projekt-DBs hinzu."""
    conn = get_db(slug)
    try:
        for col, coltype, default in [
            ("schedule",           "TEXT",    "NULL"),
            ("notification_email", "TEXT",    "NULL"),
            ("max_pages",          "INTEGER", "20"),
            ("project_type",       "TEXT",    "'website'"),
        ]:
            try:
                conn.execute(f"ALTER TABLE projects ADD COLUMN {col} {coltype} DEFAULT {default}")
                conn.commit()
            except Exception:
                pass  # Spalte existiert bereits
    finally:
        conn.close()


def migrate_all() -> None:
    """Migriert alle bestehenden Projekt-DBs."""
    if not os.path.isdir(PROJECTS_DIR):
        return
    for fname in os.listdir(PROJECTS_DIR):
        if fname.endswith(".db"):
            try:
                migrate_db(fname[:-3])
            except Exception:
                pass


GLOBAL_DB_PATH = os.path.join(DB_BASE, "spelling.db")


def get_global_db() -> sqlite3.Connection:
    conn = sqlite3.connect(GLOBAL_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_global_db() -> None:
    conn = get_global_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS spelling_candidates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            word        TEXT NOT NULL,
            message     TEXT,
            rule_id     TEXT,
            url         TEXT,
            status      TEXT DEFAULT 'neu',
            first_seen  TEXT,
            last_seen   TEXT,
            UNIQUE(word, rule_id)
        );

        CREATE TABLE IF NOT EXISTS tokens (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            token       TEXT NOT NULL UNIQUE,
            label       TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            usage_count INTEGER NOT NULL DEFAULT 0,
            last_used   TEXT
        );
    """)
    conn.commit()
    conn.close()


def list_all_projects() -> list[dict]:
    """Liest alle Projekt-DBs aus PROJECTS_DIR und gibt ihre Metadaten zurück."""
    if not os.path.isdir(PROJECTS_DIR):
        return []
    results = []
    for fname in os.listdir(PROJECTS_DIR):
        if not fname.endswith(".db"):
            continue
        slug = fname[:-3]
        try:
            conn = get_db(slug)
            row = conn.execute("SELECT * FROM projects LIMIT 1").fetchone()
            conn.close()
            if row:
                results.append(dict(row))
        except Exception:
            continue
    results.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return results
