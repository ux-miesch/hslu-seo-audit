from bs4 import BeautifulSoup
import httpx
import unicodedata
from typing import Optional

LANGUAGETOOL_API = "https://api.languagetool.org/v2/check"

IGNORE_TAGS = {
    "script", "style", "code", "pre", "noscript",
    "nav", "footer", "header", "meta", "link",
}

MIN_TEXT_LENGTH = 50
MAX_ERRORS = 50

# Wörter die nicht als Fehler gewertet werden sollen
SPELLING_WHITELIST = {
    # HSLU-spezifische Abkürzungen und Begriffe
    "ekkj", "mas", "cas", "das", "ba", "ifz", "study", "ikm", "ibr",
    "sa", "pibs", "dba", "sas", "mba", "sebwk",
    "hslu", "sdg", "isa", "isa-modul", "isa-modulen",
    "bachelor-studiengang", "bachelor-studiengängen",
    "master-studiengang", "master-studiengängen",
    "hslu-studierende", "minor", "major", "gastdozierende",
    "bsc", "msc", "zum",
    # Englische und gemischte Begriffe
    "know-how", "nonprofit management", "public", "tourism",
    "content management",
    # Allgemeine Begriffe
    "the", "it", "hours", "and", "lowers", "detection",
}


def extract_main_text(soup: BeautifulSoup) -> list[dict]:
    blocks = []
    main_selectors = ["main", "article", "[role='main']", ".content", "#content", ".post-content"]
    main_area = None
    for selector in main_selectors:
        main_area = soup.select_one(selector)
        if main_area:
            break

    search_area = main_area or soup.find("body") or soup

    for tag in search_area.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th", "blockquote"]):
        if any(parent.name in IGNORE_TAGS for parent in tag.parents):
            continue
        text = unicodedata.normalize("NFC", tag.get_text(separator=" ", strip=True))
        if len(text) < MIN_TEXT_LENGTH:
            continue
        if tag.get("aria-hidden") == "true":
            continue
        blocks.append({
            "text": text,
            "tag": tag.name,
            "preview": text[:80] + "..." if len(text) > 80 else text,
        })

    return blocks


def detect_language(soup: BeautifulSoup) -> str:
    html_tag = soup.find("html")
    if html_tag:
        lang = html_tag.get("lang", "").lower()
        if lang.startswith("fr"):
            return "fr"
        elif lang.startswith("en"):
            return "en-US"
        elif lang.startswith("it"):
            return "it"
    return "de-CH"


def check_spelling(soup: BeautifulSoup, language: Optional[str] = None) -> dict:
    issues = []
    warnings = []
    passed = []
    data = {
        "language_detected": None,
        "language_tool_available": True,
        "errors": [],
        "blocks_checked": 0,
    }

    detected_lang = language or detect_language(soup)
    data["language_detected"] = detected_lang

    blocks = extract_main_text(soup)
    data["blocks_checked"] = len(blocks)

    if not blocks:
        warnings.append({
            "code": "SPELLING_NO_TEXT",
            "message": "Kein prüfbarer Text auf der Seite gefunden.",
            "severity": "info",
        })
        return _build_result(issues, warnings, passed, data)

    all_errors = []
    error_count = 0

    with httpx.Client(timeout=30) as client:
        for block in blocks:
            if error_count >= MAX_ERRORS:
                break

            try:
                response = client.post(LANGUAGETOOL_API, data={
                    "text": block["text"],
                    "language": detected_lang,
                })
                response.raise_for_status()
                result = response.json()
            except Exception as e:
                warnings.append({
                    "code": "SPELLING_API_ERROR",
                    "message": f"LanguageTool API nicht erreichbar: {str(e)}",
                    "severity": "warning",
                })
                return _build_result(issues, warnings, passed, data)

            for match in result.get("matches", []):
                if error_count >= MAX_ERRORS:
                    break

                rule = match.get("rule", {})
                category = rule.get("category", {}).get("id", "")

                if category in ("STYLE", "REDUNDANCY"):
                    continue

                offset = match["offset"]
                length = match["length"]
                error_text = block["text"][offset:offset + length]

                # Whitelist prüfen – Gross-/Kleinschreibung ignorieren
                if error_text.lower() in SPELLING_WHITELIST:
                    continue

                suggestions = [r["value"] for r in match.get("replacements", [])[:3]]
                message_lower = match.get("message", "").lower()
                if "möglich" in message_lower or "möglicher" in message_lower:
                    severity = "warning"
                else:
                    severity = "critical" if category == "TYPOS" else "warning"

                all_errors.append({
                    "text": error_text,
                    "message": match.get("message", ""),
                    "suggestions": suggestions,
                    "rule_id": rule.get("id", ""),
                    "category": category,
                    "context": block["preview"],
                    "tag": block["tag"],
                    "severity": severity,
                })
                error_count += 1

    data["errors"] = all_errors
    data["error_count"] = len(all_errors)

    for error in all_errors:
        entry = {
            "code": "SPELLING_ERROR",
            "message": f"\"{error['text']}\" – {error['message']}",
            "severity": error["severity"],
            "suggestions": error["suggestions"],
            "context": error["context"],
            "rule_id": error["rule_id"],
        }
        if error["severity"] == "critical":
            issues.append(entry)
        else:
            warnings.append(entry)

    if not all_errors:
        passed.append({
            "code": "SPELLING_OK",
            "message": f"Keine Rechtschreibfehler in {len(blocks)} geprüften Textblöcken gefunden.",
        })
    elif error_count >= MAX_ERRORS:
        warnings.append({
            "code": "SPELLING_MAX_ERRORS",
            "message": f"Maximale Fehleranzahl ({MAX_ERRORS}) erreicht. Nicht alle Fehler werden angezeigt.",
            "severity": "info",
        })

    return _build_result(issues, warnings, passed, data)


def _build_result(issues, warnings, passed, data) -> dict:
    score = 100
    for entry in issues + warnings:
        if entry.get("code") == "SPELLING_ERROR":
            score -= 10 if entry.get("severity") == "critical" else 5
    score = max(0, score)
    return {
        "score": score,
        "issues": issues,
        "warnings": warnings,
        "passed": passed,
        "data": data,
    }
