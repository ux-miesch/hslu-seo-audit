# SEO Audit Tool – HSLU

Internes SEO-Audit-Tool der HSLU. Analysiert einzelne URLs oder ganze Websites auf technische und inhaltliche SEO-Qualität. Das Frontend läuft auf GitHub Pages, das Backend auf Render.com.

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
        ├── projects.py         ← Projekt-CRUD, Crawl, Audit, E-Mail
        ├── spelling_candidates.py ← Rechtschreib-Whitelist/Blacklist
        ├── admin.py            ← Admin-Endpunkte
        ├── single_audits.py    ← Einzelaudit-API
        └── feedback.py         ← Feedback-E-Mail an dms@hslu.ch
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
| **Seitentyp-Analyse** | Soft-Faktoren je nach Seitentyp (Conversion, Content, etc.) |
| **Kampagnen-Check (SEA)** | Google Tag Manager API – optional, nur auf Anfrage |

Die Sprache wird automatisch aus der URL erkannt (z. B. `/de/`, `/fr/`, `/en/`).

---

## Features

### Projektverwaltung
- Mehrere Projekte (je eigene SQLite-DB mit WAL-Mode)
- Crawling bis zu 200 Seiten pro Projekt
- Paket-basiertes Auditing für grosse Projekte (600 Seiten/Paket)
- Unterbrochene Audits werden nach Backend-Neustart automatisch fortgesetzt
- Content-Hash-Vergleich für inkrementelle Audits (nur geänderte Seiten)

### Automatische Audits (Scheduler)
- Wöchentliche oder monatliche Audits via APScheduler
- Slot-Verteilung über Wochentage/Stunden zur Lastverteilung
- E-Mail-Benachrichtigung nach Abschluss (SMTP)

### Einzelseiten-Audit
- Öffentlich zugänglich via `single-audits.html`
- Ergebnis-Link mit TTL (automatisches Ablaufen + Cleanup)

### Admin-Panel
- Passwortgeschützt (`ADMIN_PASSWORD` in `.env`)
- Übersicht aller Projekte und Audit-Status

### Rechtschreibprüfung
- Eigene Whitelist/Blacklist-Verwaltung via `spelling.html`
- Persisitierte Kandidaten in `spelling.db`

### Feedback
- Feedback-Formular im Frontend sendet E-Mail an `dms@hslu.ch`

---

## Deployment

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
- **Rechtschreibung:** LanguageTool (language_tool_python)
- **Frontend:** Vanilla HTML / CSS / JS
- **Hosting:** Render.com (Backend) + GitHub Pages (Frontend)
