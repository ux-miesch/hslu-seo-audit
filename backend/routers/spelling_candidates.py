from __future__ import annotations
import os
import re
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database import get_global_db, get_db, db_path

router = APIRouter(prefix="/spelling-candidates", tags=["spelling"])

WHITELIST_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "whitelist.py")

VALID_STATUSES = {"neu", "whitelist", "ignorieren"}


class StatusUpdate(BaseModel):
    status: str


@router.get("/")
def list_candidates(project: Optional[str] = Query(default=None)):
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
def update_status(candidate_id: int, body: StatusUpdate):
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
def apply_whitelist():
    """Schreibt alle Einträge mit status='whitelist' in whitelist.py."""
    conn = get_global_db()
    try:
        rows = conn.execute(
            "SELECT id, word FROM spelling_candidates WHERE status = 'whitelist'"
        ).fetchall()
        words = [r["word"].lower().strip() for r in rows if r["word"]]
        ids   = [r["id"] for r in rows]
    finally:
        conn.close()

    if not words:
        return {"added": 0, "words": []}

    # whitelist.py einlesen
    with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Bestehende Einträge aus der Menge extrahieren um Duplikate zu vermeiden
    match = re.search(r"SPELLING_WHITELIST\s*=\s*\{([^}]*)\}", content, re.DOTALL)
    if not match:
        raise HTTPException(status_code=500, detail="SPELLING_WHITELIST nicht in whitelist.py gefunden")

    existing_raw = match.group(1)
    existing = set(re.findall(r'"([^"]+)"', existing_raw))
    new_words = [w for w in words if w not in existing]

    if new_words:
        new_entries = "    " + ",\n    ".join(f'"{w}"' for w in new_words) + ","
        # Einfügen vor der schliessenden } der Menge
        updated_content = content[:match.start(1)] + match.group(1).rstrip() + "\n" + new_entries + "\n" + content[match.end(1):]
        with open(WHITELIST_PATH, "w", encoding="utf-8") as f:
            f.write(updated_content)

    # SPELLING_WHITELIST im laufenden Prozess nachladen
    import importlib
    import whitelist as _wl
    importlib.reload(_wl)
    from checks import spelling as _sp
    importlib.reload(_sp)

    return {"added": len(new_words), "words": new_words}
