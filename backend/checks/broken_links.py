import asyncio
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from whitelist import LINK_DOMAIN_WHITELIST, URL_PARAM_WHITELIST, URL_PATH_WHITELIST

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
    # Neu: Chrome-Client-Hints – reduziert Bot-Erkennung
    "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}

MAX_CONCURRENT = 10
TIMEOUT = 20
OK_CODES = set(range(200, 400))

BOT_BLOCKED_CODES = {403, 999, 429}

BOT_BLOCKED_DOMAINS = set(LINK_DOMAIN_WHITELIST) | {
    "twitter.com", "x.com", "academia.edu", "youtube.com", "youtu.be"
}

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
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    return any(d in domain for d in BOT_BLOCKED_DOMAINS)


def has_url_param_whitelisted(url: str) -> bool:
    url_lower = url.lower()
    return any(p.lower() in url_lower for p in URL_PARAM_WHITELIST)


def has_url_path_whitelisted(url: str) -> bool:
    """Prüft ob die URL einen whitegelisteten Pfad enthält."""
    return any(p in url for p in URL_PATH_WHITELIST)


def is_consent_blocked(url: str, response: httpx.Response) -> bool:
    final_url = str(response.url).lower()
    if any(indicator in final_url for indicator in CONSENT_INDICATORS):
        return True
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
        if is_domain_whitelisted(url):
            return {
                "url": url, "status_code": None, "ok": True,
                "bot_blocked": True, "consent_blocked": False,
                "final_url": url, "redirected": False, "error": None,
            }
        if has_url_param_whitelisted(url):
            return {
                "url": url, "status_code": None, "ok": True,
                "bot_blocked": False, "consent_blocked": False,
                "final_url": url, "redirected": False, "error": "param_whitelisted",
            }
        if has_url_path_whitelisted(url):
            return {
                "url": url, "status_code": None, "ok": True,
                "bot_blocked": False, "consent_blocked": False,
                "final_url": url, "redirected": False, "error": "path_whitelisted",
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
            return {"url": url, "status_code": None, "ok": True, "bot_blocked": True, "consent_blocked": False, "final_url": url, "redirected": False, "error": "timeout"}
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
    infos = []
    passed = []

    links = extract_links(soup, base_url)
    total_links = len(links)

    if total_links == 0:
        warnings.append({"code": "NO_LINKS", "message": "Keine Links auf der Seite gefunden.", "severity": "info"})
        return _build_result(issues, warnings, passed, {"total": 0, "broken": [], "redirected": [], "ok_count": 0}, infos)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=TIMEOUT) as client:
        tasks = [check_single_url(client, link["url"], semaphore) for link in links]
        results = await asyncio.gather(*tasks)

    link_map = {link["url"]: link for link in links}
    broken, timeouts, bot_blocked, consent_blocked, redirected, ok_links = [], [], [], [], [], []

    for result in results:
        meta = link_map.get(result["url"], {})
        enriched = {**result, **meta}
        if result.get("error") == "timeout":
            timeouts.append(enriched)
        elif result.get("bot_blocked"):
            bot_blocked.append(enriched)
        elif result.get("consent_blocked"):
            consent_blocked.append(enriched)
        elif not result["ok"]:
            broken.append(enriched)
        elif result.get("redirected"):
            redirected.append(enriched)
        else:
            ok_links.append(enriched)

    for link in broken:
        status = link.get("status_code")
        is_internal = link.get("is_internal", False)
        url = link["url"]

        if status == 404:
            if is_internal:
                severity = "critical"
                message = f"Interne Seite nicht gefunden (404): {url}"
            else:
                severity = "warning"
                message = f"Externe Seite nicht mehr erreichbar (404): {url}"
        elif status == 403:
            severity = "info"
            message = f"Zugriff verweigert – manuell im Browser prüfen (403): {url}"
        elif status == 500:
            severity = "warning"
            message = f"Server-Fehler auf Zielseite – später nochmals prüfen (500): {url}"
        else:
            link_type = "intern" if is_internal else "extern"
            status_info = f"Status {status}" if status else f"Fehler: {link.get('error', 'unbekannt')}"
            severity = "critical" if is_internal else "warning"
            message = f"Defekter {link_type} Link ({status_info}): {url}"

        entry = {
            "code": "BROKEN_LINK",
            "message": message,
            "severity": severity,
            "anchor_text": link.get("anchor_text"),
            "url": url,
            "status_code": status,
            "error": link.get("error"),
        }
        if severity == "critical":
            issues.append(entry)
        elif severity == "info":
            infos.append(entry)
        else:
            warnings.append(entry)

    for link in redirected:
        is_internal = link.get("is_internal", False)
        url = link["url"]
        if is_internal:
            message = f"Interne Weiterleitung – Link direkt auf Ziel-URL aktualisieren: {url}"
        else:
            message = f"Externe Weiterleitung – kein dringender Handlungsbedarf: {url}"
        infos.append({
            "code": "REDIRECT",
            "message": message,
            "severity": "info",
            "anchor_text": link.get("anchor_text"),
        })

    for link in timeouts:
        infos.append({
            "code": "TIMEOUT",
            "message": f"Seite antwortet zu langsam – manuell im Browser prüfen: {link['url']}",
            "severity": "info",
            "anchor_text": link.get("anchor_text"),
        })

    for link in bot_blocked:
        infos.append({
            "code": "BOT_BLOCKED",
            "message": f"Plattform blockiert automatische Prüfung – kein Handlungsbedarf: {link['url']}",
            "severity": "info",
            "anchor_text": link.get("anchor_text"),
        })

    if consent_blocked:
        infos.append({
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
        "timeout_count": len(timeouts),
        "consent_blocked_count": len(consent_blocked),
        "ok_count": len(ok_links),
        "broken": broken,
        "redirected": redirected,
        "links": results,
    }

    return _build_result(issues, warnings, passed, data, infos)


def _build_result(issues, warnings, passed, data, infos=None) -> dict:
    score = 100
    for entry in issues:
        if entry.get("code") == "BROKEN_LINK":
            score -= 20 if entry.get("severity") == "critical" else 10
    for entry in warnings:
        if entry.get("code") == "BROKEN_LINK":
            score -= 10
    score = max(0, score)
    return {
        "score": score,
        "issues": issues,
        "warnings": warnings,
        "infos": infos or [],
        "passed": passed,
        "data": data,
    }
