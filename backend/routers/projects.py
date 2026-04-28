from __future__ import annotations
import asyncio
import base64
import gc
import json
import os
import zlib
import re
import secrets as _secrets
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from urllib.parse import urlparse, urljoin

try:
    import psutil as _psutil
except ImportError:
    _psutil = None  # type: ignore

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import get_db, init_db, list_all_projects, db_path
from backend.audit_runner import run_checks, run_checks_with_soup
from backend.crawler import fetch_page, content_hash
from checks.broken_links import check_broken_links

router = APIRouter(prefix="/projects", tags=["projects"])

MAX_CRAWL_PAGES = 200
PACKAGE_SIZE = 600  # Seiten pro Audit-Paket (für grosse Projekte)

# In-Memory-Projektstatus (wird während Crawl/Audit befüllt)
_project_state: dict = {}
# Format: slug -> {status, pages_crawled, pages_total, pages_audited, recently_audited, current_url}

REPORT_BASE_URL = os.getenv("REPORT_BASE_URL", "https://ux-miesch.github.io/hslu-seo-audit")

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")


_URL_LANG_MAP = {
    "de-ch": "de-CH", "de": "de-CH",
    "fr-ch": "fr-CH", "fr": "fr-CH",
    "it-ch": "it-CH", "it": "it-CH",
    "en-us": "en-US", "en": "en-US",
}

def _detect_language_from_url(url: str) -> Optional[str]:
    segments = urlparse(url).path.lower().split("/")
    for seg in segments:
        if seg in _URL_LANG_MAP:
            return _URL_LANG_MAP[seg]
    return None

def _detect_language_from_content(soup: BeautifulSoup) -> Optional[str]:
    try:
        from langdetect import detect, LangDetectException
        texts = [t.get_text(strip=True) for t in soup.find_all(["p", "h1", "h2", "h3", "li"]) if len(t.get_text(strip=True)) > 20]
        full_text = " ".join(texts[:50])
        if len(full_text) < 100:
            return None
        lang = detect(full_text)
        return _URL_LANG_MAP.get(lang)
    except Exception:
        return None

def _resolve_language(url: str, soup: Optional[BeautifulSoup] = None) -> Optional[str]:
    """Inhalt schlägt URL – beide Quellen kombinieren."""
    url_lang     = _detect_language_from_url(url)
    content_lang = _detect_language_from_content(soup) if soup else None
    return content_lang or url_lang


class ProjectCreate(BaseModel):
    name: str
    root_url: str
    page_type: Optional[str] = None
    language: Optional[str] = None
    max_pages: Optional[int] = None  # None = alle Seiten (bis MAX_CRAWL_PAGES)
    notification_email: Optional[str] = None
    project_type: str = "website"  # "website" oder "blog"


class ScheduleUpdate(BaseModel):
    schedule: Optional[str] = None  # "weekly", "monthly" oder None

class EmailUpdate(BaseModel):
    notification_email: Optional[str] = None


def _mode_weights_for(project_type: Optional[str]) -> dict:
    """Leitet mode_weights aus project_type ab.
    website → conversion-Checks (Fact-Liste, CTA, Kontakt, …)
    blog    → content-Checks (Autor, Datum, Verlinkung, Trust-Signale)
    """
    if project_type == "blog":
        return {"content": 100, "conversion": 0, "course": 0, "event": 0}
    return {"content": 0, "conversion": 100, "course": 0, "event": 0}  # default: website


async def _wait_for_memory(slug: str, threshold_mb: int = 150, max_wait: int = 600) -> None:
    """Wartet bis mindestens threshold_mb RAM verfügbar sind, dann GC."""
    if _psutil is None:
        gc.collect()
        return
    waited = 0
    while waited < max_wait:
        mem = _psutil.virtual_memory()
        available = mem.available / 1024 / 1024
        used = mem.used / 1024 / 1024
        print(f"[RAM] {used:.0f}MB verwendet, {available:.0f}MB verfügbar", flush=True)
        if available >= threshold_mb:
            break
        print(f"[Speicher] Nur {available:.0f}MB verfügbar – warte 15s...", flush=True)
        if slug in _project_state:
            _project_state[slug]["ram_available_mb"] = round(available)
        await asyncio.sleep(15)
        waited += 15
    gc.collect()
    if _psutil:
        available = _psutil.virtual_memory().available / 1024 / 1024
        print(f"[Speicher] {available:.0f}MB verfügbar – OK", flush=True)


def _get_ram_mb() -> Optional[float]:
    if _psutil is None:
        return None
    return _psutil.virtual_memory().available / 1024 / 1024


def _pack_results(results: dict) -> str:
    """Komprimiert results_json mit zlib+base64. Prefix 'z:' markiert komprimierte Daten."""
    compressed = zlib.compress(json.dumps(results, ensure_ascii=False).encode("utf-8"), level=6)
    return "z:" + base64.b64encode(compressed).decode("ascii")


def _unpack_results(data) -> Optional[dict]:
    """Dekomprimiert oder parst results_json – unterstützt alte (plain JSON) und neue (komprimiert) Rows."""
    if not data:
        return None
    try:
        if isinstance(data, str) and data.startswith("z:"):
            return json.loads(zlib.decompress(base64.b64decode(data[2:])).decode("utf-8"))
        if isinstance(data, (bytes, bytearray)):
            return json.loads(zlib.decompress(data).decode("utf-8"))
        return json.loads(data)
    except Exception:
        try:
            return json.loads(data) if isinstance(data, str) else None
        except Exception:
            return None


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

def _send_notification_email(to: str, project_name: str, slug: str, page_count: int, avg_score: float, spelling_count: int = 0, low_score_pages: Optional[list] = None, project_token: Optional[str] = None) -> None:
    """Sendet E-Mail-Benachrichtigung nach abgeschlossenem Audit."""
    if not SMTP_USER or not SMTP_PASS:
        print("[EMAIL] SMTP_USER/SMTP_PASS nicht gesetzt – E-Mail übersprungen.", flush=True)
        return
    token_param  = f"&token={project_token}" if project_token else ""
    report_url   = f"{REPORT_BASE_URL}/report.html?project={slug}{token_param}"
    spelling_url = f"{REPORT_BASE_URL}/spelling.html?project={slug}{token_param}"
    import email.utils
    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_USER
    msg["To"] = to
    msg["Subject"] = f"SEO-Audit {project_name} ist bereit 🎉"
    msg["Reply-To"] = SMTP_USER
    msg["Message-ID"] = email.utils.make_msgid(domain=SMTP_USER.split("@")[-1] if "@" in SMTP_USER else "hslu.ch")
    msg["Date"] = email.utils.formatdate(localtime=True)

    plain_body = (
        f"Crawl abgeschlossen: {project_name}\n\n"
        f"{page_count} Seiten geprueft | Durchschnittlicher Score: {avg_score}\n"
        f"{spelling_count} Rechtschreibfehler gefunden\n\n"
        f"Rapport anzeigen:\n{report_url}\n\n"
        f"Rechtschreibfehler anzeigen:\n{spelling_url}\n\n"
        f"Hinweis: Die obigen Links sind persoenliche Zugangslinks. "
        f"Jede Person mit diesen Links hat vollen Zugriff auf den SEO-Audit. "
        f"Bitte Links nicht oeffentlich teilen."
    )

    html_body = f"""
    <html>
    <head>
    <style>
      @media (prefers-color-scheme: dark) {{
        .btn {{ color: #1a1a1a !important; -webkit-text-fill-color: #1a1a1a !important; }}
      }}
    </style>
    </head>
    <body style="font-family:Verdana,sans-serif;font-size:13px;color:#1a1a1a;line-height:1.6;max-width:600px;">
    <p style="font-size:15px;font-weight:700;margin-bottom:12px;">Crawl abgeschlossen: {project_name}</p>
    <p style="color:#555;margin:0;">
      <strong>{page_count}</strong> Seiten geprüft &nbsp;·&nbsp; Ø Score: <strong>{avg_score}</strong><br>
      <strong>{spelling_count}</strong> Rechtschreibfehler gefunden
    </p>
    <p style="margin-top:24px;">
      <a href="{report_url}" class="btn" style="display:block;width:fit-content;background:#77C5D8;color:#1a1a1a;-webkit-text-fill-color:#1a1a1a;padding:10px 20px;text-decoration:none;font-weight:700;margin-bottom:10px;">Rapport anzeigen →</a>
      <a href="{spelling_url}" class="btn" style="display:block;width:fit-content;background:#FCC300;color:#1a1a1a;-webkit-text-fill-color:#1a1a1a;padding:10px 20px;text-decoration:none;font-weight:700;">Rechtschreibfehler anzeigen →</a>
    </p>
    <p style="margin-top:32px;padding:12px 16px;background:#f4f4f4;border-left:3px solid #ccc;font-size:11px;color:#1a1a1a;line-height:1.5;">
      <strong>Hinweis:</strong> Die obigen Links sind persönliche Zugangslinks.
      Jede Person mit diesen Links hat vollen Zugriff auf den SEO-Audit.
      Bitte Links nicht öffentlich teilen.
    </p>
    </body></html>
    """
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.sendmail(SMTP_USER, to, msg.as_string())
        print(f"[EMAIL] Benachrichtigung gesendet an {to} ({project_name})", flush=True)
    except Exception as exc:
        print(f"[EMAIL] Fehler beim Senden: {exc}", flush=True)


async def _crawl(project_id: int, root_url: str, slug: str, max_pages: Optional[int] = None) -> None:
    """BFS-Crawl ab root_url. max_pages=None/0 → kein Limit."""
    # Sicherstellen dass _project_state initialisiert ist – unabhängig ob via Endpoint oder Scheduler aufgerufen
    if slug not in _project_state:
        _project_state[slug] = {
            "status": "crawling",
            "pages_crawled": 0,
            "pages_total": 0,
            "pages_audited": 0,
            "recently_audited": [],
            "current_url": None,
        }
    try:
        await _crawl_inner(project_id, root_url, slug, max_pages)
    except Exception as exc:
        print(f"[CRAWL] FATAL ERROR für {slug}: {exc}", flush=True)
        if slug in _project_state:
            _project_state[slug]["status"] = "error"
            _project_state[slug]["error"] = str(exc)


async def _crawl_inner(project_id: int, root_url: str, slug: str, max_pages: Optional[int] = None) -> None:
    effective_max = max_pages if max_pages and max_pages > 0 else None
    parsed_root = urlparse(root_url)
    root_path_prefix = parsed_root.path.rstrip("/")
    print(f"[CRAWL] Start: {root_url} | netloc={parsed_root.netloc} | prefix={root_path_prefix} | max={effective_max}", flush=True)

    def _normalise(u: str) -> str:
        stripped = u.rstrip("/")
        return stripped if stripped else u

    canonical_root = _normalise(root_url.split("#")[0])

    visited: set[str] = set()
    queue: list[str] = [canonical_root]
    found: list[str] = []
    _lang_detected = False  # Sprache wird nur einmal aus Inhalt ermittelt

    async with httpx.AsyncClient(
        timeout=10,
        follow_redirects=True,
        headers={"User-Agent": "HSLU-SEO-Audit-Bot/1.0"},
    ) as client:
        while queue and (effective_max is None or len(found) < effective_max):
            url = queue.pop(0)
            url = _normalise(url)
            if url in visited:
                continue
            visited.add(url)

            try:
                resp = await client.get(url)
                final_url = _normalise(str(resp.url).split("#")[0])
                print(f"[CRAWL] GET {url} -> {resp.status_code} | final={final_url} | CT={resp.headers.get('content-type','')[:40]}", flush=True)
                await asyncio.sleep(1)
                if resp.status_code != 200:
                    continue
                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type:
                    continue
                soup = await asyncio.to_thread(BeautifulSoup, resp.text, "lxml")
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

            # Sprache einmalig aus erster Seite ermitteln (Inhalt schlägt URL)
            if not _lang_detected:
                detected = _resolve_language(root_url, soup)
                if detected:
                    try:
                        db = get_db(slug)
                        db.execute("UPDATE projects SET language = ? WHERE id = ?", (detected, project_id))
                        db.commit()
                        db.close()
                        print(f"[CRAWL] Sprache erkannt: {detected} für {slug}", flush=True)
                    except Exception as lang_exc:
                        print(f"[CRAWL] Sprache-Update fehlgeschlagen: {lang_exc}", flush=True)
                _lang_detected = True

            _path = urlparse(save_url).path
            if "/category/" not in _path and "/tag/" not in _path and "download" not in _path:
                found.append(save_url)
                _project_state[slug]["pages_crawled"] = len(found)
                _project_state[slug]["current_url"] = save_url

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

    _project_state[slug]["pages_total"] = len(found)
    if len(found) == 0:
        _project_state[slug]["status"] = "error"
        _project_state[slug]["error"] = "Keine Seiten gefunden – Root-URL nicht erreichbar oder keine internen Links."
        print(f"[CRAWL] Abgebrochen: 0 Seiten gefunden für {slug}", flush=True)
        return
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


async def _audit(project_id: int, language: Optional[str], mode_weights: dict, slug: str, resume_from_package: int = 0) -> None:
    """Führt run_checks() für alle pages durch. Grosse Projekte werden in Pakete aufgeteilt."""
    BATCH_SIZE = 2

    db = get_db(slug)
    try:
        pages = db.execute(
            "SELECT id, url FROM pages WHERE project_id = ?", (project_id,)
        ).fetchall()
    finally:
        db.close()

    packages = [pages[i:i + PACKAGE_SIZE] for i in range(0, len(pages), PACKAGE_SIZE)]
    total_packages = max(len(packages), 1)
    total_pages = len(pages)

    print(f"[AUDIT] Start: {total_pages} Seiten, {total_packages} Paket(e), resume_from={resume_from_package}", flush=True)
    if total_packages > 1:
        print(f"[AUDIT] {total_pages} Seiten → {total_packages} Pakete à {PACKAGE_SIZE}. Starte ab Paket {resume_from_package + 1}.", flush=True)

    _project_state[slug] = {
        "status": f"auditing_package_{resume_from_package + 1}_of_{total_packages}",
        "pages_crawled": total_pages,
        "pages_total": total_pages,
        "pages_audited": resume_from_package * PACKAGE_SIZE,
        "current_package": resume_from_package + 1,
        "total_packages": total_packages,
        "package_pages_total": len(packages[resume_from_package]) if resume_from_package < len(packages) else 0,
        "package_pages_audited": 0,
        "recently_audited": [],
        "current_url": None,
    }

    sem = asyncio.Semaphore(2)

    async def _audit_one(page_id: int, url: str) -> None:
        async with sem:
            _project_state[slug]["current_url"] = url
            print(f"[AUDIT_ONE] Start: {url}", flush=True)
            try:
                # Step 1: Fetch page to enable incremental hashing
                page = await fetch_page(url)

                if page is None:
                    # Fallback: fetch failed, run full checks via URL
                    try:
                        results = await asyncio.wait_for(
                            run_checks(url, language=language, mode_weights=mode_weights),
                            timeout=90,
                        )
                    except asyncio.TimeoutError:
                        print(f"[AUDIT] TIMEOUT {url}", flush=True)
                        results = {
                            "error": True,
                            "error_message": "Seite konnte nicht analysiert werden (Timeout nach 90 Sekunden).",
                            "score": 0,
                            "issues": [],
                            "warnings": [],
                            "passed": [],
                        }
                    except Exception as exc:
                        print(f"[AUDIT] FEHLER {url}: {exc}", flush=True)
                        results = None
                    if results is None:
                        return
                    if results.get("error"):
                        avg_score = None
                    else:
                        scores = [
                            v["score"]
                            for v in results.values()
                            if isinstance(v, dict) and "score" in v
                        ]
                        avg_score = round(sum(scores) / len(scores), 2) if scores else None
                    db = get_db(slug)
                    try:
                        db.execute(
                            "INSERT INTO audit_results (page_id, score, results_json) VALUES (?, ?, ?)",
                            (page_id, avg_score, _pack_results(results)),
                        )
                        db.commit()
                    finally:
                        db.close()
                    state = _project_state.get(slug, {})
                    state["pages_audited"] = state.get("pages_audited", 0) + 1
                    recently = state.get("recently_audited", [])
                    if avg_score is not None:
                        recently.insert(0, {"url": url, "score": round(avg_score, 1)})
                    state["recently_audited"] = recently[:5]
                    _project_state[slug] = state
                    print(f"[AUDIT_ONE] Fertig (fallback): {url} | score={avg_score} | gesamt={state['pages_audited']}", flush=True)
                    return

                soup = page["soup"]
                page = None  # Seiteninhalt sofort freigeben

                # Step 2: Compute content hash
                new_hash = content_hash(soup, url)

                # Step 3: Load stored hash from DB
                db = get_db(slug)
                try:
                    stored_row = db.execute(
                        "SELECT content_hash, audit_skipped FROM pages WHERE project_id = ? AND url = ?",
                        (project_id, url),
                    ).fetchone()
                finally:
                    db.close()

                stored_hash = stored_row["content_hash"] if stored_row else None

                if stored_hash is not None and stored_hash == new_hash:
                    # Page unchanged: only re-run broken_links
                    print(f"[AUDIT] SKIP (unchanged) {url}", flush=True)
                    try:
                        broken_links_result = await asyncio.wait_for(
                            check_broken_links(soup, url),
                            timeout=30,
                        )
                    except asyncio.TimeoutError:
                        broken_links_result = {
                            "score": 0,
                            "issues": [{"message": "Check fehlgeschlagen: Timeout"}],
                            "warnings": [],
                            "passed": [],
                        }
                    except Exception as exc:
                        broken_links_result = {
                            "score": 0,
                            "issues": [{"message": f"Check fehlgeschlagen: {str(exc)}"}],
                            "warnings": [],
                            "passed": [],
                        }

                    # Load most recent old results_json
                    db = get_db(slug)
                    try:
                        old_row = db.execute(
                            """SELECT ar.results_json
                               FROM audit_results ar
                               WHERE ar.page_id = ?
                               ORDER BY ar.crawled_at DESC
                               LIMIT 1""",
                            (page_id,),
                        ).fetchone()
                    finally:
                        db.close()

                    if old_row and old_row["results_json"]:
                        old_results = _unpack_results(old_row["results_json"])
                    else:
                        old_results = {}

                    old_results["broken_links"] = broken_links_result

                    scores = [
                        v["score"]
                        for v in old_results.values()
                        if isinstance(v, dict) and "score" in v
                    ]
                    avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0

                    db = get_db(slug)
                    try:
                        db.execute(
                            "INSERT INTO audit_results (page_id, score, results_json) VALUES (?, ?, ?)",
                            (page_id, avg_score, _pack_results(old_results)),
                        )
                        db.execute(
                            "UPDATE pages SET audit_skipped = 1 WHERE url = ? AND project_id = ?",
                            (url, project_id),
                        )
                        db.commit()
                    finally:
                        db.close()

                else:
                    # Page changed or new: run full checks with pre-fetched soup
                    print(f"[AUDIT] FULL (new/changed) {url}", flush=True)
                    try:
                        results = await asyncio.wait_for(
                            run_checks_with_soup(soup, url, language=language, mode_weights=mode_weights),
                            timeout=90,
                        )
                    except asyncio.TimeoutError:
                        print(f"[AUDIT] TIMEOUT {url}", flush=True)
                        results = {
                            "error": True,
                            "error_message": "Seite konnte nicht analysiert werden (Timeout nach 90 Sekunden).",
                            "score": 0,
                            "issues": [],
                            "warnings": [],
                            "passed": [],
                        }
                    except Exception as exc:
                        print(f"[AUDIT] FEHLER {url}: {exc}", flush=True)
                        results = None
                    if results is None:
                        return

                    if results.get("error"):
                        avg_score = None
                    else:
                        scores = [
                            v["score"]
                            for v in results.values()
                            if isinstance(v, dict) and "score" in v
                        ]
                        avg_score = round(sum(scores) / len(scores), 2) if scores else None

                    db = get_db(slug)
                    try:
                        db.execute(
                            "INSERT INTO audit_results (page_id, score, results_json) VALUES (?, ?, ?)",
                            (page_id, avg_score, _pack_results(results)),
                        )
                        db.execute(
                            "UPDATE pages SET content_hash = ?, audit_skipped = 0 WHERE url = ? AND project_id = ?",
                            (new_hash, url, project_id),
                        )
                        db.commit()
                    finally:
                        db.close()

            except Exception as exc:
                print(f"[AUDIT] FEHLER {url}: {exc}", flush=True)
                return

            state = _project_state.get(slug, {})
            state["pages_audited"] = state.get("pages_audited", 0) + 1
            state["package_pages_audited"] = state.get("package_pages_audited", 0) + 1
            recently = state.get("recently_audited", [])
            if avg_score is not None:
                recently.insert(0, {"url": url, "score": round(avg_score, 1)})
            state["recently_audited"] = recently[:5]
            _project_state[slug] = state
            print(f"[AUDIT_ONE] Fertig: {url} | score={avg_score} | gesamt={state['pages_audited']}", flush=True)

    for pkg_idx in range(resume_from_package, len(packages)):
        package = packages[pkg_idx]
        current_pkg_num = pkg_idx + 1
        pkg_start = pkg_idx * PACKAGE_SIZE + 1
        pkg_end = pkg_idx * PACKAGE_SIZE + len(package)
        n_batches = (len(package) + BATCH_SIZE - 1) // BATCH_SIZE

        print(f"[Paket {current_pkg_num}/{total_packages}] Start – Seiten {pkg_start}–{pkg_end}", flush=True)
        _project_state[slug]["status"] = f"auditing_package_{current_pkg_num}_of_{total_packages}"
        _project_state[slug]["current_package"] = current_pkg_num
        _project_state[slug]["package_pages_total"] = len(package)
        _project_state[slug]["package_pages_audited"] = 0

        # Fortschritt in DB persistieren (für Resume nach Neustart)
        _db_prog = get_db(slug)
        try:
            _db_prog.execute(
                "UPDATE projects SET current_package=?, total_packages=?, audit_status=? WHERE id=?",
                (current_pkg_num, total_packages, f"auditing_package_{current_pkg_num}_of_{total_packages}", project_id),
            )
            _db_prog.commit()
        finally:
            _db_prog.close()

        for i in range(0, len(package), BATCH_SIZE):
            batch = package[i:i + BATCH_SIZE]
            await _wait_for_memory(slug)  # Proaktiv RAM prüfen vor jedem Batch
            await asyncio.gather(*[_audit_one(p["id"], p["url"]) for p in batch], return_exceptions=True)
            gc.collect()  # Spelling/LanguageTool-Objekte sofort freigeben
            await asyncio.sleep(5)  # Pause zwischen Batches
            ram = _get_ram_mb()
            pkg_done = _project_state[slug].get("package_pages_audited", 0)
            ram_str = f"{ram:.0f}MB verfügbar" if ram is not None else "RAM unbekannt"
            print(
                f"[Paket {current_pkg_num}/{total_packages}] Batch {i // BATCH_SIZE + 1}/{n_batches} – "
                f"RAM: {ram_str} – {pkg_done}/{len(package)} Seiten auditiert",
                flush=True,
            )

        print(f"[Paket {current_pkg_num}/{total_packages}] Abgeschlossen – warte auf Speicherfreigabe...", flush=True)

        if pkg_idx < len(packages) - 1:
            _project_state[slug]["status"] = "waiting_memory"
            await _wait_for_memory(slug)
            print(f"[Speicher] Starte Paket {current_pkg_num + 1}/{total_packages}", flush=True)

    # Audit-Status in DB zurücksetzen
    _db_done = get_db(slug)
    try:
        _db_done.execute(
            "UPDATE projects SET current_package=0, total_packages=0, audit_status=NULL WHERE id=?",
            (project_id,),
        )
        _db_done.commit()
    finally:
        _db_done.close()

    _project_state[slug]["status"] = "done"

    # E-Mail-Benachrichtigung: immer senden wenn notification_email gesetzt ist
    db2 = get_db(slug)
    try:
        proj = db2.execute(
            "SELECT name, notification_email, project_token FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if proj and proj["notification_email"]:
            # Nur jeweils das neueste Audit-Ergebnis pro Seite verwenden
            score_rows = db2.execute(
                """SELECT p.url, ar.score
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
            low_score_pages = sorted(
                [{"url": r["url"], "score": round(r["score"], 1)} for r in score_rows if r["score"] is not None],
                key=lambda x: x["score"]
            )[:5]
            # Spelling-Fehler zählen (aus globaler spelling.db)
            spelling_count = 0
            try:
                from backend.database import get_global_db
                page_urls = [r["url"] for r in db2.execute(
                    "SELECT url FROM pages WHERE project_id = ?", (project_id,)
                ).fetchall()]
                if page_urls:
                    g = get_global_db()
                    placeholders = ",".join("?" * len(page_urls))
                    spelling_count = g.execute(
                        f"SELECT COUNT(*) FROM spelling_candidates WHERE url IN ({placeholders}) AND status != 'ignorieren'",
                        page_urls,
                    ).fetchone()[0]
                    g.close()
            except Exception:
                pass
            _send_notification_email(
                to=proj["notification_email"],
                project_name=proj["name"],
                slug=slug,
                page_count=page_count,
                avg_score=avg,
                spelling_count=spelling_count,
                low_score_pages=low_score_pages,
                project_token=proj["project_token"],
            )
    finally:
        db2.close()


async def _audit_safe(project_id: int, language, mode_weights: dict, slug: str, resume_from_package: int = 0) -> None:
    """Wrapper für _audit – fängt alle Ausnahmen (inkl. BaseException) ab und setzt Status 'error'."""
    import traceback
    try:
        await _audit(project_id, language, mode_weights, slug, resume_from_package)
    except BaseException as exc:
        tb = traceback.format_exc()
        print(f"[AUDIT] KRITISCHER FEHLER für {slug}: {exc}\n{tb}", flush=True)
        if slug in _project_state:
            _project_state[slug]["status"] = "error"
            _project_state[slug]["error"] = str(exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/", status_code=201)
async def create_project(body: ProjectCreate):
    slug = _slugify(body.name)

    if os.path.exists(db_path(slug)):
        raise HTTPException(status_code=400, detail=f"Projekt '{slug}' existiert bereits.")

    init_db(slug)
    project_token = _secrets.token_urlsafe(12)
    # Sprache aus URL ableiten (wird beim ersten Crawl durch Inhaltsanalyse überschrieben)
    language = body.language or _detect_language_from_url(body.root_url)
    db = get_db(slug)
    try:
        db.execute(
            "INSERT INTO projects (name, slug, root_url, page_type, language, notification_email, max_pages, project_type, project_token) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (body.name, slug, body.root_url, body.page_type, language, body.notification_email, body.max_pages or 0, body.project_type, project_token),
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


@router.get("/summary")
def get_projects_summary():
    """Leichtgewichtiger Endpoint für die Projektliste – page_count + avg_score per aggregierter Query."""
    from backend.database import list_all_projects_summary
    return list_all_projects_summary()


@router.get("/{slug}/status")
def get_project_status(slug: str):
    """Gibt den aktuellen Crawl-/Audit-Fortschritt zurück (In-Memory + DB-Fallback)."""
    state = _project_state.get(slug)
    if state is not None:
        return state
    # Fallback: Status aus DB ableiten
    try:
        db = get_db(slug)
        try:
            proj = db.execute("SELECT id, last_crawled_at, audit_status, current_package, total_packages FROM projects WHERE slug = ?", (slug,)).fetchone()
            if proj is None:
                raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
            page_count = db.execute(
                "SELECT COUNT(*) FROM pages WHERE project_id = ?", (proj["id"],)
            ).fetchone()[0]
            audit_count = db.execute(
                "SELECT COUNT(DISTINCT ar.page_id) FROM audit_results ar "
                "JOIN pages p ON ar.page_id = p.id WHERE p.project_id = ?",
                (proj["id"],)
            ).fetchone()[0]
            recent_rows = db.execute(
                """SELECT p.url, ar.score FROM audit_results ar
                   JOIN pages p ON ar.page_id = p.id
                   WHERE p.project_id = ?
                   ORDER BY ar.crawled_at DESC LIMIT 5""",
                (proj["id"],),
            ).fetchall()
        finally:
            db.close()
        db_status = proj["audit_status"]
        if db_status and db_status.startswith("auditing_package_"):
            inferred_status = db_status
        elif proj["last_crawled_at"] and audit_count > 0:
            inferred_status = "done"
        else:
            inferred_status = "idle"
        total_pkgs = proj["total_packages"] or 1
        return {
            "status": inferred_status,
            "pages_crawled": page_count,
            "pages_total": page_count,
            "pages_audited": audit_count,
            "current_package": proj["current_package"] or 0,
            "total_packages": total_pkgs,
            "package_pages_total": PACKAGE_SIZE,
            "package_pages_audited": audit_count % PACKAGE_SIZE,
            "recently_audited": [{"url": r["url"], "score": r["score"]} for r in recent_rows],
            "current_url": None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


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
    """Gibt Projektmetadaten + Seitenliste mit Scores zurück – kein results_json."""
    db = get_db(slug)
    try:
        project = db.execute("SELECT * FROM projects WHERE slug = ?", (slug,)).fetchone()
        if project is None:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

        rows = db.execute(
            """
            SELECT p.id   AS page_id,
                   p.url,
                   p.audit_skipped,
                   ar.crawled_at,
                   ar.score
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
                    "page_id": r["page_id"],
                    "url": r["url"],
                    "crawled_at": r["crawled_at"],
                    "score": r["score"],
                    "audit_skipped": r["audit_skipped"],
                    "has_error": r["score"] is None,
                }
                for r in rows
            ],
        }
    finally:
        db.close()


@router.get("/{slug}/page-results")
def get_page_results(slug: str, url: str):
    """Gibt die vollständigen Audit-Ergebnisse für eine einzelne Seite zurück."""
    db = get_db(slug)
    try:
        project = db.execute("SELECT id FROM projects WHERE slug = ?", (slug,)).fetchone()
        if project is None:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
        row = db.execute(
            """
            SELECT ar.results_json
            FROM audit_results ar
            JOIN pages p ON ar.page_id = p.id
            WHERE p.project_id = ? AND p.url = ?
            ORDER BY ar.crawled_at DESC
            LIMIT 1
            """,
            (project["id"], url),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Keine Audit-Ergebnisse für diese Seite")
        return {"results": _unpack_results(row["results_json"])}
    finally:
        db.close()


@router.post("/{slug}/crawl", status_code=202)
async def crawl_project(slug: str):
    db = get_db(slug)
    try:
        row = db.execute("SELECT id, root_url, max_pages FROM projects WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
        project_id, root_url = row["id"], row["root_url"]
        max_pages = row["max_pages"] or None  # 0/NULL → keine Begrenzung
        db.execute(
            "DELETE FROM audit_results WHERE page_id IN (SELECT id FROM pages WHERE project_id = ?)",
            (project_id,),
        )
        db.execute("DELETE FROM pages WHERE project_id = ?", (project_id,))
        db.execute("UPDATE projects SET last_crawled_at = NULL WHERE id = ?", (project_id,))
        db.commit()
    finally:
        db.close()

    _project_state[slug] = {
        "status": "crawling",
        "pages_crawled": 0,
        "pages_total": 0,
        "pages_audited": 0,
        "recently_audited": [],
        "current_url": None,
    }
    asyncio.create_task(_crawl(project_id, root_url, slug, max_pages))
    return {"slug": slug, "crawl_status": "started"}


@router.post("/{slug}/audit", status_code=202)
async def audit_project(slug: str):
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
    asyncio.create_task(_audit_safe(project_id, language, mode_weights, slug))
    return {"slug": slug, "audit_status": "started", "pages": page_count}


@router.patch("/{slug}/email", status_code=200)
def update_email(slug: str, body: EmailUpdate):
    db = get_db(slug)
    try:
        row = db.execute("SELECT id FROM projects WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
        db.execute("UPDATE projects SET notification_email = ? WHERE slug = ?", (body.notification_email, slug))
        db.commit()
    finally:
        db.close()
    return {"slug": slug, "notification_email": body.notification_email}


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

    # Spelling-Kandidaten für alle Seiten dieses Projekts löschen
    try:
        db = get_db(slug)
        try:
            rows = db.execute("SELECT url FROM pages").fetchall()
            page_urls = [r["url"] for r in rows]
        finally:
            db.close()
        if page_urls:
            from backend.database import get_global_db
            gdb = get_global_db()
            try:
                placeholders = ",".join("?" * len(page_urls))
                gdb.execute(
                    f"DELETE FROM spelling_candidates WHERE url IN ({placeholders})",
                    page_urls,
                )
                gdb.commit()
            finally:
                gdb.close()
    except Exception as exc:
        print(f"[DELETE] Fehler beim Bereinigen der Spelling-Kandidaten für {slug}: {exc}", flush=True)

    os.remove(path)


@router.post("/{slug}/token", status_code=201)
def generate_project_token(slug: str):
    token = _secrets.token_urlsafe(12)
    db = get_db(slug)
    try:
        row = db.execute("SELECT id FROM projects WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
        db.execute("UPDATE projects SET project_token = ? WHERE slug = ?", (token, slug))
        db.commit()
    finally:
        db.close()
    return {"token": token}


@router.get("/{slug}/token/verify")
def verify_project_token(slug: str, token: Optional[str] = None):
    db = get_db(slug)
    try:
        row = db.execute("SELECT project_token FROM projects WHERE slug = ?", (slug,)).fetchone()
    finally:
        db.close()
    if row is None:
        return {"valid": False}
    stored = row["project_token"]
    if not stored or token != stored:
        return {"valid": False}
    return {"valid": True}
