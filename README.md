# SEO Audit Tool

Lokales SEO-Audit-Tool mit Python/FastAPI Backend und statischem Frontend.

## Projektstruktur

```
seo-audit/
├── backend/
│   ├── main.py              # FastAPI App & Endpunkte
│   ├── crawler.py           # HTTP-Abruf & HTML-Parsing
│   ├── checks/
│   │   ├── meta_texts.py    # Title, Description, Canonical, OG
│   │   └── headings.py      # H1–H6 Struktur & Hierarchie
│   └── requirements.txt
├── frontend/
│   └── index.html           # Minimale Testoberfläche
├── render.yaml              # Render Deployment Config
└── README.md
```

## Lokale Installation

### 1. Repository klonen
```bash
git clone https://github.com/DEIN-USERNAME/seo-audit.git
cd seo-audit
```

### 2. Python-Umgebung einrichten
```bash
python -m venv venv

# macOS/Linux:
source venv/bin/activate

# Windows:
venv\Scripts\activate
```

### 3. Abhängigkeiten installieren
```bash
pip install -r backend/requirements.txt
```

### 4. Backend starten
```bash
uvicorn backend.main:app --reload
```

API läuft auf: http://localhost:8000  
Automatische Docs: http://localhost:8000/docs

### 5. Frontend öffnen
Einfach `frontend/index.html` im Browser öffnen – kein Server nötig.

---

## API-Endpunkte

### `POST /audit`
Startet ein SEO-Audit für eine URL.

**Request:**
```json
{
  "url": "https://example.com",
  "keywords": ["seo", "audit"]
}
```

**Response:**
```json
{
  "url": "https://example.com",
  "status": "success",
  "checks": {
    "meta": { "score": 80, "issues": [], "warnings": [], "passed": [], "data": {} },
    "headings": { "score": 100, "issues": [], "warnings": [], "passed": [], "data": {} }
  }
}
```

---

## Geplante Checks

- [x] Meta-Texte (Title, Description, Canonical, Open Graph)
- [x] Überschriftenstruktur (H1–H6)
- [ ] Defekte Links
- [ ] Alt-Attribute (Bilder, PDFs, Videos)
- [ ] Rechtschreibung
- [ ] Keyword-Optimierung & semantische Vielfalt
- [ ] URL/Slug-Analyse

---

## Deployment auf Render

1. Repository auf GitHub pushen
2. Auf [render.com](https://render.com) anmelden
3. "New Web Service" → GitHub Repo verknüpfen
4. Render erkennt `render.yaml` automatisch
5. Deploy → URL notieren und in `frontend/index.html` eintragen (`const API = "..."`)

---

## Technologie

- **Backend:** Python, FastAPI, httpx, BeautifulSoup4
- **Frontend:** Vanilla HTML/CSS/JS (kein Framework nötig)
- **Hosting:** Render (Backend) + GitHub Pages (Frontend)
