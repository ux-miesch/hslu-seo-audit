import asyncio
import hashlib
import httpx
from bs4 import BeautifulSoup
from typing import Optional


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SEOAuditBot/1.0; "
        "+https://github.com/your-repo/seo-audit)"
    )
}

TIMEOUT = 15  # Sekunden


async def fetch_page(url: str) -> Optional[dict]:
    """
    Ruft eine URL ab und gibt geparsten Inhalt zurück.
    Gibt None zurück wenn die Seite nicht erreichbar ist.
    """
    # URL normalisieren
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        async with httpx.AsyncClient(
            headers=HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
            verify=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                return None

            html = response.text
            soup = await asyncio.to_thread(BeautifulSoup, html, "html.parser")

            return {
                "url": str(response.url),          # finale URL nach Redirects
                "status_code": response.status_code,
                "html": html,
                "soup": soup,
                "content_type": content_type,
            }

    except httpx.TimeoutException:
        return None
    except httpx.HTTPStatusError:
        return None
    except Exception:
        return None


async def check_url_status(url: str) -> dict:
    """
    Prüft nur den HTTP-Status einer URL (für Link-Checks).
    Gibt Status-Code und Fehlertyp zurück.
    """
    if not url.startswith(("http://", "https://")):
        return {"url": url, "status": "skipped", "reason": "kein HTTP-Link"}

    try:
        async with httpx.AsyncClient(
            headers=HEADERS,
            timeout=10,
            follow_redirects=True,
        ) as client:
            # HEAD zuerst (schneller), Fallback auf GET
            try:
                response = await client.head(url)
                # Manche Server blocken HEAD → GET als Fallback
                if response.status_code in (405, 501):
                    response = await client.get(url)
            except Exception:
                response = await client.get(url)

            return {
                "url": url,
                "status_code": response.status_code,
                "ok": response.status_code < 400,
                "final_url": str(response.url),
                "redirected": str(response.url) != url,
            }

    except httpx.TimeoutException:
        return {"url": url, "status": "error", "reason": "timeout"}
    except httpx.ConnectError:
        return {"url": url, "status": "error", "reason": "nicht erreichbar"}
    except Exception as e:
        return {"url": url, "status": "error", "reason": str(e)}


def content_hash(soup, url: str) -> str:
    """Berechnet einen Hash des relevanten Seiteninhalts für inkrementelles Auditing."""
    parts = [url]
    for tag in soup.find_all("meta"):
        parts.append(tag.get("name", "") + tag.get("property", "") + tag.get("content", ""))
    title = soup.find("title")
    if title:
        parts.append(title.get_text(strip=True))
    canonical = soup.find("link", rel="canonical")
    if canonical:
        parts.append(canonical.get("href", ""))
    for h in soup.find_all(["h1", "h2", "h3"]):
        parts.append(h.get_text(strip=True))
    for a in soup.find_all("a", href=True):
        parts.append(a["href"])
    for img in soup.find_all("img"):
        parts.append(img.get("src", "") + "|" + (img.get("alt") or ""))
    for tag in soup.find_all(["p", "li", "td", "th", "blockquote"]):
        parts.append(tag.get_text(strip=True))
    for script in soup.find_all("script", type="application/ld+json"):
        parts.append(script.string or "")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()
