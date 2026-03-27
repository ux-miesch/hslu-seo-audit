"""
mode_checks.py
Definiert welche Soft-Faktoren pro Modus geprüft werden.
Ergänzungen hier vornehmen – keine Änderungen in mode_analysis.py nötig.

Schema.org-Checks sind mit schema_only=True markiert:
→ erscheinen nur in Tab 3 Detail-Ansicht, nicht in Einfach-Ansicht oder Tab 2.
"""

MODE_CHECKS = {

    "content": [
        {
            "code": "author_present",
            "label": "Autorenschaft sichtbar",
            "desc": "Ist ein Autor mit Name und Funktion auf der Seite erkennbar?",
            "fn": "check_author",
            "schema_only": False,
        },
        {
            "code": "date_present",
            "label": "Publikationsdatum sichtbar",
            "desc": "Ist ein Publikations- oder Aktualisierungsdatum angegeben?",
            "fn": "check_date",
            "schema_only": False,
        },
        {
            "code": "internal_links",
            "label": "Interne Verlinkung vorhanden",
            "desc": "Gibt es mindestens 3 interne Links im Hauptinhalt?",
            "fn": "check_internal_links",
            "schema_only": False,
        },
        {
            "code": "external_links",
            "label": "Externe Verlinkung vorhanden",
            "desc": "Gibt es Links auf externe autoritative Quellen?",
            "fn": "check_external_links",
            "schema_only": False,
        },
        {
            "code": "schema_article",
            "label": "Artikel-Schema Markup",
            "desc": "Ist strukturiertes Artikel-Markup vorhanden (Schema.org Article/BlogPosting)?",
            "fn": "check_schema_article",
            "schema_only": True,
        },
    ],

    "conversion": [
        {
            "code": "cta_present",
            "label": "Call-to-Action vorhanden",
            "desc": "Gibt es einen klar sichtbaren Button oder Link zur Handlung?",
            "fn": "check_cta",
            "schema_only": False,
        },
        {
            "code": "contact_present",
            "label": "Kontaktmöglichkeit vorhanden",
            "desc": "Gibt es eine E-Mail, Telefonnummer oder ein Kontaktformular?",
            "fn": "check_contact",
            "schema_only": False,
        },
        {
            "code": "person_present",
            "label": "Ansprechperson sichtbar",
            "desc": "Ist eine konkrete Person mit Name sichtbar?",
            "fn": "check_person",
            "schema_only": False,
        },
        {
            "code": "transactional_keywords",
            "label": "Transaktionale Keywords im Inhalt",
            "desc": "Werden Wörter wie «anmelden», «buchen», «kaufen» im Seiteninhalt verwendet?",
            "fn": "check_transactional_keywords",
            "schema_only": False,
        },
        {
            "code": "schema_org",
            "label": "Organisation-Schema Markup",
            "desc": "Ist strukturiertes Organisations-Markup vorhanden (Schema.org Organization)?",
            "fn": "check_schema_org",
            "schema_only": True,
        },
    ],

    "course": [
        {
            "code": "price_present",
            "label": "Preis angegeben",
            "desc": "Ist ein Preis oder Kostenpunkt angegeben?",
            "fn": "check_price",
            "schema_only": False,
        },
        {
            "code": "duration_present",
            "label": "Dauer und Umfang angegeben",
            "desc": "Ist die Kursdauer oder der Umfang erkennbar?",
            "fn": "check_duration",
            "schema_only": False,
        },
        {
            "code": "next_date_present",
            "label": "Nächste Durchführung sichtbar",
            "desc": "Ist das nächste Startdatum angegeben?",
            "fn": "check_next_date",
            "schema_only": False,
        },
        {
            "code": "target_audience",
            "label": "Zielgruppe definiert",
            "desc": "Ist beschrieben für wen der Kurs geeignet ist?",
            "fn": "check_target_audience",
            "schema_only": False,
        },
        {
            "code": "certificate_present",
            "label": "Abschluss / Zertifikat erwähnt",
            "desc": "Wird ein Abschluss, Zertifikat oder Diplom erwähnt?",
            "fn": "check_certificate",
            "schema_only": False,
        },
        {
            "code": "cta_present",
            "label": "Anmelde-CTA vorhanden",
            "desc": "Gibt es einen klaren Anmelde-Button oder -Link?",
            "fn": "check_cta",
            "schema_only": False,
        },
        {
            "code": "schema_course",
            "label": "Kurs-Schema Markup",
            "desc": "Ist strukturiertes Kurs-Markup vorhanden (Schema.org Course)?",
            "fn": "check_schema_course",
            "schema_only": True,
        },
    ],

    "event": [
        {
            "code": "event_date_present",
            "label": "Datum und Zeit sichtbar",
            "desc": "Ist das Veranstaltungsdatum klar erkennbar?",
            "fn": "check_event_date",
            "schema_only": False,
        },
        {
            "code": "event_location_present",
            "label": "Ort / Format angegeben",
            "desc": "Ist der Veranstaltungsort oder das Format (online/hybrid/vor Ort) angegeben?",
            "fn": "check_event_location",
            "schema_only": False,
        },
        {
            "code": "cta_present",
            "label": "Anmelde-CTA vorhanden",
            "desc": "Gibt es einen klaren Anmelde-Button oder -Link?",
            "fn": "check_cta",
            "schema_only": False,
        },
        {
            "code": "price_present",
            "label": "Preis / Kosten angegeben",
            "desc": "Ist ein Preis oder «kostenlos» angegeben?",
            "fn": "check_price",
            "schema_only": False,
        },
        {
            "code": "speakers_present",
            "label": "Referenten sichtbar",
            "desc": "Sind Referenten oder Sprecher mit Name erkennbar?",
            "fn": "check_speakers",
            "schema_only": False,
        },
        {
            "code": "agenda_present",
            "label": "Programm / Agenda vorhanden",
            "desc": "Gibt es ein Programm oder eine Agenda?",
            "fn": "check_agenda",
            "schema_only": False,
        },
        {
            "code": "deadline_present",
            "label": "Anmeldeschluss sichtbar",
            "desc": "Ist eine Frist oder ein Anmeldeschluss angegeben?",
            "fn": "check_deadline",
            "schema_only": False,
        },
        {
            "code": "schema_event",
            "label": "Event-Schema Markup",
            "desc": "Ist strukturiertes Event-Markup vorhanden (Schema.org Event)?",
            "fn": "check_schema_event",
            "schema_only": True,
        },
    ],
}
