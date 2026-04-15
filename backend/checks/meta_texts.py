from bs4 import BeautifulSoup
from urllib.parse import urlparse


# Empfohlene Zeichenlängen (Richtlinien für Suchausgaben)
TITLE_MIN = 30
TITLE_MAX = 60
DESCRIPTION_MIN = 70
DESCRIPTION_MAX = 160


def check_meta(soup: BeautifulSoup, url: str) -> dict:
    """
    Prüft alle relevanten Meta-Informationen einer Seite:
    - <title>
    - meta description
    - meta robots
    - canonical
    - og:title / og:description (Open Graph)
    - hreflang
    """
    issues = []
    warnings = []
    passed = []
    data = {}

    # ── TITLE ─────────────────────────────────────────────────────────────
    title_tag = soup.find("title")
    if not title_tag or not title_tag.get_text(strip=True):
        data["title"] = None
        issues.append({
            "code": "TITLE_MISSING",
            "message": "Kein <title>-Tag gefunden.",
            "severity": "critical",
        })
    else:
        title_text = title_tag.get_text(strip=True)
        title_len = len(title_text)
        data["title"] = {"text": title_text, "length": title_len}

        if title_len < TITLE_MIN:
            warnings.append({
                "code": "TITLE_TOO_SHORT",
                "message": f"Title zu kurz ({title_len} Zeichen, Minimum: {TITLE_MIN}).",
                "severity": "warning",
                "value": title_text,
            })
        elif title_len > TITLE_MAX:
            warnings.append({
                "code": "TITLE_TOO_LONG",
                "message": f"Title zu lang ({title_len} Zeichen, Maximum: {TITLE_MAX}). Kann bei Suchresultaten abgeschnitten werden.",
                "severity": "warning",
                "value": title_text,
            })
        else:
            passed.append({"code": "TITLE_OK", "message": f"Title-Länge optimal ({title_len} Zeichen)."})

    # ── META DESCRIPTION ───────────────────────────────────────────────────
    desc_tag = soup.find("meta", attrs={"name": "description"})
    if not desc_tag or not desc_tag.get("content", "").strip():
        data["description"] = None
        issues.append({
            "code": "DESCRIPTION_MISSING",
            "message": "Keine Meta-Description gefunden.",
            "severity": "critical",
        })
    else:
        desc_text = desc_tag["content"].strip()
        desc_len = len(desc_text)
        data["description"] = {"text": desc_text, "length": desc_len}

        if desc_len < DESCRIPTION_MIN:
            warnings.append({
                "code": "DESCRIPTION_TOO_SHORT",
                "message": f"Meta-Description zu kurz ({desc_len} Zeichen, Minimum: {DESCRIPTION_MIN}).",
                "severity": "warning",
                "value": desc_text,
            })
        elif desc_len > DESCRIPTION_MAX:
            warnings.append({
                "code": "DESCRIPTION_TOO_LONG",
                "message": f"Meta-Description zu lang ({desc_len} Zeichen, Maximum: {DESCRIPTION_MAX}). Kann bei Suchresultaten abgeschnitten werden.",
                "severity": "warning",
                "value": desc_text,
            })
        else:
            passed.append({"code": "DESCRIPTION_OK", "message": f"Meta-Description-Länge optimal ({desc_len} Zeichen)."})

    # ── META ROBOTS ────────────────────────────────────────────────────────
    robots_tag = soup.find("meta", attrs={"name": "robots"})
    if robots_tag:
        robots_content = robots_tag.get("content", "").lower()
        data["robots"] = robots_content
        if "noindex" in robots_content:
            issues.append({
                "code": "ROBOTS_NOINDEX",
                "message": f"Seite ist auf noindex gesetzt: '{robots_content}'. Die Seite wird in den Suchresultaten nicht angezeigt.",
                "severity": "critical",
            })
        elif "nofollow" in robots_content:
            warnings.append({
                "code": "ROBOTS_NOFOLLOW",
                "message": f"Seite hat nofollow: '{robots_content}'. Links werden nicht verfolgt.",
                "severity": "warning",
            })
        else:
            passed.append({"code": "ROBOTS_OK", "message": f"Robots-Direktive: {robots_content}"})
    else:
        data["robots"] = None
        passed.append({"code": "ROBOTS_DEFAULT", "message": "Kein robots-Tag → Standard (index, follow)."})

    # ── CANONICAL ──────────────────────────────────────────────────────────
    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    if not canonical_tag:
        data["canonical"] = None
        if "hslu.ch" in url:
            warnings.append({
                "code": "CANONICAL_MISSING",
                "message": "Kein canonical-Tag im HTML gefunden. HSLU-Seiten setzen diesen Tag dynamisch per JavaScript – mit diesem Tool nicht prüfbar.",
                "severity": "info",
            })
        else:
            warnings.append({
                "code": "CANONICAL_MISSING",
                "message": "Kein canonical-Tag gefunden. Empfohlen zur Vermeidung von Duplicate Content.",
                "severity": "warning",
            })
    else:
        canonical_href = canonical_tag.get("href", "")
        data["canonical"] = canonical_href
        parsed_url = urlparse(url)
        parsed_canonical = urlparse(canonical_href)
        if parsed_url.netloc and parsed_canonical.netloc and parsed_url.netloc != parsed_canonical.netloc:
            warnings.append({
                "code": "CANONICAL_EXTERNAL",
                "message": f"Canonical zeigt auf externe Domain: {canonical_href}",
                "severity": "warning",
            })
        else:
            passed.append({"code": "CANONICAL_OK", "message": f"Canonical gesetzt: {canonical_href}"})

    # ── OPEN GRAPH ─────────────────────────────────────────────────────────
    og_title = soup.find("meta", attrs={"property": "og:title"})
    og_desc = soup.find("meta", attrs={"property": "og:description"})
    og_image = soup.find("meta", attrs={"property": "og:image"})

    og_data = {
        "title": og_title["content"].strip() if og_title and og_title.get("content") else None,
        "description": og_desc["content"].strip() if og_desc and og_desc.get("content") else None,
        "image": og_image["content"].strip() if og_image and og_image.get("content") else None,
    }
    data["open_graph"] = og_data

    missing_og = [k for k, v in og_data.items() if not v]
    if missing_og:
        warnings.append({
            "code": "OG_INCOMPLETE",
            "message": f"Open Graph unvollständig. Fehlend: {', '.join(missing_og)}.",
            "severity": "info",
        })
    else:
        passed.append({"code": "OG_OK", "message": "Open Graph vollständig (title, description, image)."})

    # ── HREFLANG ───────────────────────────────────────────────────────────
    hreflang_tags = soup.find_all("link", attrs={"rel": "alternate", "hreflang": True})
    data["hreflang"] = [
        {"lang": tag.get("hreflang"), "href": tag.get("href")}
        for tag in hreflang_tags
    ]

    # ── SCORE ──────────────────────────────────────────────────────────────
    _DEDUCTIONS = {
        "TITLE_MISSING": 20, "DESCRIPTION_MISSING": 20,
        "TITLE_TOO_SHORT": 10, "TITLE_TOO_LONG": 10,
        "DESCRIPTION_TOO_SHORT": 10, "DESCRIPTION_TOO_LONG": 10,
        "CANONICAL_MISSING": 5, "OG_INCOMPLETE": 5,
    }
    score = 100
    for entry in issues + warnings:
        if entry.get("code") == "CANONICAL_MISSING" and entry.get("severity") == "info":
            continue
        score -= _DEDUCTIONS.get(entry.get("code", ""), 0)
    score = max(0, score)

    return {
        "score": score,
        "issues": issues,
        "warnings": warnings,
        "passed": passed,
        "data": data,
    }
