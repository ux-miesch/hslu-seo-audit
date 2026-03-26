from bs4 import BeautifulSoup
from whitelist import HEADING_DUPLICATES_WHITELIST

HEADING_TAGS = ["h1", "h2", "h3"]


def check_headings(soup: BeautifulSoup) -> dict:
    """
    Prüft die Überschriftenstruktur einer Seite:
    - Genau eine H1 vorhanden?
    - H1 nicht leer?
    - Mindestens eine H2 vorhanden? (nur H1 = Fehler)
    - Hierarchie vollständig? (H3 ohne H2 = Fehler, H4 ohne H3 = Fehler)
    - Überschriften nicht zu lang?
    - Duplikate? (Whitelist wird berücksichtigt)

    Nicht mehr geprüft:
    - Reihenfolge der Überschriften im Quellcode
    - H4, H5, H6 (werden komplett ignoriert)
    """
    issues = []
    warnings = []
    passed = []

    headings = []
    for tag in soup.find_all(HEADING_TAGS):
        text = tag.get_text(strip=True)
        level = int(tag.name[1])
        headings.append({"level": level, "text": text, "tag": tag.name})

    data = {"headings": headings, "count": len(headings)}

    if not headings:
        issues.append({
            "code": "NO_HEADINGS",
            "message": "Keine Überschriften gefunden. Mindestens eine H1 und eine H2 sind erforderlich.",
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

    # ── HIERARCHIE-VOLLSTÄNDIGKEIT ─────────────────────────────────────────
    # Prüft ob übergeordnete Ebenen vorhanden sind – unabhängig von Reihenfolge.
    # H3 braucht H2, H4 braucht H3 etc. Nur H1 ohne H2 ist ein Fehler.
    levels_present = {h["level"] for h in headings}

    # H2 zwingend erforderlich
    if 2 not in levels_present:
        issues.append({
            "code": "H2_MISSING",
            "message": "Keine H2-Überschrift gefunden. Eine Seite benötigt mindestens eine H2 zur Strukturierung des Inhalts.",
            "severity": "critical",
        })
    else:
        passed.append({
            "code": "H2_PRESENT",
            "message": f"{len([h for h in headings if h['level'] == 2])} H2-Überschrift(en) gefunden.",
        })

    # H3 nur erlaubt wenn H2 vorhanden
    if 3 in levels_present and 2 not in levels_present:
        issues.append({
            "code": "H3_WITHOUT_H2",
            "message": "H3-Überschriften gefunden, aber keine H2. H3 setzt eine übergeordnete H2 voraus.",
            "severity": "critical",
        })
    elif 3 in levels_present and 2 in levels_present:
        passed.append({
            "code": "H3_OK",
            "message": f"{len([h for h in headings if h['level'] == 3])} H3-Überschrift(en) korrekt unterhalb von H2.",
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

    # ── DUPLIKATE ──────────────────────────────────────────────────────────
    texts = [h["text"].lower().strip() for h in headings if h["text"]]
    duplicates = {
        t for t in texts
        if texts.count(t) > 1 and t not in HEADING_DUPLICATES_WHITELIST
    }
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
