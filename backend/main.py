from __future__ import annotations
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sys, os, asyncio
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

    soup = page["soup"]

    # Alle Checks parallel ausführen
    tasks = {
        "meta":           asyncio.to_thread(check_meta, soup, request.url),
        "headings":       asyncio.to_thread(check_headings, soup),
        "broken_links":   check_broken_links(soup, request.url),
        "alt_attributes": asyncio.to_thread(check_alt_attributes, soup, request.url),
        "spelling":       asyncio.to_thread(check_spelling, soup, language=request.language),
        "keywords":       asyncio.to_thread(check_keywords, soup, keywords=request.keywords),
        "url_slug":       asyncio.to_thread(check_url_slug, request.url),
        "mode_analysis":  asyncio.to_thread(check_mode_analysis, soup, request.url, request.mode_weights or {}),
    }

    keys = list(tasks.keys())
    values = await asyncio.gather(*tasks.values(), return_exceptions=True)

    results = {}
    for key, result in zip(keys, values):
        if isinstance(result, Exception):
            results[key] = {
                "score": 0,
                "issues": [{"message": f"Check fehlgeschlagen: {str(result)}"}],
                "warnings": [],
                "passed": [],
            }
        else:
            results[key] = result

    # SEA separat – nur wenn aktiviert
    if request.run_sea:
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
