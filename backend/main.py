from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(__file__))
from crawler import fetch_page
from backend.routers import projects
from backend.routers import spelling_candidates
from backend.routers import admin
from backend.routers import single_audits
from backend.routers import feedback
from backend.audit_runner import run_checks
from checks.sea import check_sea


async def _resume_interrupted_audits() -> None:
    """Nimmt unterbrochene Audits nach einem Backend-Neustart wieder auf."""
    from backend.database import list_all_projects, get_db
    from backend.routers.projects import _audit, _project_state, _mode_weights_for

    projects = list_all_projects()
    for p in projects:
        audit_status = p.get("audit_status")
        if not audit_status or not audit_status.startswith("auditing_package_"):
            continue
        slug = p["slug"]
        resume_pkg = max(0, (p.get("current_package") or 1) - 1)  # 0-basiert
        print(f"[RESUME] Unterbrochener Audit für {slug} – starte ab Paket {resume_pkg + 1}", flush=True)
        db = get_db(slug)
        try:
            row = db.execute(
                "SELECT id, language, project_type FROM projects WHERE slug = ?", (slug,)
            ).fetchone()
        finally:
            db.close()
        if row:
            mode_weights = _mode_weights_for(row["project_type"] or "website")
            asyncio.create_task(
                _audit(row["id"], row["language"], mode_weights, slug, resume_from_package=resume_pkg)
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.database import migrate_all, init_global_db
    from backend.scheduler import init_scheduler, shutdown_scheduler
    from backend.single_audits import init_single_audits_db, cleanup_expired
    migrate_all()
    init_global_db()
    init_single_audits_db()
    cleanup_expired()
    init_scheduler()
    await _resume_interrupted_audits()
    yield
    shutdown_scheduler()


app = FastAPI(title="SEO Audit API", version="0.2.0", lifespan=lifespan)

app.include_router(projects.router)
app.include_router(spelling_candidates.router)
app.include_router(admin.router)
app.include_router(single_audits.router)
app.include_router(feedback.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuditRequest(BaseModel):
    url: str
    keywords: List[str] = []
    language: Optional[str] = None
    mode_weights: Optional[dict] = {
        "content": 60,
        "conversion": 40,
        "course": 0,
        "event": 0,
    }
    run_sea: bool = False


class AuditResponse(BaseModel):
    url: str
    status: str
    checks: dict


@app.get("/")
def root():
    return {"message": "SEO Audit API läuft ✓", "version": "0.2.0"}


@app.get("/outbound-ip")
async def outbound_ip():
    import httpx
    async with httpx.AsyncClient() as client:
        r = await client.get("https://api.ipify.org?format=json", timeout=10)
        return r.json()


@app.post("/audit", response_model=AuditResponse)
async def run_audit(request: AuditRequest):
    results = await run_checks(
        request.url,
        language=request.language,
        mode_weights=request.mode_weights,
        keywords=request.keywords,
    )
    if results is None:
        raise HTTPException(
            status_code=400,
            detail=f"URL konnte nicht abgerufen werden: {request.url}"
        )

    # SEA separat – nur wenn aktiviert
    if request.run_sea:
        page = await fetch_page(request.url)
        soup = page["soup"] if page else None
        if soup:
            try:
                results["sea"] = await asyncio.to_thread(check_sea, soup, request.url)
            except Exception as e:
                results["sea"] = {
                    "score": 0,
                    "issues": [{"message": f"SEA-Check fehlgeschlagen: {str(e)}"}],
                    "warnings": [],
                    "passed": [],
                }

    return AuditResponse(
        url=request.url,
        status="success",
        checks=results,
    )
