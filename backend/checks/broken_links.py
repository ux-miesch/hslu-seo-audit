import asyncio
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from whitelist import LINK_DOMAIN_WHITELIST, URL_PARAM_WHITELIST

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

MAX_CONCURRENT = 10
TIMEOUT = 10
OK_CODES = set(range(200, 400))

# Bot-blocking Status-Codes
BOT_BLOCKED_CODES = {403, 999, 429}

# Domains die Bots absichtlich blockieren – aus whitelist.py + interne Ergänzungen
BOT_BLOCKED_DOMAINS = set(LINK_DOMAIN_WHITELIST) | {
    "twitter.com", "x.com", "academia.edu"
}

# Consent-Indikatoren: URLs oder Texte im Response die auf eine Consent-Wall hindeuten
CONSENT_INDICATORS = [
    "consent", "cookie-wall", "cookiewall", "privacy-gate",
    "gdpr", "age-gate", "agegate", "paywall",
]

SKIP_SCHEMAS = {"mailto:", "tel:", "javascript:", "#"}


def is_bot_blocked(url: str, status_code: int) -> bool:
    if status_code not in BOT_BLOCKED_CODES:
        return False
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    return any(blocked in domain for blocked in BOT_BLOCKED_DOMAINS)


def is_domain_whitelisted(url: str) -> bool:
    """Prüft ob die Domain grundsätzlich übersprungen werden soll."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    return any(d in domain for d in BOT_BLOCKED_DOMAINS)


def has_url_param_whitelisted(url: str) -> bool:
    """Prüft ob die URL einen whitegelisteten Parameter enthält."""
    url_lower = url.lower()
    return any(p.lower() in url_lower for p in URL_PARAM_WHITELIST)


def is_consent_blocked(url: str, response: httpx.Response) -> bool:
    """
    Erkennt ob eine Seite hinter einer Consent-Wall steckt.
    Prüft finale URL und Response-Body auf bekannte Consent-Muster.
    """
    final_url = str(response.url).lower()
    if any(indicator in final_url for indicator in CONSENT_INDICATORS):
        return True
    # Schneller Body-Check (nur erste 2000 Zeichen)
    try:
        body = response.text[:2000].lower()
        consent_hits = sum(1 for ind in CONSENT_INDICATORS if ind in body)
        if consent_hits >= 2:
            return True
    except Exception:
        pass
    return False


async def check_single_url(
    client: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    async with semaphore:
        # Domain-Whitelist: überspringen
        if is_domain_whitelisted(url):
            return {
                "url": url, "status_code": None, "ok": True,
                "bot_blocked": True, "consent_blocked": False,
                "final_url": url, "redirected": False, "error": None,
            }
        # URL-Parameter-Whitelist: überspringen
        if has_url_param_whitelisted(url):
            return {
                "url": url, "status_code": None, "ok": True,
                "bot_blocked": False, "consent_blocked": False,
                "final_url": url, "redirected": False, "error": "param_whitelisted",
            }
        try:
            response = await client.get(url, timeout=TIMEOUT)
            status_code = response.status_code
            ok = status_code in OK_CODES
            blocked = is_bot_blocked(url, status_code)
            consent = is_consent_blocked(url, response) if ok else False

            return {
                "url": url,
                "status_code": status_code,
                "ok": ok,
                "bot_blocked": blocked,
                "consent_blocked": consent,
                "final_url": str(response.url),
                "redirected": str(response.url).rstrip("/") != url.rstrip("/"),
                "error": None,
            }
        except httpx.TimeoutException:
            return {"url": url, "status_code": None, "ok": False, "bot_blocked": False, "consent_blocked": False, "error": "timeout"}
        except httpx.ConnectError:
            return {"url": url, "status_code": None, "ok": False, "bot_blocked": False, "consent_blocked": False, "error": "nicht erreichbar"}
        except Exception as e:
            return {"url": url, "status_code": None, "ok": False, "bot_blocked": False, "consent_blocked": False, "error": str(e)}


def extract_links(soup: BeautifulSoup, base_url: str) -> list:
    links = []
    seen = set()
    parsed_base = urlparse(base_url)

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        anchor_text = tag.get_text(strip=True) or "[kein Text]"
        if not href:
            continue
        if any(href.startswith(schema) for schema in SKIP_SCHEMAS):
            continue
        absolute_url = urljoin(base_url, href)
        if not absolute_url.startswith(("http://", "https://")):
            continue
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        parsed_link = urlparse(absolute_url)
        is_internal = parsed_link.netloc == parsed_base.netloc
        links.append({
            "url": absolute_url,
            "anchor_text": anchor_text[:80],
            "is_internal": is_internal,
        })
    return links


async def check_broken_links(soup: BeautifulSoup, base_url: str) -> dict:
    issues = []
    warnings = []
    passed = []

    links = extract_links(soup, base_url)
    total_links = len(links)

    if total_links == 0:
        warnings.append({"code": "NO_LINKS", "message": "Keine Links auf der Seite gefunden.", "severity": "info"})
        return _build_result(issues, warnings, passed, {"total": 0, "broken": [], "redirected": [], "ok_count": 0})

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=TIMEOUT) as client:
        tasks = [check_single_url(client, link["url"], semaphore) for link in links]
        results = await asyncio.gather(*tasks)

    link_map = {link["url"]: link for link in links}
    broken, bot_blocked, consent_blocked, redirected, ok_links = [], [], [], [], []

    for result in results:
        meta = link_map.get(result["url"], {})
        enriched = {**result, **meta}
        if result.get("bot_blocked"):
            bot_blocked.append(enriched)
        elif result.get("consent_blocked"):
            consent_blocked.append(enriched)
        elif not result["ok"]:
            broken.append(enriched)
        elif result.get("redirected"):
            redirected.append(enriched)
        else:
            ok_links.append(enriched)

    # Issues – defekte Links
    for link in broken:
        status_info = f"Status {link['status_code']}" if link["status_code"] else f"Fehler: {link.get('error', 'unbekannt')}"
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

    # Warnings – Weiterleitungen
    for link in redirected:
        warnings.append({
            "code": "REDIRECT",
            "message": f"Weiterleitung: {link['url']} → {link.get('final_url')}",
            "severity": "info",
            "anchor_text": link.get("anchor_text"),
        })

    # Warnings – Bot-geblockte Links
    if bot_blocked:
        warnings.append({
            "code": "BOT_BLOCKED",
            "message": f"{len(bot_blocked)} Link(s) nicht prüfbar (Plattform blockiert Bots): "
                       + ", ".join(l["url"] for l in bot_blocked[:5]),
            "severity": "info",
        })

    # Warnings – Consent-geblockte Links (eigene Kategorie)
    if consent_blocked:
        warnings.append({
            "code": "CONSENT_BLOCKED",
            "message": f"{len(consent_blocked)} Link(s) hinter einer Consent-Wall – Inhalt nicht prüfbar: "
                       + ", ".join(l["url"] for l in consent_blocked[:5]),
            "severity": "info",
        })

    if not broken:
        passed.append({
            "code": "NO_BROKEN_LINKS",
            "message": f"Alle {len(ok_links)} geprüften Links sind erreichbar.",
        })

    data = {
        "total": total_links,
        "broken_count": len(broken),
        "redirected_count": len(redirected),
        "bot_blocked_count": len(bot_blocked),
        "consent_blocked_count": len(consent_blocked),
        "ok_count": len(ok_links),
        "broken": broken,
        "redirected": redirected,
        "links": results,
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
