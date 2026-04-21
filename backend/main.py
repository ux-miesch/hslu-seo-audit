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
from backend.audit_runner import run_checks
from checks.sea import check_sea


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
    yield
    shutdown_scheduler()


app = FastAPI(title="SEO Audit API", version="0.2.0", lifespan=lifespan)

app.include_router(projects.router)
app.include_router(spelling_candidates.router)
app.include_router(admin.router)
app.include_router(single_audits.router)

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
