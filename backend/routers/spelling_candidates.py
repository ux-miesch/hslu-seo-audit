from __future__ import annotations
import os
import re
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Header
from pydantic import BaseModel

from backend.database import get_global_db, get_db, db_path

router = APIRouter(prefix="/spelling-candidates", tags=["spelling"])

WHITELIST_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "whitelist.py")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

VALID_STATUSES = {"neu", "whitelist", "ignorieren"}


def _require_admin(x_admin_password: Optional[str]) -> None:
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="ADMIN_PASSWORD nicht konfiguriert.")
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Ungültiger Zugang.")


def _verify_project_token(slug: str, token: Optional[str]) -> None:
    if not token:
        raise HTTPException(status_code=401, detail="Token fehlt.")
    if not os.path.exists(db_path(slug)):
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    db = get_db(slug)
    try:
        row = db.execute("SELECT project_token FROM projects WHERE slug = ?", (slug,)).fetchone()
    finally:
        db.close()
    if row is None or not row["project_token"] or token != row["project_token"]:
        raise HTTPException(status_code=401, detail="Ungültiger Token.")


class StatusUpdate(BaseModel):
    status: str


@router.get("/")
def list_candidates(
    project: Optional[str] = Query(default=None),
    token: Optional[str] = Query(default=None),
    x_admin_password: Optional[str] = Header(default=None),
):
    if project:
        _verify_project_token(project, token)
    else:
        _require_admin(x_admin_password)

    conn = get_global_db()
    try:
        if project:
            if not os.path.exists(db_path(project)):
                raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
            proj_conn = get_db(project)
            try:
                proj_row = proj_conn.execute(
                    "SELECT id FROM projects WHERE slug = ?", (project,)
                ).fetchone()
                if proj_row is None:
                    raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
                page_rows = proj_conn.execute(
                    "SELECT url FROM pages WHERE project_id = ?", (proj_row["id"],)
                ).fetchall()
                urls = [r["url"] for r in page_rows]
            finally:
                proj_conn.close()
            if not urls:
                return []
            placeholders = ",".join("?" * len(urls))
            rows = conn.execute(
                f"SELECT * FROM spelling_candidates WHERE url IN ({placeholders}) ORDER BY last_seen DESC",
                urls,
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM spelling_candidates ORDER BY last_seen DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.patch("/{candidate_id}")
def update_status(
    candidate_id: int,
    body: StatusUpdate,
    project: Optional[str] = Query(default=None),
    token: Optional[str] = Query(default=None),
    x_admin_password: Optional[str] = Header(default=None),
):
    if project:
        _verify_project_token(project, token)
        # Sicherstellen dass der Eintrag zu einer Seite dieses Projekts gehört
        proj_conn = get_db(project)
        try:
            proj_row = proj_conn.execute("SELECT id FROM projects WHERE slug = ?", (project,)).fetchone()
            if proj_row is None:
                raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
            page_rows = proj_conn.execute(
                "SELECT url FROM pages WHERE project_id = ?", (proj_row["id"],)
            ).fetchall()
            project_urls = {r["url"] for r in page_rows}
        finally:
            proj_conn.close()
        gconn = get_global_db()
        try:
            cand = gconn.execute(
                "SELECT url FROM spelling_candidates WHERE id = ?", (candidate_id,)
            ).fetchone()
        finally:
            gconn.close()
        if cand is None:
            raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
        if cand["url"] not in project_urls:
            raise HTTPException(status_code=403, detail="Kein Zugriff auf diesen Eintrag.")
    else:
        _require_admin(x_admin_password)

    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Ungültiger Status: {body.status}")
    conn = get_global_db()
    try:
        row = conn.execute(
            "SELECT id FROM spelling_candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
        conn.execute(
            "UPDATE spelling_candidates SET status = ? WHERE id = ?",
            (body.status, candidate_id),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM spelling_candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        return dict(updated)
    finally:
        conn.close()


@router.post("/apply-whitelist")
def apply_whitelist(
    project: Optional[str] = Query(default=None),
    token: Optional[str] = Query(default=None),
    x_admin_password: Optional[str] = Header(default=None),
):
    """Schreibt alle Einträge mit status='whitelist' in die spelling_whitelist-Tabelle der DB."""
    if project:
        _verify_project_token(project, token)
    else:
        _require_admin(x_admin_password)

    conn = get_global_db()
    try:
        rows = conn.execute(
            "SELECT word FROM spelling_candidates WHERE status = 'whitelist'"
        ).fetchall()
        # Deduplizieren (gleiche Wörter mit verschiedenen rule_ids)
        words = list(dict.fromkeys(r["word"].lower().strip() for r in rows if r["word"]))

        if not words:
            return {"added": 0, "words": []}

        # Bereits in DB-Whitelist vorhandene Wörter ermitteln
        existing = {
            r["word"] for r in conn.execute("SELECT word FROM spelling_whitelist").fetchall()
        }
        new_words = [w for w in words if w not in existing]

        # Neue Wörter einfügen
        for w in new_words:
            conn.execute(
                "INSERT OR IGNORE INTO spelling_whitelist (word) VALUES (?)", (w,)
            )
        conn.commit()
    finally:
        conn.close()

    return {"added": len(new_words), "words": new_words}
