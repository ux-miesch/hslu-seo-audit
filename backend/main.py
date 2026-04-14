from __future__ import annotations
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(__file__))
from crawler import fetch_page
from backend.routers import projects
from backend.database import init_db
from backend.audit_runner import run_checks
from checks.sea import check_sea

app = FastAPI(title="SEO Audit API", version="0.2.0")

init_db()
app.include_router(projects.router)

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
