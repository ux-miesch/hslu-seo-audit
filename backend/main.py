from __future__ import annotations
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from crawler import fetch_page
from checks.meta_texts import check_meta
from checks.headings import check_headings
from checks.broken_links import check_broken_links
from checks.alt_attributes import check_alt_attributes
from checks.spelling import check_spelling
from checks.keywords import check_keywords
from checks.url_slug import check_url_slug
from checks.mode_analysis import check_mode_analysis
from checks.sea import check_sea

app = FastAPI(title="SEO Audit API", version="0.2.0")

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
    page = await fetch_page(request.url)
    if page is None:
        raise HTTPException(
            status_code=400,
            detail=f"URL konnte nicht abgerufen werden: {request.url}"
        )

    results = {}

    results["meta"] = check_meta(page["soup"], request.url)
    results["headings"] = check_headings(page["soup"])
    results["broken_links"] = await check_broken_links(page["soup"], request.url)
    results["alt_attributes"] = check_alt_attributes(page["soup"], request.url)
    results["spelling"] = check_spelling(page["soup"], language=request.language)
    results["keywords"] = check_keywords(page["soup"], keywords=request.keywords)
    results["url_slug"] = check_url_slug(request.url)
    results["mode_analysis"] = check_mode_analysis(
        page["soup"],
        request.url,
        request.mode_weights or {},
    )
    if request.run_sea:
        results["sea"] = check_sea(page["soup"], request.url)

    return AuditResponse(
        url=request.url,
        status="success",
        checks=results,
    )
