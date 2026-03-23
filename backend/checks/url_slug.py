from urllib.parse import urlparse, unquote
import re


# Empfohlene URL-Länge
URL_MAX_LENGTH = 75
SLUG_MAX_LENGTH = 60
SLUG_MAX_SEGMENTS = 5

# Problematische Zeichen im Slug
PROBLEMATIC_CHARS = re.compile(r'[^a-z0-9\-\/\.]')

# Typische Parameter die auf dynamische/unoptimierte URLs hinweisen
PROBLEMATIC_PARAMS = {
    "sessionid", "sid", "phpsessid", "jsessionid",
    "utm_source", "utm_medium", "utm_campaign",  # Tracking-Parameter (OK in Ads, nicht in canonical)
    "ref", "source", "from",
}


def check_url_slug(url: str) -> dict:
    """
    Analysiert die URL/Slug einer Seite auf SEO-Kriterien:
    - URL-Länge
    - Sonderzeichen und Umlaute
    - Tiefe der URL-Struktur
    - Großbuchstaben
    - Underscores statt Bindestriche
    - Tracking-Parameter
    - Dateiendungen (.php, .html etc.)
    - Doppelte Slashes
    - Sinnvolle Slug-Länge
    """
    issues = []
    warnings = []
    passed = []

    parsed = urlparse(url)
    path = parsed.path
    query = parsed.query
    full_url = url

    data = {
        "url": url,
        "scheme": parsed.scheme,
        "domain": parsed.netloc,
        "path": path,
        "query": query,
        "segments": [],
    }

    # URL-Segmente analysieren
    segments = [s for s in path.split("/") if s]
    data["segments"] = segments
    slug = segments[-1] if segments else ""
    data["slug"] = slug

    # ── HTTPS ─────────────────────────────────────────────────────────────
    if parsed.scheme != "https":
        issues.append({
            "code": "URL_NOT_HTTPS",
            "message": f"URL verwendet kein HTTPS: {url}",
            "severity": "critical",
        })
    else:
        passed.append({"code": "URL_HTTPS", "message": "URL verwendet HTTPS ✓"})

    # ── URL-LÄNGE ─────────────────────────────────────────────────────────
    url_length = len(full_url)
    data["url_length"] = url_length

    if url_length > URL_MAX_LENGTH:
        warnings.append({
            "code": "URL_TOO_LONG",
            "message": f"URL zu lang ({url_length} Zeichen, empfohlen: max {URL_MAX_LENGTH}): {url}",
            "severity": "warning",
        })
    else:
        passed.append({"code": "URL_LENGTH_OK", "message": f"URL-Länge optimal ({url_length} Zeichen)."})

    # ── GROSSBUCHSTABEN ───────────────────────────────────────────────────
    if path != path.lower():
        issues.append({
            "code": "URL_UPPERCASE",
            "message": f"URL enthält Grossbuchstaben. Kann zu Duplicate Content führen: {path}",
            "severity": "warning",
        })
    else:
        passed.append({"code": "URL_LOWERCASE", "message": "URL ist komplett kleingeschrieben ✓"})

    # ── UMLAUTE & SONDERZEICHEN ───────────────────────────────────────────
    decoded_path = unquote(path)
    umlaut_pattern = re.compile(r'[äöüÄÖÜß]')
    has_umlauts = bool(umlaut_pattern.search(decoded_path))

    encoded_chars = re.compile(r'%[0-9A-Fa-f]{2}')
    has_encoded = bool(encoded_chars.search(path))

    if has_umlauts or has_encoded:
        warnings.append({
            "code": "URL_SPECIAL_CHARS",
            "message": (
                f"URL enthält Umlaute oder Sonderzeichen: {decoded_path}. "
                "Empfehlung: Umlaute ersetzen (ä→ae, ö→oe, ü→ue)."
            ),
            "severity": "warning",
        })
    else:
        passed.append({"code": "URL_NO_SPECIAL_CHARS", "message": "URL enthält keine Sonderzeichen oder Umlaute ✓"})

    # ── UNDERSCORES ───────────────────────────────────────────────────────
    if "_" in path:
        warnings.append({
            "code": "URL_UNDERSCORES",
            "message": f"URL verwendet Underscores statt Bindestriche: {path}. Google bevorzugt Bindestriche.",
            "severity": "warning",
        })
    else:
        passed.append({"code": "URL_HYPHENS", "message": "URL verwendet Bindestriche (korrekt) ✓"})

    # ── URL-TIEFE ─────────────────────────────────────────────────────────
    depth = len(segments)
    data["depth"] = depth

    if depth > SLUG_MAX_SEGMENTS:
        warnings.append({
            "code": "URL_TOO_DEEP",
            "message": f"URL-Struktur sehr tief ({depth} Ebenen, empfohlen: max {SLUG_MAX_SEGMENTS}): {path}",
            "severity": "warning",
        })
    else:
        passed.append({"code": "URL_DEPTH_OK", "message": f"URL-Tiefe angemessen ({depth} Ebenen) ✓"})

    # ── DOPPELTE SLASHES ──────────────────────────────────────────────────
    if "//" in path:
        warnings.append({
            "code": "URL_DOUBLE_SLASH",
            "message": f"URL enthält doppelte Slashes: {path}",
            "severity": "warning",
        })
    else:
        passed.append({"code": "URL_NO_DOUBLE_SLASH", "message": "Keine doppelten Slashes ✓"})

    # ── DATEIENDUNGEN ─────────────────────────────────────────────────────
    bad_extensions = re.compile(r'\.(php|asp|aspx|jsp|cfm|cgi)$', re.IGNORECASE)
    if bad_extensions.search(path):
        ext = bad_extensions.search(path).group()
        warnings.append({
            "code": "URL_FILE_EXTENSION",
            "message": f"URL enthält Dateiendung \"{ext}\". Empfehlung: Sprechende URLs ohne Endungen verwenden.",
            "severity": "info",
        })
    else:
        passed.append({"code": "URL_NO_BAD_EXTENSION", "message": "URL enthält keine technischen Dateiendungen ✓"})

    # ── QUERY-PARAMETER ───────────────────────────────────────────────────
    if query:
        params = {p.split("=")[0].lower() for p in query.split("&") if "=" in p}
        found_problematic = params & PROBLEMATIC_PARAMS
        if found_problematic:
            warnings.append({
                "code": "URL_TRACKING_PARAMS",
                "message": f"URL enthält Tracking-/Session-Parameter: {', '.join(found_problematic)}. Diese sollten nicht in der canonical URL sein.",
                "severity": "warning",
            })
        else:
            warnings.append({
                "code": "URL_HAS_PARAMS",
                "message": f"URL enthält Query-Parameter: ?{query}. Prüfen ob diese in der canonical URL nötig sind.",
                "severity": "info",
            })
    else:
        passed.append({"code": "URL_NO_PARAMS", "message": "URL enthält keine Query-Parameter ✓"})

    # ── SLUG-LÄNGE ────────────────────────────────────────────────────────
    if slug:
        slug_length = len(slug)
        data["slug_length"] = slug_length

        if slug_length > SLUG_MAX_LENGTH:
            warnings.append({
                "code": "SLUG_TOO_LONG",
                "message": f"Slug zu lang ({slug_length} Zeichen, empfohlen: max {SLUG_MAX_LENGTH}): \"{slug}\"",
                "severity": "warning",
            })
        elif slug_length < 3:
            warnings.append({
                "code": "SLUG_TOO_SHORT",
                "message": f"Slug sehr kurz ({slug_length} Zeichen): \"{slug}\"",
                "severity": "info",
            })
        else:
            passed.append({"code": "SLUG_LENGTH_OK", "message": f"Slug-Länge optimal ({slug_length} Zeichen): \"{slug}\" ✓"})

        # Zahlen-only Slug
        if re.match(r'^\d+$', slug):
            warnings.append({
                "code": "SLUG_NUMBERS_ONLY",
                "message": f"Slug besteht nur aus Zahlen: \"{slug}\". Sprechende Slugs sind SEO-freundlicher.",
                "severity": "warning",
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
