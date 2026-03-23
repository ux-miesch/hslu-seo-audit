from __future__ import annotations
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from crawler import fetch_page
from checks.meta_texts import check_meta
from checks.headings import check_headings

app = FastAPI(title="SEO Audit API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In Produktion einschränken
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuditRequest(BaseModel):
    url: str
    keywords: List[str] = []


class AuditResponse(BaseModel):
    url: str
    status: str
    checks: dict


@app.get("/")
def root():
    return {"message": "SEO Audit API läuft ✓"}


@app.post("/audit", response_model=AuditResponse)
async def run_audit(request: AuditRequest):
    page = await fetch_page(request.url)
    if page is None:
        raise HTTPException(status_code=400, detail=f"URL konnte nicht abgerufen werden: {request.url}")

    results = {}
    results["meta"] = check_meta(page["soup"], request.url)
    results["headings"] = check_headings(page["soup"])

    return AuditResponse(
        url=request.url,
        status="success",
        checks=results,
    )
