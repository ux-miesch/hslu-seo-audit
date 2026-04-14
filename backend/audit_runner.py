from __future__ import annotations
import asyncio
import sys
import os
from typing import Optional

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


async def run_checks(
    url: str,
    language: Optional[str] = None,
    mode_weights: Optional[dict] = None,
    keywords: list = [],
) -> Optional[dict]:
    if mode_weights is None:
        mode_weights = {"content": 60, "conversion": 40, "course": 0, "event": 0}

    page = await fetch_page(url)
    if page is None:
        return None

    soup = page["soup"]

    tasks = {
        "meta":           asyncio.to_thread(check_meta, soup, url),
        "headings":       asyncio.to_thread(check_headings, soup),
        "broken_links":   check_broken_links(soup, url),
        "alt_attributes": asyncio.to_thread(check_alt_attributes, soup, url),
        "spelling":       asyncio.to_thread(check_spelling, soup, language=language),
        "keywords":       asyncio.to_thread(check_keywords, soup, keywords=keywords),
        "url_slug":       asyncio.to_thread(check_url_slug, url),
        "mode_analysis":  asyncio.to_thread(check_mode_analysis, soup, url, mode_weights),
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

    return results
