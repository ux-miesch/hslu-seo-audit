import asyncio
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Optional

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SEOAuditBot/1.0; "
        "+https://github.com/ux-miesch/hslu-seo-audit)"
    )
}

# Maximale gleichzeitige Requests
MAX_CONCURRENT = 10
TIMEOUT = 10

# Status-Codes die als "OK" gelten
OK_CODES = set(range(200, 400))

# Links mit diesen Schemas überspringen
SKIP_SCHEMAS = {"mailto:", "tel:", "javascript:", "#"}


async def check_single_url(
    client: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Prüft eine einzelne URL auf Erreichbarkeit."""
    async with semaphore:
        try:
            # HEAD zuerst (schneller), Fallback auf GET
            try:
                response = await client.head(url, timeout=TIMEOUT)
                if response.status_code in (405, 501):
                    response = await client.get(url, timeout=TIMEOUT)
            except Exception:
                response = await client.get(url, timeout=TIMEOUT)

            ok = response.status_code in OK_CODES
            return {
                "url": url,
                "status_code": response.status_code,
                "ok": ok,
                "final_url": str(response.url),
                "redirected": str(response.url).rstrip("/") != url.rstrip("/"),
                "error": None,
            }

        except httpx.TimeoutException:
            return {"url": url, "status_code": None, "ok": False, "error": "timeout"}
        except httpx.ConnectError:
            return {"url": url, "status_code": None, "ok": False, "error": "nicht erreichbar"}
        except Exception as e:
            return {"url": url, "status_code": None, "ok": False, "error": str(e)}


def extract_links(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Extrahiert alle Links aus der Seite und klassifiziert sie."""
    links = []
    seen = set()

    parsed_base = urlparse(base_url)

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        anchor_text = tag.get_text(strip=True) or "[kein Text]"

        # Leere Links überspringen
        if not href:
            continue

        # Sonder-Schemas überspringen
        if any(href.startswith(schema) for schema in SKIP_SCHEMAS):
            continue

        # Relative URLs zu absoluten machen
        absolute_url = urljoin(base_url, href)

        # Nur HTTP/HTTPS
        if not absolute_url.startswith(("http://", "https://")):
            continue

        # Duplikate überspringen
        if absolute_url in seen:
            continue
        seen.add(absolute_url)

        # Intern oder extern?
        parsed_link = urlparse(absolute_url)
        is_internal = parsed_link.netloc == parsed_base.netloc

        links.append({
            "url": absolute_url,
            "anchor_text": anchor_text[:80],  # kürzen
            "is_internal": is_internal,
        })

    return links


async def check_broken_links(soup: BeautifulSoup, base_url: str) -> dict:
    """
    Prüft alle Links auf der Seite parallel auf Erreichbarkeit.
    """
    issues = []
    warnings = []
    passed = []

    # Links extrahieren
    links = extract_links(soup, base_url)
    total_links = len(links)

    if total_links == 0:
        warnings.append({
            "code": "NO_LINKS",
            "message": "Keine Links auf der Seite gefunden.",
            "severity": "info",
        })
        return _build_result(issues, warnings, passed, {
            "total": 0, "broken": [], "redirected": [], "ok": []
        })

    # Alle Links parallel prüfen
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    async with httpx.AsyncClient(
        headers=HEADERS,
        follow_redirects=True,
        timeout=TIMEOUT,
    ) as client:
        tasks = [
            check_single_url(client, link["url"], semaphore)
            for link in links
        ]
        results = await asyncio.gather(*tasks)

    # Ergebnisse mit Metadaten verknüpfen
    link_map = {link["url"]: link for link in links}
    broken = []
    redirected = []
    ok_links = []

    for result in results:
        meta = link_map.get(result["url"], {})
        enriched = {**result, **meta}

        if not result["ok"]:
            broken.append(enriched)
        elif result.get("redirected"):
            redirected.append(enriched)
        else:
            ok_links.append(enriched)

    # Issues & Warnings generieren
    for link in broken:
        status_info = (
            f"Status {link['status_code']}"
            if link["status_code"]
            else f"Fehler: {link.get('error', 'unbekannt')}"
        )
        link_type = "intern" if link.get("is_internal") else "extern"
        issues.append({
            "code": "BROKEN_LINK",
            "message": f"Defekter {link_type} Link ({status_info}): {link['url']}",
            "severity": "critical" if link.get("is_internal") else "warning",
            "anchor_text": link.get("anchor_text"),
            "url": link["url"],
            "status_code": link.get("status_code"),
            "error": link.get("error"),
        })

    for link in redirected:
        warnings.append({
            "code": "REDIRECT",
            "message": f"Weiterleitung: {link['url']} → {link.get('final_url')}",
            "severity": "info",
            "anchor_text": link.get("anchor_text"),
        })

    if not broken:
        passed.append({
            "code": "NO_BROKEN_LINKS",
            "message": f"Alle {len(ok_links)} geprüften Links sind erreichbar.",
        })

    # Zusammenfassung
    data = {
        "total": total_links,
        "broken_count": len(broken),
        "redirected_count": len(redirected),
        "ok_count": len(ok_links),
        "broken": broken,
        "redirected": redirected,
    }

    return _build_result(issues, warnings, passed, data)


def _build_result(issues, warnings, passed, data) -> dict:
    total = len(issues) + len(warnings) + len(passed)
    score = round((len(passed) / total) * 100) if total > 0 else 0
    return {
        "score": score,
        "issues": issues,
        "warnings": warnings,
        "passed": passed,
        "data": data,
    }
