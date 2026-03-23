from bs4 import BeautifulSoup
from typing import Optional


HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]


def check_headings(soup: BeautifulSoup) -> dict:
    """
    Prüft die Überschriftenstruktur einer Seite:
    - Genau eine H1 vorhanden?
    - Hierarchie korrekt (kein Sprung von H1 → H3)?
    - H1 nicht leer?
    - Überschriften nicht zu lang?
    - Duplicate-Überschriften?
    """
    issues = []
    warnings = []
    passed = []

    # Alle Überschriften in Dokumentreihenfolge sammeln
    headings = []
    for tag in soup.find_all(HEADING_TAGS):
        text = tag.get_text(strip=True)
        level = int(tag.name[1])  # "h2" → 2
        headings.append({"level": level, "text": text, "tag": tag.name})

    data = {"headings": headings, "count": len(headings)}

    if not headings:
        issues.append({
            "code": "NO_HEADINGS",
            "message": "Keine Überschriften gefunden. Mindestens eine H1 ist erforderlich.",
            "severity": "critical",
        })
        return _build_result(issues, warnings, passed, data)

    # ── H1 PRÜFUNG ─────────────────────────────────────────────────────────
    h1_list = [h for h in headings if h["level"] == 1]

    if len(h1_list) == 0:
        issues.append({
            "code": "H1_MISSING",
            "message": "Keine H1-Überschrift gefunden. Jede Seite benötigt genau eine H1.",
            "severity": "critical",
        })
    elif len(h1_list) > 1:
        warnings.append({
            "code": "H1_MULTIPLE",
            "message": f"{len(h1_list)} H1-Überschriften gefunden. Nur eine H1 pro Seite empfohlen.",
            "severity": "warning",
            "values": [h["text"] for h in h1_list],
        })
    else:
        h1_text = h1_list[0]["text"]
        if not h1_text:
            issues.append({
                "code": "H1_EMPTY",
                "message": "H1-Überschrift ist leer.",
                "severity": "critical",
            })
        else:
            passed.append({
                "code": "H1_OK",
                "message": f"Genau eine H1 gefunden: \"{h1_text}\"",
            })

    # ── HIERARCHIE PRÜFUNG ─────────────────────────────────────────────────
    hierarchy_errors = []
    prev_level = 0

    for i, heading in enumerate(headings):
        current_level = heading["level"]

        # Erstes Heading sollte H1 sein
        if i == 0 and current_level != 1:
            warnings.append({
                "code": "FIRST_HEADING_NOT_H1",
                "message": f"Erste Überschrift ist kein H1, sondern {heading['tag'].upper()}: \"{heading['text']}\"",
                "severity": "warning",
            })

        # Sprung prüfen (z.B. H1 → H3 überspringt H2)
        if prev_level > 0 and current_level > prev_level + 1:
            hierarchy_errors.append({
                "from": f"h{prev_level}",
                "to": heading["tag"],
                "text": heading["text"],
                "skipped": f"h{prev_level + 1}",
            })

        prev_level = current_level

    if hierarchy_errors:
        for err in hierarchy_errors:
            warnings.append({
                "code": "HEADING_HIERARCHY_SKIP",
                "message": (
                    f"Hierarchiesprung: Nach {err['from'].upper()} folgt {err['to'].upper()} "
                    f"(übersprungen: {err['skipped'].upper()}). Überschrift: \"{err['text']}\""
                ),
                "severity": "warning",
            })
    else:
        passed.append({
            "code": "HEADING_HIERARCHY_OK",
            "message": "Überschriftenhierarchie ist korrekt (keine Sprünge).",
        })

    # ── LEERE ÜBERSCHRIFTEN ────────────────────────────────────────────────
    empty_headings = [h for h in headings if not h["text"]]
    if empty_headings:
        for h in empty_headings:
            issues.append({
                "code": "HEADING_EMPTY",
                "message": f"Leere {h['tag'].upper()}-Überschrift gefunden.",
                "severity": "critical",
            })
    else:
        passed.append({"code": "HEADINGS_NOT_EMPTY", "message": "Keine leeren Überschriften gefunden."})

    # ── ZU LANGE ÜBERSCHRIFTEN ─────────────────────────────────────────────
    MAX_HEADING_LEN = 70
    long_headings = [h for h in headings if len(h["text"]) > MAX_HEADING_LEN]
    if long_headings:
        for h in long_headings:
            warnings.append({
                "code": "HEADING_TOO_LONG",
                "message": f"{h['tag'].upper()} zu lang ({len(h['text'])} Zeichen): \"{h['text'][:60]}...\"",
                "severity": "info",
            })
    else:
        passed.append({"code": "HEADINGS_LENGTH_OK", "message": "Alle Überschriften sind in akzeptabler Länge."})

    # ── DUPLICATE ÜBERSCHRIFTEN ────────────────────────────────────────────
    texts = [h["text"].lower() for h in headings if h["text"]]
    duplicates = {t for t in texts if texts.count(t) > 1}
    if duplicates:
        for dup in duplicates:
            warnings.append({
                "code": "HEADING_DUPLICATE",
                "message": f"Doppelte Überschrift gefunden: \"{dup}\"",
                "severity": "info",
            })
    else:
        passed.append({"code": "HEADINGS_UNIQUE", "message": "Alle Überschriften sind eindeutig."})

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
