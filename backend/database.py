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
    # Auto-repair: wenn projects-Tabelle fehlt (korrupte/leere DB), Schema neu anlegen
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "projects" not in tables:
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
                project_type       TEXT    NOT NULL DEFAULT 'website',
                project_token      TEXT    DEFAULT NULL,
                current_package    INTEGER NOT NULL DEFAULT 0,
                total_packages     INTEGER NOT NULL DEFAULT 0,
                audit_status       TEXT    DEFAULT NULL
            );
            CREATE TABLE IF NOT EXISTS pages (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id     INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                url            TEXT    NOT NULL,
                content_hash   TEXT    DEFAULT NULL,
                audit_skipped  INTEGER DEFAULT 0
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
            project_type       TEXT    NOT NULL DEFAULT 'website',
            project_token      TEXT    DEFAULT NULL,
            current_package    INTEGER NOT NULL DEFAULT 0,
            total_packages     INTEGER NOT NULL DEFAULT 0,
            audit_status       TEXT    DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS pages (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id     INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            url            TEXT    NOT NULL,
            content_hash   TEXT    DEFAULT NULL,
            audit_skipped  INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS audit_results (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id      INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            crawled_at   TEXT    NOT NULL DEFAULT (datetime('now')),
            score        REAL,
            results_json TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_pages_project_id        ON pages(project_id);
        CREATE INDEX IF NOT EXISTS idx_pages_url               ON pages(url);
        CREATE INDEX IF NOT EXISTS idx_audit_results_page_id   ON audit_results(page_id);
        CREATE INDEX IF NOT EXISTS idx_audit_results_crawled_at ON audit_results(crawled_at);
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
            ("project_token",      "TEXT",    "NULL"),
        ]:
            try:
                conn.execute(f"ALTER TABLE projects ADD COLUMN {col} {coltype} DEFAULT {default}")
                conn.commit()
            except Exception:
                pass  # Spalte existiert bereits
        for col, coltype, default in [
            ("current_package", "INTEGER", "0"),
            ("total_packages",  "INTEGER", "0"),
            ("audit_status",    "TEXT",    "NULL"),
        ]:
            try:
                conn.execute(f"ALTER TABLE projects ADD COLUMN {col} {coltype} DEFAULT {default}")
                conn.commit()
            except Exception:
                pass
        # Indexes (idempotent dank IF NOT EXISTS)
        for sql in [
            "CREATE INDEX IF NOT EXISTS idx_pages_project_id        ON pages(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_pages_url               ON pages(url)",
            "CREATE INDEX IF NOT EXISTS idx_audit_results_page_id   ON audit_results(page_id)",
            "CREATE INDEX IF NOT EXISTS idx_audit_results_crawled_at ON audit_results(crawled_at)",
        ]:
            try:
                conn.execute(sql)
                conn.commit()
            except Exception:
                pass
        for col, coltype, default in [
            ("content_hash",  "TEXT",    "NULL"),
            ("audit_skipped", "INTEGER", "0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE pages ADD COLUMN {col} {coltype} DEFAULT {default}")
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


def migrate_all_schema() -> None:
    """Nur ALTER TABLE – keine Indexes. Schnell genug für den Startup."""
    if not os.path.isdir(PROJECTS_DIR):
        return
    for fname in os.listdir(PROJECTS_DIR):
        if not fname.endswith(".db"):
            continue
        slug = fname[:-3]
        try:
            conn = get_db(slug)
            try:
                for col, coltype, default in [
                    ("schedule",           "TEXT",    "NULL"),
                    ("notification_email", "TEXT",    "NULL"),
                    ("max_pages",          "INTEGER", "20"),
                    ("project_type",       "TEXT",    "'website'"),
                    ("project_token",      "TEXT",    "NULL"),
                    ("current_package",    "INTEGER", "0"),
                    ("total_packages",     "INTEGER", "0"),
                    ("audit_status",       "TEXT",    "NULL"),
                ]:
                    try:
                        conn.execute(f"ALTER TABLE projects ADD COLUMN {col} {coltype} DEFAULT {default}")
                        conn.commit()
                    except Exception:
                        pass
                for col, coltype, default in [
                    ("content_hash",  "TEXT",    "NULL"),
                    ("audit_skipped", "INTEGER", "0"),
                ]:
                    try:
                        conn.execute(f"ALTER TABLE pages ADD COLUMN {col} {coltype} DEFAULT {default}")
                        conn.commit()
                    except Exception:
                        pass
            finally:
                conn.close()
        except Exception:
            pass


async def migrate_all_indexes() -> None:
    """Erstellt fehlende Indexes gestaffelt im Hintergrund (kein Startup-Block)."""
    import asyncio
    if not os.path.isdir(PROJECTS_DIR):
        return
    for fname in os.listdir(PROJECTS_DIR):
        if not fname.endswith(".db"):
            continue
        slug = fname[:-3]
        try:
            conn = get_db(slug)
            try:
                for sql in [
                    "CREATE INDEX IF NOT EXISTS idx_pages_project_id        ON pages(project_id)",
                    "CREATE INDEX IF NOT EXISTS idx_pages_url               ON pages(url)",
                    "CREATE INDEX IF NOT EXISTS idx_audit_results_page_id   ON audit_results(page_id)",
                    "CREATE INDEX IF NOT EXISTS idx_audit_results_crawled_at ON audit_results(crawled_at)",
                ]:
                    try:
                        conn.execute(sql)
                        conn.commit()
                    except Exception:
                        pass
            finally:
                conn.close()
        except Exception:
            pass
        await asyncio.sleep(2)  # Gestaffelt – kein RAM-Spike


GLOBAL_DB_PATH = os.path.join(DB_BASE, "spelling.db")


def get_global_db() -> sqlite3.Connection:
    conn = sqlite3.connect(GLOBAL_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Auto-migration: spelling_whitelist-Tabelle anlegen falls fehlend
    conn.execute("""
        CREATE TABLE IF NOT EXISTS spelling_whitelist (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            word       TEXT NOT NULL UNIQUE,
            added_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
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

        CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS spelling_whitelist (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            word       TEXT NOT NULL UNIQUE,
            added_at   TEXT NOT NULL DEFAULT (datetime('now'))
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


def list_all_projects_summary() -> list[dict]:
    """Liest alle Projekt-DBs mit aggregierten Audit-Daten – ein Query pro DB, kein N+1."""
    if not os.path.isdir(PROJECTS_DIR):
        return []
    results = []
    for fname in os.listdir(PROJECTS_DIR):
        if not fname.endswith(".db"):
            continue
        slug = fname[:-3]
        try:
            conn = get_db(slug)
            row = conn.execute("""
                SELECT
                    p.slug,
                    p.name,
                    p.root_url,
                    p.project_type,
                    p.schedule,
                    p.last_crawled_at,
                    p.created_at,
                    p.project_token,
                    COUNT(DISTINCT pa.id)      AS page_count,
                    ROUND(AVG(ar.score), 1)    AS avg_score
                FROM projects p
                LEFT JOIN pages pa ON pa.project_id = p.id
                LEFT JOIN audit_results ar ON ar.page_id = pa.id
                GROUP BY p.id
            """).fetchone()
            conn.close()
            if row:
                results.append(dict(row))
        except Exception:
            continue
    results.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return results
