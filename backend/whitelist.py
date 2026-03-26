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
# nicht als defekt oder Redirect gemeldet.
# Muster werden als Teilstring geprüft (case-insensitive).
URL_PARAM_WHITELIST = [
    "post_type=",
    "p=",
    "page_id=",
    "preview=true",
    "replytocom=",
    "doing_wp_cron",
    "ver=",
    "utm_",
    "fbclid=",
    "gclid=",
    "ref=",
    "session=",
    "token=",
]

# ── Alt-Attribute: Datei-Whitelist ─────────────────────────────────────────
# Bilddateien die beim Alt-Attribut-Check ignoriert werden.
# Eintragen: exakter Dateiname (nur Dateiname, nicht voller Pfad).
# Vergleich erfolgt case-insensitive.
#
# Wann einen Dateinamen hier eintragen?
# - Rein dekorative Grafiken die keinen inhaltlichen Mehrwert haben
# - Icons und UI-Elemente (Pfeile, Trennlinien, Hintergründe)
# - Technische Grafiken die nie beschriftet werden müssen
#
ALT_ATTRIBUTE_FILENAME_WHITELIST = [
    "black-arrow.svg",
    # Weitere Dateien hier ergänzen, z.B.:
    # "icon-arrow-right.svg",
    # "decorative-line.svg",
    # "logo-bg.png",
]
