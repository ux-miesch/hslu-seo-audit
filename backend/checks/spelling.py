from bs4 import BeautifulSoup
import httpx
import re
import sqlite3
import os
import unicodedata
from datetime import datetime
from typing import Optional
from whitelist import SPELLING_WHITELIST
from langdetect import detect, LangDetectException

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_BASE = os.environ.get("DB_PATH", _BACKEND_DIR)
_GLOBAL_DB = os.path.join(_DB_BASE, "spelling.db")

# Rule-IDs die grundsätzlich nicht gespeichert werden (Leerzeichen-/Whitespace-Regeln)
_SKIP_RULE_KEYWORDS = ("LEERZEICHEN", "WHITESPACE", "REPEAT")
_SKIP_RULE_IDS = {
    "COMMA_PARENTHESIS_WHITESPACE",
    "LEERZEICHEN_NACH_VOR_ANFUEHRUNGSZEICHEN",
    "AUSLASSUNGSPUNKTE_LEERZEICHEN",
    "LEERZEICHEN_VOR_AUSRUFEZEICHEN_ETC",
    "EINHEIT_LEERZEICHEN",
}


def _is_skipped_rule(rule_id: str) -> bool:
    if rule_id in _SKIP_RULE_IDS:
        return True
    return any(kw in rule_id for kw in _SKIP_RULE_KEYWORDS)


def _get_ignored_pairs() -> set:
    """Gibt alle (word, rule_id)-Paare zurück die ignoriert werden sollen."""
    try:
        conn = sqlite3.connect(_GLOBAL_DB, check_same_thread=False)
        rows = conn.execute(
            "SELECT word, rule_id FROM spelling_candidates WHERE status = 'ignorieren'"
        ).fetchall()
        conn.close()
        return {(r[0], r[1]) for r in rows}
    except Exception:
        return set()


def _get_db_whitelist() -> set:
    """Gibt alle Wörter aus der DB-Whitelist zurück (via 'Whitelist anwenden' hinzugefügt)."""
    try:
        conn = sqlite3.connect(_GLOBAL_DB, check_same_thread=False)
        rows = conn.execute("SELECT word FROM spelling_whitelist").fetchall()
        conn.close()
        return {r[0].lower().strip() for r in rows}
    except Exception:
        return set()


def _save_candidates(errors: list, url: str) -> None:
    """Upsert Fehler in spelling_candidates: neu → anlegen, vorhanden → last_seen + url updaten."""
    try:
        conn = sqlite3.connect(_GLOBAL_DB, check_same_thread=False)
        now = datetime.utcnow().isoformat()
        for e in errors:
            word = e["text"].strip()
            rule_id = e.get("rule_id", "")
            if not word or not rule_id:
                continue
            if _is_skipped_rule(rule_id):
                continue
            conn.execute("""
                INSERT INTO spelling_candidates (word, message, rule_id, url, status, first_seen, last_seen)
                VALUES (?, ?, ?, ?, 'neu', ?, ?)
                ON CONFLICT(word, rule_id) DO UPDATE SET
                    last_seen = excluded.last_seen,
                    url       = excluded.url
            """, (word, e.get("message", ""), rule_id, url, now, now))
        conn.commit()
        conn.close()
    except Exception:
        pass  # Nicht kritisch – Spell-Check läuft trotzdem

LANGUAGETOOL_API = "https://api.languagetool.org/v2/check"

IGNORE_TAGS = {
    "script", "style", "code", "pre", "noscript",
    "nav", "footer", "header", "meta", "link",
}

MIN_TEXT_LENGTH = 50
MAX_ERRORS = 50

DEDUPE_BY_RULE_ONLY = {
    "WHITESPACE_BEFORE_PUNCTUATION",
    "COMMA_PARENTHESIS_WHITESPACE",
    "PUNCTUATION_PARAGRAPH_END",
    "DE_SENTENCE_WHITESPACE",
    "WHITESPACE_BEFORE_CLOSING_BRACKET",
}

DEDUPE_BY_MESSAGE_PREFIX = [
    "Vor Satzzeichen",
    "Nur hinter einem Komma",
    "Vor dem Punkt",
    "Vor einer schliessenden",
]


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


def detect_language(soup: BeautifulSoup, text: str = "") -> str:
    # Schritt 1: HTML lang-Tag prüfen
    html_tag = soup.find("html")
    if html_tag:
        lang = html_tag.get("lang", "").lower()
        if lang.startswith("de"):
            return "de-CH"
        elif lang.startswith("en"):
            return "en-US"
        elif lang.startswith("fr"):
            return "fr"
        elif lang.startswith("it"):
            return "it"

    # Schritt 2: Falls kein lang-Tag oder unklar → Text analysieren
    if text and len(text) >= 50:
        try:
            detected = detect(text)
            mapping = {
                "de": "de-CH",
                "en": "en-US",
                "fr": "fr",
                "it": "it",
            }
            return mapping.get(detected, "de-CH")
        except LangDetectException:
            pass

    # Fallback
    return "de-CH"


def check_spelling(soup: BeautifulSoup, url: str = "", language: Optional[str] = None) -> dict:
    issues = []
    warnings = []
    infos = []
    passed = []
    data = {
        "language_detected": None,
        "language_tool_available": True,
        "errors": [],
        "blocks_checked": 0,
    }

    blocks = extract_main_text(soup)
    data["blocks_checked"] = len(blocks)

    if not blocks:
        warnings.append({
            "code": "SPELLING_NO_TEXT",
            "message": "Kein prüfbarer Text auf der Seite gefunden.",
            "severity": "info",
        })
        return _build_result(issues, warnings, passed, data)

    # Alle Blöcke zu einem Text zusammenfassen
    full_text = "\n\n".join(block["text"] for block in blocks)

    detected_lang = language or detect_language(soup, full_text)
    data["language_detected"] = detected_lang

    ignored_pairs  = _get_ignored_pairs()
    db_whitelist   = _get_db_whitelist()
    combined_whitelist = SPELLING_WHITELIST | db_whitelist
    all_errors = []
    error_count = 0

    # Einen einzigen API-Call
    with httpx.Client(timeout=15) as client:
        try:
            response = client.post(LANGUAGETOOL_API, data={
                "text": full_text,
                "language": detected_lang,
            })
            if response.status_code >= 500:
                warnings.append({
                    "code": "SPELLING_API_ERROR",
                    "message": "Rechtschreibprüfung temporär nicht verfügbar.",
                    "severity": "warning",
                })
                return _build_result(issues, warnings, passed, data)
            response.raise_for_status()
            result = response.json()
        except httpx.TimeoutException:
            warnings.append({
                "code": "SPELLING_API_ERROR",
                "message": "Rechtschreibprüfung nicht erreichbar (Timeout).",
                "severity": "warning",
            })
            return _build_result(issues, warnings, passed, data)
        except Exception as e:
            warnings.append({
                "code": "SPELLING_API_ERROR",
                "message": f"Rechtschreibprüfung nicht erreichbar: {str(e)}",
                "severity": "warning",
            })
            return _build_result(issues, warnings, passed, data)

    # Duplikate entfernen
    seen = set()
    unique_matches = []
    for match in result.get("matches", []):
        rid = match.get("rule", {}).get("id", "")
        msg = match.get("message", "").replace("ß", "ss")
        o = match.get("offset", 0)
        l = match.get("length", 0)
        if rid in DEDUPE_BY_RULE_ONLY:
            key = rid
        elif any(msg.startswith(prefix) for prefix in DEDUPE_BY_MESSAGE_PREFIX):
            key = msg
        else:
            key = (full_text[o:o + l].lower(), msg)
        if key not in seen:
            seen.add(key)
            unique_matches.append(match)

    for match in unique_matches:
        if error_count >= MAX_ERRORS:
            break

        rule = match.get("rule", {})
        category = rule.get("category", {}).get("id", "")
        rule_id = rule.get("id", "")

        if category in ("STYLE", "REDUNDANCY"):
            continue

        msg = match.get("message", "").replace("ß", "ss")
        o = max(0, match.get("offset", 0))
        l = match.get("length", 0)
        is_whitespace_err = rule_id in DEDUPE_BY_RULE_ONLY or any(msg.startswith(p) for p in DEDUPE_BY_MESSAGE_PREFIX)
        if is_whitespace_err:
            error_text = "Leerzeichen vor Satzzeichen"
        else:
            error_text = full_text[o:min(o + l, len(full_text))]

        # Zu kurze oder satzzeichenbehaftete Treffer filtern
        if len(error_text.strip()) < 2:
            continue
        if re.match(r'^[^a-zA-ZäöüÄÖÜ]', error_text) or re.search(r'[^\w]$', error_text):
            continue

        # Whitelist prüfen – Gross-/Kleinschreibung ignorieren (hardcodiert + DB)
        if error_text.lower() in combined_whitelist:
            continue

        # Ignorieren-Kandidaten überspringen
        if (error_text.lower(), rule_id) in ignored_pairs:
            continue

        context_start = max(0, o - 40)
        context_end = min(len(full_text), o + l + 40)
        context = full_text[context_start:context_end]

        suggestions = [r["value"] for r in match.get("replacements", [])[:3]]
        message_lower = match.get("message", "").lower()
        if category == "COMPOUNDING" or rule_id == "WHITESPACE_BEFORE_PUNCTUATION":
            severity = "info"
        elif "möglich" in message_lower:
            severity = "warning"
        else:
            severity = "critical" if category == "TYPOS" else "warning"

        display_message = "Schreibweise prüfen: Bindestrich oder Zusammenschreibung." if category == "COMPOUNDING" else match.get("message", "")

        all_errors.append({
            "text": error_text,
            "message": display_message,
            "suggestions": suggestions,
            "rule_id": rule_id,
            "category": category,
            "context": context,
            "severity": severity,
        })
        error_count += 1

    data["errors"] = all_errors
    data["error_count"] = len(all_errors)

    # Fehler in spelling_candidates persistieren (nur wenn URL bekannt)
    if url and all_errors:
        _save_candidates(all_errors, url)

    for error in all_errors:
        entry = {
            "code": "SPELLING_ERROR",
            "message": f"\"{error['text']}\" – {error['message']}",
            "severity": error["severity"],
            "suggestions": error["suggestions"],
            "context": error["context"],
            "rule_id": error["rule_id"],
            "text": error["text"],
        }
        if error["severity"] == "critical":
            issues.append(entry)
        elif error["severity"] == "info":
            infos.append(entry)
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

    return _build_result(issues, warnings, passed, data, infos)


def _build_result(issues, warnings, passed, data, infos=None) -> dict:
    score = 100
    for entry in issues + warnings:
        if entry.get("code") == "SPELLING_ERROR":
            score -= 10 if entry.get("severity") == "critical" else 5
    score = max(0, score)
    return {
        "score": score,
        "issues": issues,
        "warnings": warnings,
        "infos": infos or [],
        "passed": passed,
        "data": data,
    }
