"""
mode_analysis.py
Führt die Soft-Faktor-Checks pro aktivem Modus aus.
Welche Checks pro Modus gelten, ist in mode_checks.py definiert.
"""

import re
import json
from bs4 import BeautifulSoup, NavigableString, Tag
from urllib.parse import urlparse, urljoin
from mode_checks import MODE_CHECKS

# ── Keyword-Listen ────────────────────────────────────────────────────────

CTA_KEYWORDS = [
    "anmelden", "jetzt anmelden", "registrieren", "jetzt registrieren",
    "kontaktieren", "kontakt aufnehmen", "anfragen", "jetzt buchen",
    "buchen", "kaufen", "bestellen", "mehr erfahren", "teilnehmen",
    "bewerben", "jetzt bewerben", "abonnieren", "newsletter",
    "termin vereinbaren", "beratung", "kostenloses gespräch",
    "sign up", "register", "contact us", "get in touch", "book now",
    "buy now", "order now", "apply now", "learn more", "subscribe",
    "get started", "request", "schedule",
]

TRANSACTIONAL_KEYWORDS = [
    "anmelden", "registrieren", "buchen", "kaufen", "bestellen",
    "bewerben", "teilnehmen", "anfragen", "kontaktieren", "abonnieren",
    "herunterladen", "download", "kostenlos", "gratis", "preis",
    "kosten", "rabatt", "angebot", "jetzt",
    "buy", "order", "sign up", "book", "apply", "subscribe",
    "free", "price", "cost", "discount", "offer",
]

AUTHOR_PATTERNS = [
    r"\bvon\s+[A-ZÄÖÜ][a-zäöü]+\s+[A-ZÄÖÜ][a-zäöü]+",
    r"\bAutor(?:in)?[:\s]+[A-ZÄÖÜ]",
    r"\bby\s+[A-Z][a-z]+\s+[A-Z][a-z]+",
]

DATE_PATTERNS = [
    r"\b\d{1,2}\.\s*(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+\d{4}\b",
    r"\b\d{1,2}\.\d{1,2}\.\d{4}\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
]

PRICE_PATTERNS = [
    r"CHF\s*[\d'.,]+", r"Fr\.\s*[\d'.,]+",
    r"€\s*[\d'.,]+", r"EUR\s*[\d'.,]+",
    r"[\d'.,]+\s*CHF", r"[\d'.,]+\s*€",
    r"\bkostenlos\b", r"\bgratis\b", r"\bfree\b",
]

DURATION_PATTERNS = [
    r"\d+\s*(?:Stunden?|Tage?|Wochen?|Monate?|Jahre?|Semester)",
    r"\d+\s*(?:hours?|days?|weeks?|months?|years?)",
    r"\d+\s*ECTS", r"\d+\s*Lektionen?",
    r"(?:Teilzeit|Vollzeit|berufsbegleitend|part-time|full-time)",
]

CERTIFICATE_KEYWORDS = [
    "zertifikat", "diplom", "cas", "das", "mas", "mba", "bachelor",
    "master", "abschluss", "certificate", "diploma", "degree",
]

AUDIENCE_PATTERNS = [
    r"richtet sich an", r"für\s+(?:alle|erfahrene|angehende|Menschen|Fachleute)",
    r"voraussetzungen?", r"zielgruppe", r"target audience",
    r"für wen", r"who should attend",
]

LOCATION_KEYWORDS = [
    "online", "hybrid", "vor ort", "präsenz", "virtuell", "remote",
    "zürich", "bern", "luzern", "basel", "genf", "zug",
    "in-person", "on-site", "livestream",
]

AGENDA_KEYWORDS = [
    "programm", "agenda", "ablauf", "tagesordnung",
    "program", "schedule", "timetable",
]

DEADLINE_PATTERNS = [
    r"anmeldeschluss", r"anmeldefrist", r"bis\s+\d{1,2}\.",
    r"deadline", r"last\s+date", r"registration\s+closes",
]


# ── Hilfsfunktionen ───────────────────────────────────────────────────────

def get_text(soup: BeautifulSoup) -> str:
    """Extrahiert sichtbaren Text ohne Nav/Footer/Scripts."""
    soup_copy = BeautifulSoup(str(soup), "html.parser")
    for tag in soup_copy(["nav", "footer", "script", "style", "header"]):
        if isinstance(tag, Tag):
            tag.decompose()
    return soup_copy.get_text(" ", strip=True).lower()


def get_links(soup: BeautifulSoup, base_url: str) -> list:
    base_domain = urlparse(base_url).netloc
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        links.append({
            "url": absolute,
            "text": a.get_text(strip=True).lower(),
            "is_internal": parsed.netloc == base_domain,
        })
    return links


def get_schema(soup: BeautifulSoup) -> list:
    schemas = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                schemas.extend(data)
            else:
                schemas.append(data)
        except Exception:
            pass
    return schemas


# ── Prüffunktionen ────────────────────────────────────────────────────────

def check_cta(soup, base_url, text):
    links = get_links(soup, base_url)
    found = any(kw in lnk["text"] for lnk in links for kw in CTA_KEYWORDS)
    if not found:
        buttons = soup.find_all(["button", "a"], class_=re.compile(r"btn|button|cta", re.I))
        found = any(kw in b.get_text(strip=True).lower() for b in buttons for kw in CTA_KEYWORDS)
    return found, "Call-to-Action gefunden" if found else "Kein Call-to-Action gefunden"


def check_contact(soup, base_url, text):
    has_mailto = bool(soup.find("a", href=re.compile(r"^mailto:")))
    has_tel = bool(soup.find("a", href=re.compile(r"^tel:")))
    has_form = bool(soup.find("form"))
    has_contact_link = any(
        "kontakt" in a.get_text(strip=True).lower() or "contact" in a.get_text(strip=True).lower()
        for a in soup.find_all("a", href=True)
    )
    found = has_mailto or has_tel or has_form or has_contact_link
    detail = []
    if has_mailto: detail.append("E-Mail")
    if has_tel: detail.append("Telefon")
    if has_form: detail.append("Formular")
    if has_contact_link and not detail: detail.append("Kontakt-Link")
    msg = "Kontaktmöglichkeit vorhanden: " + ", ".join(detail) if found else "Keine Kontaktmöglichkeit gefunden"
    return found, msg


def check_person(soup, base_url, text):
    raw = soup.get_text(" ", strip=True)
    for pat in AUTHOR_PATTERNS:
        if re.search(pat, raw):
            return True, "Ansprechperson erkannt"
    has_class = bool(soup.find(class_=re.compile(r"vcard|author|person|contact", re.I)))
    if has_class:
        return True, "Ansprechperson erkannt (Klassen-Pattern)"
    return False, "Keine Ansprechperson erkennbar"


def check_transactional_keywords(soup, base_url, text):
    found = [kw for kw in TRANSACTIONAL_KEYWORDS if kw in text]
    if found:
        return True, f"Transaktionale Keywords gefunden: {', '.join(found[:5])}"
    return False, "Keine transaktionalen Keywords im Inhalt gefunden"


def check_author(soup, base_url, text):
    raw = soup.get_text(" ", strip=True)
    for pat in AUTHOR_PATTERNS:
        if re.search(pat, raw):
            return True, "Autorenschaft erkannt"
    if soup.find(class_=re.compile(r"author|autor|byline", re.I)):
        return True, "Autorenschaft erkannt (Klassen-Pattern)"
    for s in get_schema(soup):
        if s.get("author"):
            return True, "Autorenschaft via Schema.org erkannt"
    return False, "Keine Autorenschaft erkennbar"


def check_date(soup, base_url, text):
    if soup.find("time"):
        return True, "Datum vorhanden (<time>-Tag)"
    raw = soup.get_text(" ", strip=True)
    for pat in DATE_PATTERNS:
        m = re.search(pat, raw)
        if m:
            return True, f"Datum erkannt: {m.group()}"
    return False, "Kein Publikationsdatum gefunden"


def check_internal_links(soup, base_url, text):
    links = get_links(soup, base_url)
    internal = [l for l in links if l["is_internal"]]
    count = len(internal)
    if count >= 3:
        return True, f"{count} interne Links vorhanden"
    elif count > 0:
        return False, f"Nur {count} interne Link(s) – mindestens 3 empfohlen"
    return False, "Keine internen Links gefunden"


def check_external_links(soup, base_url, text):
    links = get_links(soup, base_url)
    external = [l for l in links if not l["is_internal"]]
    if external:
        return True, f"{len(external)} externe Link(s) vorhanden"
    return False, "Keine externen Links gefunden"


def check_price(soup, base_url, text):
    raw = soup.get_text(" ", strip=True)
    for pat in PRICE_PATTERNS:
        m = re.search(pat, raw, re.IGNORECASE)
        if m:
            return True, f"Preisangabe erkannt: {m.group()}"
    return False, "Kein Preis oder Kostenangabe gefunden"


def check_duration(soup, base_url, text):
    raw = soup.get_text(" ", strip=True)
    for pat in DURATION_PATTERNS:
        m = re.search(pat, raw, re.IGNORECASE)
        if m:
            return True, f"Dauer erkannt: {m.group()}"
    return False, "Keine Angabe zu Dauer oder Umfang gefunden"


def check_next_date(soup, base_url, text):
    keywords = ["start", "beginn", "nächste durchführung", "durchführung", "startdatum", "next date"]
    raw = soup.get_text(" ", strip=True).lower()
    for kw in keywords:
        idx = raw.find(kw)
        if idx >= 0:
            snippet = raw[idx:idx+100]
            for pat in DATE_PATTERNS:
                if re.search(pat, snippet, re.IGNORECASE):
                    return True, "Nächste Durchführung erkannt"
    return False, "Kein Startdatum / nächste Durchführung gefunden"


def check_target_audience(soup, base_url, text):
    raw = soup.get_text(" ", strip=True)
    for pat in AUDIENCE_PATTERNS:
        if re.search(pat, raw, re.IGNORECASE):
            return True, "Zielgruppe erkannt"
    return False, "Keine Zielgruppe definiert"


def check_certificate(soup, base_url, text):
    found = [kw for kw in CERTIFICATE_KEYWORDS if kw in text]
    if found:
        return True, f"Abschluss/Zertifikat erwähnt: {', '.join(found[:3])}"
    return False, "Kein Abschluss oder Zertifikat erwähnt"


def check_event_date(soup, base_url, text):
    if soup.find("time"):
        return True, "Datum vorhanden (<time>-Tag)"
    raw = soup.get_text(" ", strip=True)
    for pat in DATE_PATTERNS:
        m = re.search(pat, raw)
        if m:
            return True, f"Datum erkannt: {m.group()}"
    return False, "Kein Veranstaltungsdatum gefunden"


def check_event_location(soup, base_url, text):
    found = [kw for kw in LOCATION_KEYWORDS if kw in text]
    if found:
        return True, f"Ort/Format erkannt: {', '.join(found[:3])}"
    return False, "Kein Veranstaltungsort oder Format gefunden"


def check_speakers(soup, base_url, text):
    keywords = ["referent", "speaker", "dozent", "referentin", "keynote", "moderator"]
    found = [kw for kw in keywords if kw in text]
    if found:
        return True, "Referenten/Sprecher erkannt"
    return False, "Keine Referenten erkennbar"


def check_agenda(soup, base_url, text):
    found = [kw for kw in AGENDA_KEYWORDS if kw in text]
    if found:
        return True, f"Programm/Agenda erkannt: {', '.join(found)}"
    return False, "Kein Programm oder Agenda gefunden"


def check_deadline(soup, base_url, text):
    raw = soup.get_text(" ", strip=True)
    for pat in DEADLINE_PATTERNS:
        if re.search(pat, raw, re.IGNORECASE):
            return True, "Anmeldeschluss/Frist erkannt"
    return False, "Kein Anmeldeschluss gefunden"


def check_trust_signals(soup, base_url, text):
    keywords = [
        "akkreditiert", "akkreditierung", "zertifiziert", "ausgezeichnet",
        "referenz", "referenzen", "bewertung", "erfahrungsbericht",
        "testimonial", "empfehlung", "partner", "mitglied",
        "accredited", "certified", "award", "review", "testimonial",
    ]
    found = [kw for kw in keywords if kw in text]
    if found:
        return True, f"Trust-Signale erkannt: {', '.join(found[:3])}"
    has_ratings = bool(soup.find(class_=re.compile(r"rating|review|testimonial|trust|award", re.I)))
    if has_ratings:
        return True, "Trust-Signale erkannt (Klassen-Pattern)"
    return False, "Keine Trust-Signale gefunden"


def check_fact_list(soup, base_url, text):
    if soup.find("table"):
        return True, "Fact-Liste als Tabelle vorhanden"
    if soup.find("dl"):
        return True, "Fact-Liste als Definition-Liste vorhanden"
    info_box = soup.find(class_=re.compile(r"fact|info.?box|keydata|kennzahl|overview|steckbrief", re.I))
    if info_box:
        return True, "Fact-/Info-Box erkannt"
    return False, "Keine Fact-Liste oder strukturierte Übersicht gefunden"


def check_site_navigation(soup, base_url, text):
    if soup.find("nav"):
        return True, "Site-Navigation vorhanden (<nav>)"
    breadcrumb = soup.find(class_=re.compile(r"breadcrumb|breadcrumbs|bread-crumb", re.I))
    if breadcrumb:
        return True, "Breadcrumb-Navigation erkannt"
    side_nav = soup.find(class_=re.compile(r"sidebar|side-nav|sidenav|sub-nav|subnav|local-nav", re.I))
    if side_nav:
        return True, "Seitennavigation erkannt"
    return False, "Keine Site-Navigation erkennbar"


def check_person_with_contact(soup, base_url, text):
    person_ok, _ = check_person(soup, base_url, text)
    contact_ok, _ = check_contact(soup, base_url, text)
    if person_ok and contact_ok:
        return True, "Kontaktperson mit Kontaktdaten vorhanden"
    if person_ok:
        return False, "Ansprechperson erkannt, aber keine Kontaktdaten gefunden"
    if contact_ok:
        return False, "Kontaktdaten vorhanden, aber keine Ansprechperson erkennbar"
    return False, "Keine Kontaktperson und keine Kontaktdaten gefunden"


def check_infoveranstaltung(soup, base_url, text):
    keywords = [
        "infoveranstaltung", "infoabend", "informationsabend", "infoanlass",
        "tag der offenen tür", "open house", "open day",
        "schnuppertag", "orientierungsabend", "beratungsgespräch",
    ]
    found = [kw for kw in keywords if kw in text]
    if found:
        return True, f"Infoveranstaltung erkannt: {', '.join(found[:2])}"
    return False, "Keine Infoveranstaltung oder Infoabend erwähnt"


def check_cas_mas_sas(soup, base_url, text):
    patterns = [r"\bcas\b", r"\bmas\b", r"\bsas\b", r"\bdas\b"]
    raw = soup.get_text(" ", strip=True)
    for pat in patterns:
        if re.search(pat, raw, re.IGNORECASE):
            m = re.search(pat, raw, re.IGNORECASE)
            return True, f"Programmzuordnung erkannt: {m.group().upper()}"
    return False, "Keine Zuordnung zu CAS / MAS / SAS erkennbar"


def check_schema_article(soup, base_url, text):
    types = [s.get("@type", "") for s in get_schema(soup)]
    found = any(t in ["Article", "BlogPosting", "NewsArticle"] for t in types)
    return found, "Artikel-Schema Markup vorhanden" if found else "Kein Artikel-Schema Markup gefunden"


def check_schema_org(soup, base_url, text):
    found = any(s.get("@type") == "Organization" for s in get_schema(soup))
    return found, "Organisation-Schema vorhanden" if found else "Kein Organisation-Schema gefunden"


def check_schema_course(soup, base_url, text):
    found = any(s.get("@type") == "Course" for s in get_schema(soup))
    return found, "Kurs-Schema Markup vorhanden" if found else "Kein Kurs-Schema Markup gefunden"


def check_schema_event(soup, base_url, text):
    found = any(s.get("@type") == "Event" for s in get_schema(soup))
    return found, "Event-Schema Markup vorhanden" if found else "Kein Event-Schema Markup gefunden"


MODE_LABELS = {
    "content":    "Content & Autorität",
    "conversion": "Ausbildungs-Seite",
    "course":     "Weiterbildungs-Seite",
    "event":      "Event",
}

# ── Dispatcher ────────────────────────────────────────────────────────────

FN_MAP = {
    "check_cta": check_cta,
    "check_contact": check_contact,
    "check_person": check_person,
    "check_transactional_keywords": check_transactional_keywords,
    "check_author": check_author,
    "check_date": check_date,
    "check_internal_links": check_internal_links,
    "check_external_links": check_external_links,
    "check_price": check_price,
    "check_duration": check_duration,
    "check_next_date": check_next_date,
    "check_target_audience": check_target_audience,
    "check_certificate": check_certificate,
    "check_event_date": check_event_date,
    "check_event_location": check_event_location,
    "check_speakers": check_speakers,
    "check_agenda": check_agenda,
    "check_deadline": check_deadline,
    "check_schema_article": check_schema_article,
    "check_schema_org": check_schema_org,
    "check_schema_course": check_schema_course,
    "check_schema_event": check_schema_event,
    "check_trust_signals": check_trust_signals,
    "check_fact_list": check_fact_list,
    "check_site_navigation": check_site_navigation,
    "check_person_with_contact": check_person_with_contact,
    "check_infoveranstaltung": check_infoveranstaltung,
    "check_cas_mas_sas": check_cas_mas_sas,
}


# ── Haupt-Funktion ────────────────────────────────────────────────────────

def check_mode_analysis(soup: BeautifulSoup, base_url: str, mode_weights: dict) -> dict:
    issues = []
    warnings = []
    passed = []
    schema_results = []

    active_modes = {k: v for k, v in mode_weights.items() if v > 0}

    if not active_modes:
        return _build_result(issues, warnings, passed, {"schema_results": [], "active_modes": []})

    text = get_text(soup)

    for mode_key, weight in active_modes.items():
        checks = MODE_CHECKS.get(mode_key, [])
        for check in checks:
            fn = FN_MAP.get(check["fn"])
            if not fn:
                continue
            try:
                ok, msg = fn(soup, base_url, text)
            except Exception as e:
                ok, msg = False, f"Fehler bei Check: {str(e)}"

            result = {
                "code": check["code"],
                "label": check["label"],
                "desc": check["desc"],
                "mode": mode_key,
                "weight": weight,
                "ok": ok,
                "message": msg,
                "schema_only": check.get("schema_only", False),
            }

            if check.get("schema_only"):
                schema_results.append(result)
            elif ok:
                passed.append({
                    "code": check["code"],
                    "message": msg,
                })
            else:
                warnings.append({
                    "code": check["code"],
                    "message": msg,
                    "severity": "warning",
                })

    data = {
        "active_modes": list(active_modes.keys()),
        "schema_results": schema_results,
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
