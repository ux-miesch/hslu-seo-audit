from bs4 import BeautifulSoup
from collections import Counter
import re
import math


# Stoppwörter Deutsch & Englisch
STOPWORDS_DE = {
    "der", "die", "das", "ein", "eine", "einer", "einem", "einen", "eines",
    "und", "oder", "aber", "doch", "sondern", "denn", "weil", "dass", "ob",
    "wenn", "als", "wie", "was", "wer", "wo", "wann", "warum", "welche",
    "welcher", "welches", "ist", "sind", "war", "waren", "wird", "werden",
    "wurde", "wurden", "hat", "haben", "hatte", "hatten", "wird", "worden",
    "ich", "du", "er", "sie", "es", "wir", "ihr", "sie", "Sie", "mich",
    "dich", "sich", "uns", "euch", "mir", "dir", "ihm", "ihr", "ihnen",
    "mein", "dein", "sein", "ihr", "unser", "euer", "in", "an", "auf",
    "für", "mit", "von", "zu", "bei", "nach", "aus", "über", "unter",
    "vor", "hinter", "neben", "zwischen", "durch", "ohne", "gegen", "um",
    "nicht", "kein", "keine", "keiner", "keinem", "keinen", "auch", "noch",
    "schon", "nur", "sehr", "mehr", "immer", "dann", "da", "hier", "dort",
    "so", "nun", "bereits", "dabei", "jedoch", "sowie", "deren", "dem",
    "den", "des", "im", "am", "zum", "zur", "vom", "ins", "ans", "aufs",
}

STOPWORDS_EN = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "can", "this", "that",
    "these", "those", "it", "its", "we", "you", "he", "she", "they",
    "their", "our", "your", "my", "his", "her", "i", "not", "no", "so",
}

STOPWORDS = STOPWORDS_DE | STOPWORDS_EN

# Schwellenwerte
KEYWORD_DENSITY_MIN = 0.5   # % – Keyword zu selten
MIN_WORD_LENGTH = 3
MIN_VOCABULARY_RICHNESS = 0.3  # Type-Token-Ratio


def extract_text_content(soup: BeautifulSoup) -> dict:
    """
    Extrahiert strukturierten Text: Titel, Headings, Body-Text.
    """
    # Title
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)

    # Meta Description
    meta_desc = ""
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if meta_tag:
        meta_desc = meta_tag.get("content", "").strip()

    # Headings
    headings_text = []
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = tag.get_text(strip=True)
        if text:
            headings_text.append({"level": tag.name, "text": text})

    # Body-Text (Hauptinhalt) – auf Kopie arbeiten damit das originale Soup nicht verändert wird
    body_text = ""
    soup_copy = BeautifulSoup(str(soup), "html.parser")
    main_area = (
        soup_copy.find("main")
        or soup_copy.find("article")
        or soup_copy.select_one("[role='main']")
        or soup_copy.find("body")
    )
    if main_area:
        for tag in main_area.find_all(["script", "style", "nav", "footer"]):
            tag.decompose()
        body_text = main_area.get_text(separator=" ", strip=True)

    # Gesamttext für Analyse
    full_text = f"{title} {meta_desc} {' '.join(h['text'] for h in headings_text)} {body_text}"

    return {
        "title": title,
        "meta_description": meta_desc,
        "headings": headings_text,
        "body_text": body_text,
        "full_text": full_text,
    }


def tokenize(text: str) -> list[str]:
    """Text in Wörter aufteilen, bereinigen."""
    words = re.findall(r'\b[a-zA-ZäöüÄÖÜß]{' + str(MIN_WORD_LENGTH) + r',}\b', text)
    return [w.lower() for w in words]


def calculate_tfidf_keywords(words: list[str], top_n: int = 15) -> list[dict]:
    """
    Berechnet die wichtigsten Wörter via TF (Term Frequency).
    Filtert Stoppwörter heraus.
    """
    filtered = [w for w in words if w not in STOPWORDS]
    if not filtered:
        return []

    total = len(filtered)
    freq = Counter(filtered)

    keywords = []
    for word, count in freq.most_common(top_n * 2):
        tf = (count / total) * 100
        keywords.append({
            "word": word,
            "count": count,
            "density": round(tf, 2),
        })

    return keywords[:top_n]


def check_vocabulary_richness(words: list[str]) -> dict:
    """
    Type-Token-Ratio (TTR): Verhältnis einzigartiger Wörter zu Gesamtwörtern.
    Hohe TTR = reicher Wortschatz, niedrige TTR = repetitiv.
    """
    if not words:
        return {"ttr": 0, "unique": 0, "total": 0}

    filtered = [w for w in words if w not in STOPWORDS and len(w) >= MIN_WORD_LENGTH]
    if not filtered:
        return {"ttr": 0, "unique": 0, "total": 0}

    unique = len(set(filtered))
    total = len(filtered)
    ttr = round(unique / total, 3)

    return {"ttr": ttr, "unique": unique, "total": total}


def check_keyword_in_important_places(
    keyword: str,
    content: dict,
) -> dict:
    """
    Prüft ob ein Keyword in den wichtigen SEO-Stellen vorkommt:
    Title, H1, Meta Description, Body.
    """
    kw = keyword.lower()
    result = {
        "in_title": kw in content["title"].lower(),
        "in_h1": any(kw in h["text"].lower() for h in content["headings"] if h["level"] == "h1"),
        "in_meta_description": kw in content["meta_description"].lower(),
        "in_headings": any(kw in h["text"].lower() for h in content["headings"]),
        "in_body": kw in content["body_text"].lower(),
    }
    result["score"] = sum(result.values())
    return result


def check_keywords(soup: BeautifulSoup, keywords: list[str] = None) -> dict:
    """
    Analysiert Keyword-Optimierung und semantische Vielfalt:
    - Automatische Top-Keywords Erkennung
    - Keyword-Dichte (zu wenig / zu viel)
    - Keyword in Title, H1, Meta-Description?
    - Vocabulary Richness (Type-Token-Ratio)
    - Semantische Vielfalt der Überschriften
    """
    issues = []
    warnings = []
    passed = []

    # Text extrahieren
    content = extract_text_content(soup)
    all_words = tokenize(content["full_text"])
    body_words = tokenize(content["body_text"])

    data = {
        "word_count": len(body_words),
        "top_keywords": [],
        "vocabulary": {},
        "keyword_analysis": [],
    }

    if len(body_words) < 50:
        warnings.append({
            "code": "CONTENT_TOO_SHORT",
            "message": f"Zu wenig Text für eine Keyword-Analyse ({len(body_words)} Wörter). Mindestens 50 empfohlen.",
            "severity": "warning",
        })
        return _build_result(issues, warnings, passed, data)

    # ── TOP KEYWORDS ERMITTELN ─────────────────────────────────────────────
    top_keywords = calculate_tfidf_keywords(all_words, top_n=15)
    data["top_keywords"] = top_keywords

    # ── VOCABULARY RICHNESS ────────────────────────────────────────────────
    vocab = check_vocabulary_richness(body_words)
    data["vocabulary"] = vocab

    if vocab["ttr"] < MIN_VOCABULARY_RICHNESS:
        warnings.append({
            "code": "LOW_VOCABULARY_RICHNESS",
            "message": (
                f"Geringer Wortschatz (TTR: {vocab['ttr']}). "
                f"Nur {vocab['unique']} einzigartige Wörter bei {vocab['total']} Gesamtwörtern. "
                "Mehr semantische Vielfalt empfohlen."
            ),
            "severity": "warning",
        })
    else:
        passed.append({
            "code": "VOCABULARY_RICHNESS_OK",
            "message": f"Gute semantische Vielfalt (TTR: {vocab['ttr']}, {vocab['unique']} einzigartige Wörter).",
        })

    # ── BENUTZERDEFINIERTE KEYWORDS PRÜFEN ────────────────────────────────
    if keywords:
        kw_analyses = []
        for keyword in keywords:
            placement = check_keyword_in_important_places(keyword, content)

            # Dichte im Body berechnen
            kw_words = tokenize(keyword)
            kw_count = sum(1 for w in body_words if w in kw_words)
            density = round((kw_count / len(body_words)) * 100, 2) if body_words else 0

            analysis = {
                "keyword": keyword,
                "density": density,
                "count": kw_count,
                "placement": placement,
            }
            kw_analyses.append(analysis)

            # Keyword nicht gefunden
            if kw_count == 0:
                issues.append({
                    "code": "KEYWORD_NOT_FOUND",
                    "message": f"Keyword \"{keyword}\" nicht im Seitentext gefunden.",
                    "severity": "critical",
                    "keyword": keyword,
                })
            elif density < KEYWORD_DENSITY_MIN:
                warnings.append({
                    "code": "KEYWORD_DENSITY_LOW",
                    "message": f"Keyword \"{keyword}\" zu selten ({density}% Dichte, Min: {KEYWORD_DENSITY_MIN}%).",
                    "severity": "warning",
                    "keyword": keyword,
                    "density": density,
                })
            else:
                passed.append({
                    "code": "KEYWORD_DENSITY_OK",
                    "message": f"Keyword \"{keyword}\" mit guter Dichte ({density}%).",
                    "keyword": keyword,
                })

            # Keyword in wichtigen Stellen?
            if not placement["in_title"]:
                warnings.append({
                    "code": "KEYWORD_NOT_IN_TITLE",
                    "message": f"Keyword \"{keyword}\" nicht im Title-Tag.",
                    "severity": "warning",
                    "keyword": keyword,
                })
            else:
                passed.append({"code": "KEYWORD_IN_TITLE", "message": f"Keyword \"{keyword}\" im Title vorhanden."})

            if not placement["in_h1"]:
                warnings.append({
                    "code": "KEYWORD_NOT_IN_H1",
                    "message": f"Keyword \"{keyword}\" nicht in der H1-Überschrift.",
                    "severity": "warning",
                    "keyword": keyword,
                })
            else:
                passed.append({"code": "KEYWORD_IN_H1", "message": f"Keyword \"{keyword}\" in H1 vorhanden."})

            if not placement["in_meta_description"]:
                warnings.append({
                    "code": "KEYWORD_NOT_IN_META",
                    "message": f"Keyword \"{keyword}\" nicht in der Meta-Description.",
                    "severity": "warning",
                    "keyword": keyword,
                })
            else:
                passed.append({"code": "KEYWORD_IN_META", "message": f"Keyword \"{keyword}\" in Meta-Description vorhanden."})

        data["keyword_analysis"] = kw_analyses

    # ── SEMANTISCHE VIELFALT DER ÜBERSCHRIFTEN ────────────────────────────
    heading_words = tokenize(" ".join(h["text"] for h in content["headings"]))
    heading_filtered = [w for w in heading_words if w not in STOPWORDS]

    if heading_filtered:
        heading_unique = len(set(heading_filtered))
        heading_total = len(heading_filtered)
        heading_ttr = round(heading_unique / heading_total, 2) if heading_total > 0 else 0

        if heading_ttr < 0.5 and heading_total > 5:
            warnings.append({
                "code": "HEADINGS_LOW_VARIETY",
                "message": f"Überschriften haben wenig semantische Vielfalt (TTR: {heading_ttr}). Mehr unterschiedliche Begriffe empfohlen.",
                "severity": "info",
            })
        else:
            passed.append({
                "code": "HEADINGS_VARIETY_OK",
                "message": f"Überschriften haben gute semantische Vielfalt (TTR: {heading_ttr}).",
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
