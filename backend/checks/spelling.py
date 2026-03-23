from bs4 import BeautifulSoup
import re
from typing import Optional

# language_tool_python ist die beste Option für Deutsch/Französisch
# Installation: pip install language_tool_python
# Beim ersten Start wird das LanguageTool-JAR automatisch heruntergeladen (~200MB)
# Java muss installiert sein: https://www.java.com

try:
    import language_tool_python
    LANGUAGE_TOOL_AVAILABLE = True
except ImportError:
    LANGUAGE_TOOL_AVAILABLE = False


# Elemente die wir beim Text-Extrahieren ignorieren
IGNORE_TAGS = {
    "script", "style", "code", "pre", "noscript",
    "nav", "footer", "header", "meta", "link",
}

# Minimale Textlänge für Rechtschreibprüfung (kurze Snippets ignorieren)
MIN_TEXT_LENGTH = 50

# Maximale Anzahl Fehler die wir zurückgeben (Performance)
MAX_ERRORS = 50


def extract_main_text(soup: BeautifulSoup) -> list[dict]:
    """
    Extrahiert Textblöcke aus dem Hauptinhalt der Seite.
    Ignoriert Navigation, Footer, Scripts etc.
    Gibt Liste von {text, tag, context} zurück.
    """
    blocks = []

    # Hauptinhalt-Bereiche priorisieren
    main_selectors = ["main", "article", "[role='main']", ".content", "#content", ".post-content"]
    main_area = None
    for selector in main_selectors:
        main_area = soup.select_one(selector)
        if main_area:
            break

    # Fallback: ganzes body
    search_area = main_area or soup.find("body") or soup

    for tag in search_area.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th", "blockquote"]):
        # Ignorierte Tags überspringen
        if any(parent.name in IGNORE_TAGS for parent in tag.parents):
            continue

        text = tag.get_text(separator=" ", strip=True)

        # Zu kurze Texte überspringen
        if len(text) < MIN_TEXT_LENGTH:
            continue

        # Nur sichtbarer Text (keine aria-hidden)
        if tag.get("aria-hidden") == "true":
            continue

        blocks.append({
            "text": text,
            "tag": tag.name,
            "preview": text[:80] + "..." if len(text) > 80 else text,
        })

    return blocks


def detect_language(soup: BeautifulSoup) -> str:
    """
    Erkennt die Sprache der Seite anhand des html lang-Attributs.
    Fallback: de-CH
    """
    html_tag = soup.find("html")
    if html_tag:
        lang = html_tag.get("lang", "").lower()
        if lang.startswith("fr"):
            return "fr"
        elif lang.startswith("en"):
            return "en-US"
        elif lang.startswith("it"):
            return "it"
    return "de-CH"  # Standard: Schweizerdeutsch


def check_spelling(soup: BeautifulSoup, language: Optional[str] = None) -> dict:
    """
    Prüft die Rechtschreibung und Grammatik des Seitentexts.
    Verwendet LanguageTool (unterstützt DE, FR, EN, IT).
    """
    issues = []
    warnings = []
    passed = []
    data = {
        "language_detected": None,
        "language_tool_available": LANGUAGE_TOOL_AVAILABLE,
        "errors": [],
        "blocks_checked": 0,
    }

    if not LANGUAGE_TOOL_AVAILABLE:
        warnings.append({
            "code": "SPELLING_UNAVAILABLE",
            "message": (
                "Rechtschreibprüfung nicht verfügbar. "
                "Bitte installieren: pip install language_tool_python. "
                "Hinweis: Erfordert Java (https://www.java.com)."
            ),
            "severity": "info",
        })
        return _build_result(issues, warnings, passed, data)

    # Sprache erkennen
    detected_lang = language or detect_language(soup)
    data["language_detected"] = detected_lang

    # Textblöcke extrahieren
    blocks = extract_main_text(soup)
    data["blocks_checked"] = len(blocks)

    if not blocks:
        warnings.append({
            "code": "SPELLING_NO_TEXT",
            "message": "Kein prüfbarer Text auf der Seite gefunden.",
            "severity": "info",
        })
        return _build_result(issues, warnings, passed, data)

    # LanguageTool initialisieren
    try:
        tool = language_tool_python.LanguageTool(detected_lang)
    except Exception as e:
        warnings.append({
            "code": "SPELLING_TOOL_ERROR",
            "message": f"LanguageTool konnte nicht gestartet werden: {str(e)}",
            "severity": "warning",
        })
        return _build_result(issues, warnings, passed, data)

    all_errors = []
    error_count = 0

    try:
        for block in blocks:
            if error_count >= MAX_ERRORS:
                break

            text = block["text"]

            try:
                matches = tool.check(text)
            except Exception:
                continue

            for match in matches:
                if error_count >= MAX_ERRORS:
                    break

                # Fehlertyp klassifizieren
                rule_id = match.ruleId
                category = match.category

                # Reine Stil-Hinweise überspringen
                if category in ("STYLE", "REDUNDANCY"):
                    continue

                error_text = text[match.offset: match.offset + match.errorLength]
                suggestions = match.replacements[:3]  # Max 3 Vorschläge

                severity = "critical" if category == "TYPOS" else "warning"

                error_entry = {
                    "text": error_text,
                    "message": match.message,
                    "suggestions": suggestions,
                    "rule_id": rule_id,
                    "category": category,
                    "context": block["preview"],
                    "tag": block["tag"],
                    "severity": severity,
                }
                all_errors.append(error_entry)
                error_count += 1

    finally:
        tool.close()

    data["errors"] = all_errors
    data["error_count"] = len(all_errors)

    # Issues & Warnings aus Fehlern generieren
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
    total = len(issues) + len(warnings) + len(passed)
    score = round((len(passed) / total) * 100) if total > 0 else 0
    return {
        "score": score,
        "issues": issues,
        "warnings": warnings,
        "passed": passed,
        "data": data,
    }
