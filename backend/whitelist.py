# whitelist.py
# Zentrale Whitelist für alle Checks.
# Ergänzungen hier vornehmen – keine Änderungen in den Check-Dateien nötig.

# ── Überschriften ──────────────────────────────────────────────────────────
# Begriffe die nicht als Duplikat-Überschrift gemeldet werden.
# Vergleich erfolgt case-insensitive und mit strip().
HEADING_DUPLICATES_WHITELIST = [
    "angebot",
    "angebote",
    "kontakt",
    "über uns",
    "ueber uns",
    "news",
    "aktuelles",
    "home",
    "startseite",
    "impressum",
    "datenschutz",
    "links",
    "downloads",
    "publikationen",
    "team",
    "partner",
    "weiteres",
    "informationen",
    "hinweise",
]

# ── URL-Parameter Whitelist ────────────────────────────────────────────────
# URLs die einen dieser Parameter enthalten werden beim Link-Check
# nicht als defekt oder Redirect gemeldet – sie werden ignoriert.
# Muster werden als Teilstring geprüft (case-insensitive).
URL_PARAM_WHITELIST = [
    "post_type=",        # WordPress interne Post-Type-Links
    "p=",                # WordPress Preview-Links (?p=12345)
    "page_id=",          # WordPress Seiten-ID
    "preview=true",      # WordPress Vorschau
    "replytocom=",       # WordPress Kommentar-Antworten
    "doing_wp_cron",     # WordPress Cron-Jobs
    "ver=",              # Asset-Versionierung
    "utm_",              # Analytics-Parameter (utm_source, utm_medium etc.)
    "fbclid=",           # Facebook Click ID
    "gclid=",            # Google Click ID
    "ref=",              # Referral-Parameter
    "session=",          # Session-IDs
    "token=",            # Token-Parameter
]

# Platzhalter für spätere Erweiterungen
# ALT_ATTRIBUTE_WHITELIST = []
# KEYWORD_STOPWORDS = []
