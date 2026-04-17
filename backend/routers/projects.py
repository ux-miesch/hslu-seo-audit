from __future__ import annotations
import asyncio
import json
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from urllib.parse import urlparse, urljoin

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.database import get_db, init_db, list_all_projects, db_path
from backend.audit_runner import run_checks

router = APIRouter(prefix="/projects", tags=["projects"])

MAX_CRAWL_PAGES = 200

REPORT_BASE_URL = os.getenv("REPORT_BASE_URL", "https://ux-miesch.github.io/hslu-seo-audit")

SMTP_HOST = "mail.metanet.ch"
SMTP_PORT = 465
SMTP_USER = "seo@miesch.com"
SMTP_PASS = "SEO785235.ch"


class ProjectCreate(BaseModel):
    name: str
    root_url: str
    page_type: Optional[str] = None
    language: Optional[str] = None
    max_pages: int = 20
    notification_email: Optional[str] = None
    project_type: str = "website"  # "website" oder "blog"


class ScheduleUpdate(BaseModel):
    schedule: Optional[str] = None  # "weekly", "monthly" oder None


def _mode_weights_for(project_type: Optional[str]) -> dict:
    """Leitet mode_weights aus project_type ab.
    website → conversion-Checks (Fact-Liste, CTA, Kontakt, …)
    blog    → content-Checks (Autor, Datum, Verlinkung, Trust-Signale)
    """
    if project_type == "blog":
        return {"content": 100, "conversion": 0, "course": 0, "event": 0}
    return {"content": 0, "conversion": 100, "course": 0, "event": 0}  # default: website


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

def _send_notification_email(to: str, project_name: str, slug: str, page_count: int, avg_score: float) -> None:
    """Sendet E-Mail-Benachrichtigung nach abgeschlossenem Audit."""
    report_url = f"{REPORT_BASE_URL}/report.html?project={slug}"
    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_USER
    msg["To"] = to
    msg["Subject"] = f"SEO Audit abgeschlossen – {project_name}"

    html_body = f"""
    <html><body style="font-family:Verdana,sans-serif;font-size:13px;color:#1a1a1a;">
    <p>Der SEO Audit für das Projekt <strong>{project_name}</strong> ist abgeschlossen.</p>
    <ul>
      <li>Auditierte Seiten: <strong>{page_count}</strong></li>
      <li>Durchschnittsscore: <strong>{avg_score}</strong> / 100</li>
    </ul>
    <p><a href="{report_url}" style="background:#77C5D8;color:#000;padding:8px 16px;text-decoration:none;font-weight:700;">Rapport anzeigen →</a></p>
    </body></html>
    """
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.sendmail(SMTP_USER, to, msg.as_string())
        print(f"[EMAIL] Benachrichtigung gesendet an {to} ({project_name})", flush=True)
    except Exception as exc:
        print(f"[EMAIL] Fehler beim Senden: {exc}", flush=True)


async def _crawl(project_id: int, root_url: str, slug: str, max_pages: int = 20) -> None:
    """BFS-Crawl ab root_url, max max_pages Seiten, gleiche Domain."""
    parsed_root = urlparse(root_url)
    root_path_prefix = parsed_root.path.rstrip("/")
    print(f"[CRAWL] Start: {root_url} | netloc={parsed_root.netloc} | prefix={root_path_prefix}", flush=True)

    def _normalise(u: str) -> str:
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
        while queue and len(found) < max_pages:
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

            if final_url != url:
                if final_url in visited:
                    continue
                visited.add(final_url)
                save_url = final_url
            else:
                save_url = url

            _path = urlparse(save_url).path
            if "/category/" not in _path and "/tag/" not in _path and "download" not in _path:
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
                    and "download" not in parsed.path
                    and abs_url not in visited
                    and abs_url not in queue
                ):
                    queue.append(abs_url)
                    added += 1
            print(f"[CRAWL] -> {added} neue interne Links zur Queue | Queue={len(queue)} | found={len(found)}", flush=True)

    print(f"[CRAWL] Fertig: {len(found)} Seiten gefunden -> speichere in DB ({slug}.db)", flush=True)
    db = get_db(slug)
    try:
        db.execute("DELETE FROM pages WHERE project_id = ?", (project_id,))
        for url in found:
            db.execute("INSERT INTO pages (project_id, url) VALUES (?, ?)", (project_id, url))
        db.execute("UPDATE projects SET last_crawled_at = datetime('now') WHERE id = ?", (project_id,))
        db.commit()
        print(f"[CRAWL] DB-Commit OK: {len(found)} pages für project_id={project_id}", flush=True)
    finally:
        db.close()


async def _audit(project_id: int, language: Optional[str], mode_weights: dict, slug: str) -> None:
    """Führt run_checks() für alle pages parallel aus (max 5 gleichzeitig)."""
    db = get_db(slug)
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
            except Exception as exc:
                print(f"[AUDIT] FEHLER {url}: {exc}", flush=True)
                results = None
            if results is None:
                return
            scores = [
                v["score"]
                for v in results.values()
                if isinstance(v, dict) and "score" in v
            ]
            avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
            db = get_db(slug)
            try:
                db.execute(
                    "INSERT INTO audit_results (page_id, score, results_json) VALUES (?, ?, ?)",
                    (page_id, avg_score, json.dumps(results)),
                )
                db.commit()
            finally:
                db.close()

    await asyncio.gather(*[_audit_one(p["id"], p["url"]) for p in pages])

    # E-Mail-Benachrichtigung: immer senden wenn notification_email gesetzt ist
    db2 = get_db(slug)
    try:
        proj = db2.execute(
            "SELECT name, notification_email FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if proj and proj["notification_email"]:
            # Nur jeweils das neueste Audit-Ergebnis pro Seite verwenden
            score_rows = db2.execute(
                """SELECT ar.score
                   FROM audit_results ar
                   JOIN pages p ON ar.page_id = p.id
                   WHERE p.project_id = ?
                     AND ar.crawled_at = (
                         SELECT MAX(ar2.crawled_at)
                         FROM audit_results ar2
                         WHERE ar2.page_id = ar.page_id
                     )""",
                (project_id,),
            ).fetchall()
            page_count = len(score_rows)
            scores = [r["score"] for r in score_rows if r["score"] is not None]
            avg = round(sum(scores) / len(scores), 1) if scores else 0.0
            _send_notification_email(
                to=proj["notification_email"],
                project_name=proj["name"],
                slug=slug,
                page_count=page_count,
                avg_score=avg,
            )
    finally:
        db2.close()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/", status_code=201)
async def create_project(body: ProjectCreate, background_tasks: BackgroundTasks):
    slug = _slugify(body.name)

    if os.path.exists(db_path(slug)):
        raise HTTPException(status_code=400, detail=f"Projekt '{slug}' existiert bereits.")

    init_db(slug)
    db = get_db(slug)
    try:
        db.execute(
            "INSERT INTO projects (name, slug, root_url, page_type, language, notification_email, max_pages, project_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (body.name, slug, body.root_url, body.page_type, body.language, body.notification_email, body.max_pages, body.project_type),
        )
        db.commit()
        row = db.execute("SELECT * FROM projects WHERE slug = ?", (slug,)).fetchone()
        project = dict(row)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        db.close()

    return {**project, "crawl_status": "pending"}


@router.get("/")
def list_projects():
    return list_all_projects()


@router.get("/{slug}")
def get_project(slug: str):
    db = get_db(slug)
    try:
        row = db.execute("SELECT * FROM projects WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
        return dict(row)
    finally:
        db.close()


@router.get("/{slug}/pages")
def get_pages(slug: str):
    db = get_db(slug)
    try:
        project = db.execute("SELECT id FROM projects WHERE slug = ?", (slug,)).fetchone()
        if project is None:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
        rows = db.execute(
            """
            SELECT p.id,
                   p.url,
                   ar.score,
                   ar.crawled_at AS last_audited_at
            FROM pages p
            LEFT JOIN audit_results ar ON ar.page_id = p.id
              AND ar.crawled_at = (
                  SELECT MAX(ar2.crawled_at)
                  FROM audit_results ar2
                  WHERE ar2.page_id = p.id
              )
            WHERE p.project_id = ?
            ORDER BY p.url
            """,
            (project["id"],),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


@router.get("/{slug}/report")
def get_report(slug: str):
    db = get_db(slug)
    try:
        project = db.execute("SELECT * FROM projects WHERE slug = ?", (slug,)).fetchone()
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
    db = get_db(slug)
    try:
        row = db.execute("SELECT id, root_url, max_pages FROM projects WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
        project_id, root_url = row["id"], row["root_url"]
        max_pages = row["max_pages"] or 20
        db.execute(
            "DELETE FROM audit_results WHERE page_id IN (SELECT id FROM pages WHERE project_id = ?)",
            (project_id,),
        )
        db.execute("DELETE FROM pages WHERE project_id = ?", (project_id,))
        db.execute("UPDATE projects SET last_crawled_at = NULL WHERE id = ?", (project_id,))
        db.commit()
    finally:
        db.close()

    background_tasks.add_task(_crawl, project_id, root_url, slug, max_pages)
    return {"slug": slug, "crawl_status": "started"}


@router.post("/{slug}/audit", status_code=202)
async def audit_project(slug: str, background_tasks: BackgroundTasks):
    db = get_db(slug)
    try:
        row = db.execute(
            "SELECT id, language, page_type, project_type FROM projects WHERE slug = ?", (slug,)
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
        project_type = row["project_type"] or "website"
    finally:
        db.close()

    mode_weights = _mode_weights_for(project_type)
    background_tasks.add_task(_audit, project_id, language, mode_weights, slug)
    return {"slug": slug, "audit_status": "started", "pages": page_count}


@router.patch("/{slug}/schedule", status_code=200)
def update_schedule(slug: str, body: ScheduleUpdate):
    db = get_db(slug)
    try:
        row = db.execute("SELECT id FROM projects WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
        db.execute("UPDATE projects SET schedule = ? WHERE slug = ?", (body.schedule, slug))
        db.commit()
    finally:
        db.close()

    from backend.scheduler import update_project_schedule
    update_project_schedule(slug, body.schedule)

    return {"slug": slug, "schedule": body.schedule}


@router.delete("/{slug}", status_code=204)
def delete_project(slug: str):
    path = db_path(slug)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    # APScheduler-Job entfernen falls vorhanden
    try:
        from backend.scheduler import update_project_schedule
        update_project_schedule(slug, None)
    except Exception:
        pass

    os.remove(path)
