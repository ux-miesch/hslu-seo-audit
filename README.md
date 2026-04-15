# SEO Audit Tool – HSLU

Internes SEO-Audit-Tool der HSLU. Analysiert Webseiten auf technische und inhaltliche SEO-Qualität. Das Frontend läuft auf GitHub Pages, das Backend auf Render.com.

---

## Projektstruktur

```
hslu-seo-audit/
├── index.html                  ← Frontend (GitHub Pages)
├── build.sh                    ← Version setzen + git push
├── deploy.sh                   ← Vollständiger Deploy-Prozess
├── start.sh                    ← Backend lokal starten
├── render.yaml                 ← Render-Konfiguration
├── .python-version             ← Python 3.11.9
├── frontend/
│   └── assets/
│       └── HSLU_Logo_DE_Weiss_rgb.svg
└── backend/
    ├── main.py                 ← FastAPI, parallele Checks
    ├── crawler.py              ← Seiten-Crawler
    ├── whitelist.py            ← Zentrale Ausnahmelisten
    ├── mode_checks.py          ← Seitentyp-Definitionen
    ├── requirements.txt
    ├── gtm_credentials.json    ← GTM API (git-ignored)
    └── checks/
        ├── meta_texts.py
        ├── headings.py
        ├── broken_links.py
        ├── alt_attributes.py
        ├── spelling.py
        ├── keywords.py
        ├── url_slug.py
        ├── mode_analysis.py
        └── sea.py
```

---

## Checks

Alle 8 Checks sind implementiert und aktiv:

| Check | Beschreibung |
|---|---|
| **Meta-Texte** | Title, Meta-Description, Canonical, Robots, Open Graph |
| **Überschriften** | H1–H6 Struktur, Hierarchie, Duplikate, Länge |
| **Defekte Links** | Erreichbarkeit aller Links, Weiterleitungen, Bot-Blocking |
| **Alt-Attribute** | Bilder, iFrames, PDFs, Videos |
| **Rechtschreibung** | Fehler via LanguageTool Public API (de-CH / en-US) |
| **Keywords & Semantik** | Keyword-Dichte, Platzierung, Wortschatz-Vielfalt |
| **URL / Slug** | HTTPS, Länge, Sonderzeichen, Tiefe, Parameter |
| **Seitentyp-Analyse** | Soft-Faktoren je nach Seitentyp (Conversion, Content, etc.) |
| **Kampagnen-Check (SEA)** | Google Tag Manager API – optional |

---

## Deployment

- **Frontend:** GitHub Pages → https://ux-miesch.github.io/hslu-seo-audit
- **Backend:** Render.com → https://hslu-seo-audit.onrender.com

```bash
bash deploy.sh
```

Setzt die Build-Version, pusht auf GitHub. Render.com deployed das Backend automatisch.

---

## Lokale Entwicklung

```bash
cd ~/Desktop/hslu-seo-audit
source venv/bin/activate
bash start.sh
```

Backend läuft auf: http://localhost:8000  
API-Dokumentation: http://localhost:8000/docs

---

## Technologie

- **Backend:** Python 3.11, FastAPI, httpx, BeautifulSoup4, asyncio (parallele Ausführung)
- **Frontend:** Vanilla HTML/CSS/JS
- **Rechtschreibung:** LanguageTool Public API
- **Hosting:** Render.com (Backend, Free Tier) + GitHub Pages (Frontend)
