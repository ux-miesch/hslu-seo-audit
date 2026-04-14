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
            "code": "trust_signals",
            "label": "Trust-Signale vorhanden",
            "desc": "Sind Vertrauenssignale wie Akkreditierungen, Referenzen oder Bewertungen erkennbar?",
            "fn": "check_trust_signals",
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
            "code": "fact_list",
            "label": "Fact-Liste vorhanden",
            "desc": "Gibt es eine strukturierte Übersicht mit Kerninformationen (Tabelle, Liste, Info-Box)?",
            "fn": "check_fact_list",
            "schema_only": False,
        },
        {
            "code": "site_navigation",
            "label": "Site-Navigation erkennbar",
            "desc": "Ist eine Navigationsstruktur (Breadcrumb, Seitennavigation) vorhanden?",
            "fn": "check_site_navigation",
            "schema_only": False,
        },
        {
            "code": "person_with_contact",
            "label": "Kontaktperson inkl. Kontaktdaten",
            "desc": "Ist eine Ansprechperson mit Kontaktmöglichkeit (E-Mail oder Telefon) sichtbar?",
            "fn": "check_person_with_contact",
            "schema_only": False,
        },
        {
            "code": "infoveranstaltung",
            "label": "Infoveranstaltung erwähnt",
            "desc": "Wird auf eine Infoveranstaltung, einen Infoabend oder Tag der offenen Tür hingewiesen?",
            "fn": "check_infoveranstaltung",
            "schema_only": False,
        },
        {
            "code": "cta_present",
            "label": "CTA klar sichtbar",
            "desc": "Gibt es einen klar sichtbaren Button oder Link zur Handlung?",
            "fn": "check_cta",
            "schema_only": False,
        },
        {
            "code": "contact_present",
            "label": "Kontaktdaten vorhanden",
            "desc": "Gibt es eine E-Mail, Telefonnummer oder ein Kontaktformular?",
            "fn": "check_contact",
            "schema_only": False,
        },
        {
            "code": "transactional_keywords",
            "label": "Transaktionale Keywords im Inhalt",
            "desc": "Werden Wörter wie «anmelden», «buchen», «bewerben» im Seiteninhalt verwendet?",
            "fn": "check_transactional_keywords",
            "schema_only": False,
        },
        {
            "code": "duration_present",
            "label": "Dauer und Umfang angegeben",
            "desc": "Ist die Dauer oder der Umfang des Angebots erkennbar?",
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
            "code": "certificate_present",
            "label": "Abschluss / Zertifikat erwähnt",
            "desc": "Wird ein Abschluss, Zertifikat oder Diplom erwähnt?",
            "fn": "check_certificate",
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
            "code": "fact_list",
            "label": "Fact-Liste vorhanden",
            "desc": "Gibt es eine strukturierte Übersicht mit Kerninformationen (Tabelle, Liste, Info-Box)?",
            "fn": "check_fact_list",
            "schema_only": False,
        },
        {
            "code": "site_navigation",
            "label": "Site-Navigation erkennbar",
            "desc": "Ist eine Navigationsstruktur (Breadcrumb, Seitennavigation) vorhanden?",
            "fn": "check_site_navigation",
            "schema_only": False,
        },
        {
            "code": "person_with_contact",
            "label": "Kontaktperson inkl. Kontaktdaten",
            "desc": "Ist eine Ansprechperson mit Kontaktmöglichkeit (E-Mail oder Telefon) sichtbar?",
            "fn": "check_person_with_contact",
            "schema_only": False,
        },
        {
            "code": "infoveranstaltung",
            "label": "Infoveranstaltung erwähnt",
            "desc": "Wird auf eine Infoveranstaltung, einen Infoabend oder Tag der offenen Tür hingewiesen?",
            "fn": "check_infoveranstaltung",
            "schema_only": False,
        },
        {
            "code": "cta_present",
            "label": "CTA klar sichtbar",
            "desc": "Gibt es einen klar sichtbaren Button oder Link zur Handlung?",
            "fn": "check_cta",
            "schema_only": False,
        },
        {
            "code": "contact_present",
            "label": "Kontaktdaten vorhanden",
            "desc": "Gibt es eine E-Mail, Telefonnummer oder ein Kontaktformular?",
            "fn": "check_contact",
            "schema_only": False,
        },
        {
            "code": "transactional_keywords",
            "label": "Transaktionale Keywords im Inhalt",
            "desc": "Werden Wörter wie «anmelden», «buchen», «bewerben» im Seiteninhalt verwendet?",
            "fn": "check_transactional_keywords",
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
            "code": "certificate_present",
            "label": "Abschluss / Zertifikat erwähnt",
            "desc": "Wird ein Abschluss, Zertifikat oder Diplom erwähnt?",
            "fn": "check_certificate",
            "schema_only": False,
        },
        {
            "code": "cas_mas_sas",
            "label": "Zuordnung CAS / MAS / SAS",
            "desc": "Ist die Zuordnung zu einem CAS-, MAS- oder SAS-Programm erkennbar?",
            "fn": "check_cas_mas_sas",
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
    ],
}
