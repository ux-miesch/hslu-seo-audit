# SEO Audit Tool – HSLU

Internes SEO-Audit-Tool der HSLU. Analysiert einzelne URLs oder ganze Websites auf technische und inhaltliche SEO-Qualität. Das Frontend läuft auf GitHub Pages, das Backend auf Render.com.

> **Hinweis zum aktuellen Setup:** Git, Render.com und die SMTP-Mail-Logik basieren auf «Best Effort» und wurden pragmatisch aufgesetzt. Im Rahmen eines offiziellen IT-Projekts müssen diese Komponenten neu und sauber aufgebaut werden (inkl. SLA, Monitoring, Backup, HSLU-Infrastruktur). Die Programm-Logik (Checks, Scoring, Audit-Runner) bleibt als Anforderungsdokumentation erhalten und kann in jeder geeigneten Technologie neu implementiert werden.

---

## Audit-Typen

Das Tool unterscheidet zwischen zwei grundlegend verschiedenen Audit-Modi:

### Einzelseiten-Audit (`single-audits.html`)
- Manuelle Prüfung einer einzelnen URL
- Ergebnis wird **30 Tage** gespeichert, danach automatisch gelöscht (TTL)
- Öffentlich zugänglich via Link (kein Login erforderlich)
- Geeignet für schnelle Einzelprüfungen und Sharing

### Projekt-Audit (`projects.html` / `report.html`)
- Automatisiertes Crawling ganzer Websitebereiche
- Ergebnisse werden **dauerhaft** gespeichert (kein automatisches Löschen)
- Wöchentliche oder monatliche Wiederholung via Scheduler
- Passwortgeschützt, mit Projekt-Token für externe Redakteur:innen
- Geeignet für laufende Qualitätssicherung ganzer Domains

---

## Projektstruktur

```
hslu-seo-audit/
├── index.html              ← Einzelseiten-Audit (Startseite)
├── projects.html           ← Projektverwaltung (Mehrseiten-Audit)
├── report.html             ← Audit-Berichte
├── single-audits.html      ← Einzelseiten-Audit (öffentlich, mit Link)
├── spelling.html           ← Rechtschreibprüfung / Whitelist-Verwaltung
├── admin.html              ← Admin-Panel (passwortgeschützt)
├── build.sh                ← Version setzen + git push
├── deploy.sh               ← Vollständiger Deploy-Prozess
├── start.sh                ← Backend lokal starten
├── render.yaml             ← Render.com-Konfiguration
├── .python-version         ← Python 3.11.9
├── frontend/
│   └── assets/
│       └── HSLU_Logo_DE_Weiss_rgb.svg
└── backend/
    ├── main.py             ← FastAPI App, Lifespan, Router-Registration
    ├── audit_runner.py     ← Check-Orchestrierung (parallel, asyncio)
    ├── crawler.py          ← Seiten-Crawler, Content-Hash
    ├── database.py         ← SQLite pro Projekt (WAL-Mode), Schema-Migration
    ├── scheduler.py        ← APScheduler (wöchentl./monatl. Auto-Audits)
    ├── single_audits.py    ← Einzelaudit-DB (mit TTL + Cleanup)
    ├── mode_checks.py      ← Seitentyp-Definitionen
    ├── whitelist.py        ← Zentrale Ausnahmelisten
    ├── requirements.txt
    ├── gtm_credentials.json  ← GTM API-Credentials (git-ignored)
    ├── checks/
    │   ├── meta_texts.py
    │   ├── headings.py
    │   ├── broken_links.py
    │   ├── alt_attributes.py
    │   ├── spelling.py
    │   ├── keywords.py
    │   ├── url_slug.py
    │   ├── mode_analysis.py
    │   └── sea.py
    └── routers/
        ├── projects.py            ← Projekt-CRUD, Crawl, Audit, E-Mail
        ├── spelling_candidates.py ← Rechtschreib-Whitelist/Blacklist
        ├── admin.py               ← Admin-Endpunkte
        ├── single_audits.py       ← Einzelaudit-API
        └── feedback.py            ← Feedback-E-Mail an dms@hslu.ch
```

---

## Checks

| Check | Beschreibung |
|---|---|
| **Meta-Texte** | Title, Meta-Description, Canonical, Robots, Open Graph |
| **Überschriften** | H1–H6 Struktur, Hierarchie, Duplikate, Länge |
| **Defekte Links** | Erreichbarkeit aller Links, Weiterleitungen, Bot-Blocking |
| **Alt-Attribute** | Bilder, iFrames, PDFs, Videos |
| **Rechtschreibung** | Fehler via LanguageTool (de-CH / fr-CH / it-CH / en-US) |
| **Keywords & Semantik** | Keyword-Dichte, Platzierung, Wortschatz-Vielfalt |
| **URL / Slug** | HTTPS, Länge, Sonderzeichen, Tiefe, Parameter |
| **Seitentyp-Analyse** | Soft-Faktoren je nach Seitentyp (Web-Site, Content-Blog, Event-Seite, Nichts spezifisches) |
| **Kampagnen-Check (SEA)** | Google Tag Manager API – optional, nur auf Anfrage |

Die Sprache wird automatisch aus der URL erkannt (z.B. `/de/`, `/fr/`, `/en/`) und per `langdetect` aus dem Seiteninhalt verifiziert.

→ Detaillierte Test-Logiken siehe **Appendix** am Ende dieses Dokuments sowie die vollständige Dokumentation im OneNote.

---

## Features

### Projektverwaltung
- Mehrere Projekte (je eigene SQLite-DB mit WAL-Mode)
- Crawling bis zu 600 Seiten pro Projekt (paketbasiert, 600 Seiten/Paket)
- Content-Hash-Vergleich für inkrementelle Audits (nur geänderte Seiten werden neu auditiert)
- Unterbrochene Audits werden nach Backend-Neustart automatisch fortgesetzt
- Projekttypen: Web-Site, Content-Blog, Event-Seite, Nichts spezifisches

### Automatische Audits (Scheduler)
- Wöchentliche oder monatliche Audits via APScheduler
- Slot-Verteilung über Wochentage (Mo–Fr) und Stunden (00:00–07:00) zur Lastverteilung
- E-Mail-Benachrichtigung nach Abschluss (SMTP via Metanet)

### Einzelseiten-Audit
- Öffentlich zugänglich via `single-audits.html`
- Ergebnis-Link mit 30-Tage-TTL (automatisches Ablaufen + Cleanup)

### Zugangssystem
- **Admin-Passwort:** Zugang zu `projects.html`, `admin.html`, `single-audits.html`, `spelling.html`
- **Projekt-Token:** Pro Projekt generierter Token für externe Redakteur:innen (Zugang nur zu Rapport und Spelling-Liste des eigenen Projekts)

### Rechtschreibprüfung
- Eigene Whitelist/Blacklist-Verwaltung via `spelling.html`
- Persistierte Kandidaten in `spelling.db`
- Projektgefilterte Ansicht für Redakteur:innen via Link mit Token

### Feedback
- Feedback-Formular im Footer sendet E-Mail an `dms@hslu.ch`

---

## Deployment

> **Hinweis:** Das aktuelle Deployment-Setup (GitHub Pages + Render.com) ist ein «Best Effort»-Setup ohne SLA oder offizielles HSLU-Monitoring. Es ist für den produktiven Einsatz geeignet, soll aber im Rahmen eines IT-Projekts auf HSLU-eigene Infrastruktur migriert werden.

- **Frontend:** GitHub Pages → https://ux-miesch.github.io/hslu-seo-audit
- **Backend:** Render.com (Frankfurt, Starter Plan) → https://hslu-seo-audit.onrender.com

```bash
bash deploy.sh
```

`deploy.sh` ruft `build.sh` auf: setzt die Build-Version in allen HTML-Dateien, committed und pusht auf GitHub. Render.com deployed das Backend automatisch via `render.yaml`.

---

## Lokale Entwicklung

```bash
cd ~/Documents/Claude-Code/hslu-seo-audit
source venv/bin/activate
bash start.sh
```

Backend läuft auf: http://localhost:8000  
API-Dokumentation: http://localhost:8000/docs

---

## Umgebungsvariablen

Werden lokal via `.env` gesetzt, auf Render.com via Environment Variables:

| Variable | Beschreibung |
|---|---|
| `SMTP_HOST` | SMTP-Server für E-Mail-Versand |
| `SMTP_PORT` | SMTP-Port (Standard: 465) |
| `SMTP_USER` | SMTP-Benutzername |
| `SMTP_PASS` | SMTP-Passwort |
| `ADMIN_PASSWORD` | Passwort für das Admin-Panel |
| `DB_PATH` | Pfad für SQLite-Datenbanken (optional, Standard: `backend/`) |
| `REPORT_BASE_URL` | Basis-URL für Berichts-Links in E-Mails (optional) |

`.env` ist git-ignored. `backend/gtm_credentials.json` ist git-ignored.

---

## Technologie

- **Backend:** Python 3.11, FastAPI, httpx, BeautifulSoup4, asyncio
- **Datenbank:** SQLite (WAL-Mode, pro Projekt)
- **Scheduler:** APScheduler
- **Rechtschreibung:** LanguageTool Public API
- **Spracherkennung:** langdetect
- **Frontend:** Vanilla HTML / CSS / JS
- **Hosting:** Render.com (Backend) + GitHub Pages (Frontend)

> Die Wahl der Technologie ist nicht zwingend. Das Tool kann in jeder geeigneten Sprache und Infrastruktur neu implementiert werden. Entscheidend sind die Anforderungen und die Check-Logik – nicht der technische Stack.

---

---

# Appendix – Test-Logiken (Kurzübersicht)

> Vollständige Dokumentation aller Test-Logiken, Parameter und Beispiele im OneNote:  
> **[hslu-seo-audit – OneNote Dokumentation](https://hsluzern.sharepoint.com/sites/rs_mk_marketing-kommunikation/_layouts/Doc.aspx?sourcedoc=%7b00DF00EA-F590-45ED-A798-53FFEDC2A9E5%7d&wd=target%28Web%2FSEA%20SEO.one%7C4DEA980F-00ED-4F39-9B61-7F68DD9995B5%2Fhslu-seo-audit%7C7C799611-7740-7749-8276-75F0CB9BD46E%2F%29&wdpartid=%7b4165A66E-15AD-210D-2430-DE5D84E82D83%7d%7b1%7d&wdsectionfileid=%7b75234D02-4C39-441A-9310-0F9FC234E8E0%7d&end)**

---

## Score-System

Jede Seite erhält einen Score von **0–100**. Der Gesamtscore ist der Durchschnitt aller aktiven Checks. Fehler ziehen Punkte ab:

| Schwere | Abzug |
|---|---|
| Kritisch | −20 Punkte |
| Mittel | −10 Punkte |
| Gering | −5 Punkte |

**Farbskala:**

| Farbe | Score | Bedeutung |
|---|---|---|
| 🟢 Grün | 99–100 | Ausgezeichnet |
| 🔵 Cyan | 66–98 | Gut – kleinere Optimierungen möglich |
| 🟡 Gelb | 33–65 | Verbesserungswürdig |
| 🟣 Magenta | 0–32 | Kritisch – sofort handeln |

---

## A1 – Meta-Texte

Prüft `<title>`, `<meta name="description">`, Canonical-Tag, Robots-Tag und Open Graph.

| Kriterium | Abzug |
|---|---|
| Title fehlt | −20 |
| Title zu lang (>60 Zeichen) oder zu kurz (<30 Zeichen) | −10 |
| Description fehlt | −20 |
| Description zu lang (>160 Zeichen) oder zu kurz (<70 Zeichen) | −10 |
| Kein Canonical-Tag (ausser HSLU-Seiten: Info-Hinweis, kein Abzug) | −5 |
| Robots: noindex gesetzt | −20 |

---

## A2 – Überschriften

Prüft `<h1>`–`<h3>`. H4–H6 werden ignoriert.

| Kriterium | Abzug |
|---|---|
| Keine Überschriften vorhanden | −20 |
| H1 fehlt | −20 |
| Mehrere H1 | −10 |
| H2 fehlt | −20 |
| H3 ohne H2 | −10 |
| Leere Überschrift | −10 pro Stück |
| Überschrift >70 Zeichen | −5 pro Stück |
| Doppelte Überschrift | −5 pro Duplikat |

---

## A3 – Defekte Links

Prüft alle `<a href>`-Links auf Erreichbarkeit via HTTP-Request.

| Status | Behandlung |
|---|---|
| 200–399 | OK – kein Eintrag |
| 4xx / 5xx | Fehler – Abzug je nach Typ |
| Timeout (>8s) | Info – kein Abzug |
| Bot-Blocking (403/429/999) | Info – kein Abzug |
| Consent-Wall / Redirect | Info – kein Abzug |

**Abzüge:**

| Typ | Abzug |
|---|---|
| Interner 404 | −20 |
| Externer 404 / 5xx | −10 |

**Nicht geprüft:** `mailto:`, `tel:`, `javascript:`, `#`, Dateidownloads (PDF, ZIP etc.), Personenprofil-URLs (`/personensuche/`, `pid=`), Social-Media-Domains (LinkedIn, Instagram etc.).

---

## A4 – Alt-Attribute

Prüft `<img>`, `<video>`, `<iframe>`, PDF-Links auf vorhandene und sinnvolle Beschriftungen.

| Kriterium | Abzug |
|---|---|
| Bild ohne Alt-Text | −10 pro Bild |
| Alt-Text zu kurz (<3 Zeichen) | −5 pro Bild |
| Dekoratives Bild ohne `alt=""` | −5 |

---

## A5 – Rechtschreibung

Prüft den sichtbaren Seitentext via LanguageTool Public API.

- Sprache wird automatisch erkannt (HTML `lang`-Attribut + `langdetect`)
- Unterstützte Sprachen: `de-CH`, `fr-CH`, `it-CH`, `en-US`
- Strukturelle CMS-Fehler (z.B. Leerzeichen vor `?`) werden als Info klassifiziert (kein Abzug)
- Gefundene Kandidaten werden in `spelling.db` gespeichert und können via `spelling.html` whitelistet oder ignoriert werden

| Schwere | Abzug |
|---|---|
| Kritischer Tippfehler | −10 |
| Warnung / Grammatik | −5 |
| Info (CMS-Fehler) | 0 |

---

## A6 – Keywords & Semantik

Prüft Keyword-Dichte, Platzierung und Wortschatz-Vielfalt.

| Kriterium | Abzug |
|---|---|
| Keyword nicht gefunden | −20 |
| Keyword-Dichte <0.5% | −10 |
| Wortschatz zu arm (TTR <0.3) | −10 |
| Keyword fehlt in Title / H1 / Meta | je −5 |
| Überschriften zu eintönig (TTR <0.5) | −5 |

Ohne benutzerdefinierte Keywords: max. −15 Punkte (TTR + Heading-Vielfalt).

---

## A7 – URL / Slug

Prüft ausschliesslich die URL-Struktur – ohne Seiteninhalt zu laden.

| Kriterium | Abzug |
|---|---|
| Kein HTTPS | −20 |
| URL zu lang (>75 Zeichen) | −10 |
| Grossbuchstaben im Pfad | −10 |
| Umlaute / Sonderzeichen | −10 |
| Unterstriche statt Bindestriche | −5 |
| URL-Tiefe >5 Ebenen | −5 |
| Doppelte Slashes | −5 |
| Technische Dateiendungen (.php, .asp etc.) | −5 |
| Tracking-Parameter (utm_, sessionid etc.) | −5 |
| Slug zu lang (>60 Zeichen) oder zu kurz (<3 Zeichen) | −5 |

---

## A8 – Seitentyp-Analyse

Prüft seitentyp-spezifische Soft-Faktoren. Der Typ wird beim Projekt-Erstellen festgelegt oder beim Einzeltest automatisch erkannt.

### Web-Site
| Kriterium |
|---|
| Fact-Liste / Info-Box vorhanden |
| Site-Navigation erkennbar |
| Kontaktperson mit Kontaktdaten |
| Infoveranstaltung erwähnt |
| CTA klar sichtbar |
| Kontaktdaten vorhanden |
| Transaktionale Keywords (anmelden, bewerben etc.) |
| Dauer und Umfang angegeben |
| Nächste Durchführung / Startdatum |
| Abschluss / Zertifikat erwähnt |

### Content-Blog
| Kriterium |
|---|
| Autorenschaft sichtbar |
| Publikationsdatum vorhanden |
| Interne Verlinkung (min. 3 Links) |
| Externe Verlinkung vorhanden |
| Trust-Signale (Referenzen, Akkreditierungen) |

### Event-Seite
| Kriterium |
|---|
| Datum & Zeit sichtbar |
| Ort / Format angegeben |
| Anmelde-CTA vorhanden |
| Preis / Kosten angegeben |
| Referenten sichtbar |
| Programm / Agenda vorhanden |

### Nichts spezifisches
Alle obigen Checks kombiniert – kein Check ist Pflicht, Abzüge sind geringer gewichtet.

---

## A9 – Kampagnen-Check (SEA)

Optionaler Check via Google Tag Manager API. Prüft ob aktive Kampagnen-Tags vorhanden sind (Google Ads, Meta Pixel, LinkedIn Insight Tag).

- Nur für HSLU-Seiten verfügbar
- Erfordert `gtm_credentials.json` (git-ignored)
- Wird nicht automatisch aktiviert – nur auf explizite Anfrage

---

*Letzte Aktualisierung: Mai 2026 – DMS HSLU*
