# whitelist.py
# Zentrale Whitelist für alle Checks.
# Ergänzungen hier vornehmen – keine Änderungen in den Check-Dateien nötig.

# ── Überschriften ──────────────────────────────────────────────────────────
HEADING_DUPLICATES_WHITELIST = [
    "angebot", "angebote", "kontakt", "über uns", "ueber uns",
    "news", "aktuelles", "home", "startseite", "impressum",
    "datenschutz", "links", "downloads", "publikationen",
    "team", "partner", "weiteres", "informationen", "hinweise",
]

# ── URL-Pfad Whitelist ────────────────────────────────────────────────────
# URLs die einen dieser Pfad-Bestandteile enthalten werden beim Link-Check ignoriert.
URL_PATH_WHITELIST = [
    "/personensuche/person-detail-site",
    "/info-veranstaltungen/",
]

# ── URL-Parameter Whitelist ────────────────────────────────────────────────
# URLs die einen dieser Parameter enthalten werden beim Link-Check ignoriert.
URL_PARAM_WHITELIST = [
    "post_type=", "p=", "page_id=", "preview=true",
    "replytocom=", "doing_wp_cron", "ver=", "utm_",
    "fbclid=", "gclid=", "ref=", "session=", "token=",
]

# ── Link-Domain Whitelist ──────────────────────────────────────────────────
# Domains die beim Link-Check grundsätzlich übersprungen werden.
# Grund: Bot-Blocking, Login-Walls oder bekannte Consent-Probleme.
LINK_DOMAIN_WHITELIST = [
    "linkedin.com",       # Blockiert Bots kategorisch mit 999-Fehler
    "instagram.com",      # Blockiert nicht eingeloggte Bots
    "facebook.com",       # Blockiert Bots / Consent-Wall
    "zenodo.org",         # Bekanntes Bot-Blocking
    "researchgate.net",   # Bekanntes Bot-Blocking
]

# ── Alt-Attribute: Datei-Whitelist ─────────────────────────────────────────
# Einzelne Bilddateien die beim Alt-Attribut-Check ignoriert werden.
# SVG-Dateien werden generell in der Logik ignoriert (siehe alt_attributes.py).
ALT_ATTRIBUTE_FILENAME_WHITELIST = [
    "black-arrow.svg",
    # Weitere Dateien hier ergänzen:
    # "icon-arrow-right.svg",
]

# ── Alt-Attribute: Dateierweiterungen ignorieren ───────────────────────────
# Alle Bilder mit diesen Endungen werden beim Alt-Attribut-Check übersprungen.
ALT_ATTRIBUTE_EXTENSION_WHITELIST = [
    ".svg",   # SVGs sind meist dekorativ (Icons, Logos, Pfeile)
]

# ── Rechtschreibung: Whitelist ─────────────────────────────────────────────
# Wörter die beim Rechtschreibcheck ignoriert werden (Gross-/Kleinschreibung egal).
SPELLING_WHITELIST = {
    "ekkj", "mas", "cas", "das", "ba", "ifz", "study", "ikm", "ibr",
    "sa", "pibs", "dba", "sas", "mba", "sebwk",
    "hslu", "sdg", "isa", "isa-modul", "isa-modulen",
    "bachelor-studiengang", "bachelor-studiengängen",
    "master-studiengang", "master-studiengängen",
    "hslu-studierende", "minor", "major", "gastdozierende",
    "bsc", "msc", "zum",
    "know-how", "nonprofit management", "public", "tourism",
    "content management",
    "the", "it", "hours", "and", "lowers", "detection", "saq", "weiterbildungs-abc", "studies", "sur",
}
