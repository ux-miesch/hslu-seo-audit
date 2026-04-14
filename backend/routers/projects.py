from __future__ import annotations
import asyncio
import json
import re
from typing import Optional
from urllib.parse import urlparse, urljoin

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.database import get_db
from backend.audit_runner import run_checks

router = APIRouter(prefix="/projects", tags=["projects"])

MAX_CRAWL_PAGES = 200


class ProjectCreate(BaseModel):
    name: str
    root_url: str
    page_type: Optional[str] = None
    language: Optional[str] = None


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[äÄ]", "ae", slug)
    slug = re.sub(r"[öÖ]", "oe", slug)
    slug = re.sub(r"[üÜ]", "ue", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

async def _crawl(project_id: int, root_url: str) -> None:
    """BFS-Crawl ab root_url, max MAX_CRAWL_PAGES Seiten, gleiche Domain."""
    parsed_root = urlparse(root_url)
    root_path_prefix = parsed_root.path.rstrip("/")
    print(f"[CRAWL] Start: {root_url} | netloc={parsed_root.netloc} | prefix={root_path_prefix}", flush=True)

    def _normalise(u: str) -> str:
        """Trailing slash entfernen – ausser bei root_url selbst."""
        stripped = u.rstrip("/")
        return stripped if stripped else u

    canonical_root = _normalise(root_url.split("#")[0])

    visited: set[str] = set()
    queue: list[str] = [canonical_root]
    found: list[str] = []

    async with httpx.AsyncClient(
        timeout=10,
        follow_redirects=True,
        headers={"User-Agent": "HSLU-SEO-Audit-Bot/1.0"},
    ) as client:
        while queue and len(found) < MAX_CRAWL_PAGES:
            url = queue.pop(0)
            url = _normalise(url)
            if url in visited:
                continue
            visited.add(url)

            try:
                resp = await client.get(url)
                final_url = _normalise(str(resp.url).split("#")[0])
                print(f"[CRAWL] GET {url} -> {resp.status_code} | final={final_url} | CT={resp.headers.get('content-type','')[:40]}", flush=True)
                if resp.status_code != 200:
                    continue
                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type:
                    continue
                soup = BeautifulSoup(resp.text, "lxml")
            except Exception as exc:
                print(f"[CRAWL] FEHLER bei {url}: {exc}", flush=True)
                continue

            # Bei Redirect: finale URL verwenden und auf Duplikat prüfen
            if final_url != url:
                if final_url in visited:
                    continue
                visited.add(final_url)
                save_url = final_url
            else:
                save_url = url
            # Category- und Tag-Seiten zum Entdecken crawlen, aber nicht in pages speichern
            _path = urlparse(save_url).path
            if "/category/" not in _path and "/tag/" not in _path:
                found.append(save_url)
            links = soup.find_all("a", href=True)
            print(f"[CRAWL] Seite OK: {url} | {len(links)} Links gefunden", flush=True)

            added = 0
            for tag in links:
                href = tag["href"].strip()
                if not href or href.startswith("mailto:") or href.startswith("tel:"):
                    continue
                abs_url = _normalise(urljoin(url, href).split("#")[0])
                parsed = urlparse(abs_url)
                query_ok = (not parsed.query) or parsed.query.startswith("post_type=post")
                if (
                    parsed.netloc == parsed_root.netloc
                    and parsed.scheme in ("http", "https")
                    and parsed.path.startswith(root_path_prefix or "/")
                    and query_ok
                    and abs_url not in visited
                    and abs_url not in queue
                ):
                    queue.append(abs_url)
                    added += 1
            print(f"[CRAWL] -> {added} neue interne Links zur Queue hinzugefügt | Queue={len(queue)} | found={len(found)}", flush=True)

    print(f"[CRAWL] Fertig: {len(found)} Seiten gefunden -> speichere in DB", flush=True)
    db = get_db()
    try:
        db.execute("DELETE FROM pages WHERE project_id = ?", (project_id,))
        for url in found:
            db.execute(
                "INSERT INTO pages (project_id, url) VALUES (?, ?)",
                (project_id, url),
            )
        db.execute(
            "UPDATE projects SET last_crawled_at = datetime('now') WHERE id = ?",
            (project_id,),
        )
        db.commit()
        print(f"[CRAWL] DB-Commit OK: {len(found)} pages für project_id={project_id}", flush=True)
    finally:
        db.close()


async def _audit(project_id: int, language: Optional[str], mode_weights: dict) -> None:
    """Führt run_checks() für alle pages parallel aus (max 5 gleichzeitig)."""
    db = get_db()
    try:
        pages = db.execute(
            "SELECT id, url FROM pages WHERE project_id = ?", (project_id,)
        ).fetchall()
    finally:
        db.close()

    sem = asyncio.Semaphore(5)

    async def _audit_one(page_id: int, url: str) -> None:
        async with sem:
            try:
                results = await asyncio.wait_for(
                    run_checks(url, language=language, mode_weights=mode_weights),
                    timeout=90,
                )
            except Exception:
                results = None
            if results is None:
                return
            scores = [
                v["score"]
                for v in results.values()
                if isinstance(v, dict) and "score" in v
            ]
            avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
            db = get_db()
            try:
                db.execute(
                    "INSERT INTO audit_results (page_id, score, results_json) VALUES (?, ?, ?)",
                    (page_id, avg_score, json.dumps(results)),
                )
                db.commit()
            finally:
                db.close()

    await asyncio.gather(*[_audit_one(p["id"], p["url"]) for p in pages])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/", status_code=201)
async def create_project(body: ProjectCreate, background_tasks: BackgroundTasks):
    slug = _slugify(body.name)
    db = get_db()
    try:
        db.execute(
            """
            INSERT INTO projects (name, slug, root_url, page_type, language)
            VALUES (?, ?, ?, ?, ?)
            """,
            (body.name, slug, body.root_url, body.page_type, body.language),
        )
        db.commit()
        row = db.execute(
            "SELECT * FROM projects WHERE slug = ?", (slug,)
        ).fetchone()
        project = dict(row)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        db.close()

    background_tasks.add_task(_crawl, project["id"], body.root_url)
    return {**project, "crawl_status": "started"}


@router.get("/")
def list_projects():
    db = get_db()
    try:
        rows = db.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


@router.get("/{slug}")
def get_project(slug: str):
    db = get_db()
    try:
        row = db.execute(
            "SELECT * FROM projects WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
        return dict(row)
    finally:
        db.close()


@router.get("/{slug}/report")
def get_report(slug: str):
    db = get_db()
    try:
        project = db.execute(
            "SELECT * FROM projects WHERE slug = ?", (slug,)
        ).fetchone()
        if project is None:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

        rows = db.execute(
            """
            SELECT p.url,
                   ar.crawled_at,
                   ar.score,
                   ar.results_json
            FROM pages p
            JOIN audit_results ar ON ar.page_id = p.id
            WHERE p.project_id = ?
              AND ar.crawled_at = (
                  SELECT MAX(ar2.crawled_at)
                  FROM audit_results ar2
                  WHERE ar2.page_id = p.id
              )
            ORDER BY p.url
            """,
            (project["id"],),
        ).fetchall()

        return {
            "project": dict(project),
            "pages": [
                {
                    "url": r["url"],
                    "crawled_at": r["crawled_at"],
                    "score": r["score"],
                    "results": json.loads(r["results_json"]) if r["results_json"] else None,
                }
                for r in rows
            ],
        }
    finally:
        db.close()


@router.post("/{slug}/crawl", status_code=202)
async def crawl_project(slug: str, background_tasks: BackgroundTasks):
    db = get_db()
    try:
        row = db.execute(
            "SELECT id, root_url FROM projects WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
        project_id, root_url = row["id"], row["root_url"]

        # Bestehende Daten löschen
        db.execute(
            """
            DELETE FROM audit_results WHERE page_id IN (
                SELECT id FROM pages WHERE project_id = ?
            )
            """,
            (project_id,),
        )
        db.execute("DELETE FROM pages WHERE project_id = ?", (project_id,))
        db.commit()
    finally:
        db.close()

    background_tasks.add_task(_crawl, project_id, root_url)
    return {"slug": slug, "crawl_status": "started"}


@router.post("/{slug}/audit", status_code=202)
async def audit_project(slug: str, background_tasks: BackgroundTasks):
    db = get_db()
    try:
        row = db.execute(
            "SELECT id, language, page_type FROM projects WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

        page_count = db.execute(
            "SELECT COUNT(*) FROM pages WHERE project_id = ?", (row["id"],)
        ).fetchone()[0]

        if page_count == 0:
            raise HTTPException(
                status_code=409,
                detail="Keine Seiten gefunden – bitte zuerst /crawl aufrufen.",
            )

        project_id = row["id"]
        language = row["language"]
    finally:
        db.close()

    mode_weights = {"content": 60, "conversion": 40, "course": 0, "event": 0}

    background_tasks.add_task(_audit, project_id, language, mode_weights)
    return {"slug": slug, "audit_status": "started", "pages": page_count}


@router.delete("/{slug}", status_code=204)
def delete_project(slug: str):
    db = get_db()
    try:
        row = db.execute(
            "SELECT id FROM projects WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
        db.execute("DELETE FROM projects WHERE id = ?", (row["id"],))
        db.commit()
    finally:
        db.close()
