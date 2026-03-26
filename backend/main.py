from __future__ import annotations
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from crawler import fetch_page
from checks.meta_texts import check_meta
from checks.headings import check_headings
from checks.broken_links import check_broken_links
from checks.alt_attributes import check_alt_attributes
from checks.spelling import check_spelling
from checks.keywords import check_keywords
from checks.url_slug import check_url_slug

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
    language: Optional[str] = None  # z.B. "de-CH", "fr", "en-US"


class AuditResponse(BaseModel):
    url: str
    status: str
    checks: dict


@app.get("/")
def root():
    return {"message": "SEO Audit API läuft ✓", "version": "0.2.0"}


@app.post("/audit", response_model=AuditResponse)
async def run_audit(request: AuditRequest):
    # Seite abrufen
    page = await fetch_page(request.url)
    if page is None:
        raise HTTPException(
            status_code=400,
            detail=f"URL konnte nicht abgerufen werden: {request.url}"
        )

    results = {}

    # Check 1: Meta-Texte
    results["meta"] = check_meta(page["soup"], request.url)

    # Check 2: Überschriftenstruktur
    results["headings"] = check_headings(page["soup"])

    # Check 3: Defekte Links (async)
    results["broken_links"] = await check_broken_links(page["soup"], request.url)

    # Check 4: Alt-Attribute
    results["alt_attributes"] = check_alt_attributes(page["soup"], request.url)

    # Check 5: Rechtschreibung
    results["spelling"] = check_spelling(page["soup"], language=request.language)

    # Check 6: Keywords & semantische Vielfalt
    results["keywords"] = check_keywords(page["soup"], keywords=request.keywords)

    # Check 7: URL/Slug
    results["url_slug"] = check_url_slug(request.url)

    return AuditResponse(
        url=request.url,
        status="success",
        checks=results,
    )
