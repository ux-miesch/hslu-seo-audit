#!/bin/bash
# deploy.sh
# Führt alle Schritte nach einem Build aus:
# 1. build.sh (Version setzen + git push)
# 2. Virtuelle Umgebung neu starten
# 3. Backend-Server starten (uvicorn)
# 4. Browser mit index.html öffnen

PROJECT_DIR=~/Desktop/hslu-seo-audit

echo "──────────────────────────────────"
echo "  SEO Audit Tool – Deploy"
echo "──────────────────────────────────"

# In Projektordner wechseln
cd "$PROJECT_DIR" || { echo "✗ Projektordner nicht gefunden: $PROJECT_DIR"; exit 1; }

# 1. Build (Version setzen + git push)
echo ""
echo "→ Schritt 1: Build starten..."
bash build.sh || { echo "✗ build.sh fehlgeschlagen"; exit 1; }
echo "✓ Build abgeschlossen"

# 2. Virtuelle Umgebung neu starten
echo ""
echo "→ Schritt 2: Virtuelle Umgebung aktivieren..."
source venv/bin/activate || { echo "✗ venv nicht gefunden – bitte zuerst erstellen mit: python3 -m venv venv"; exit 1; }
echo "✓ Virtuelle Umgebung aktiv"

# 3. Abhängigkeiten aktualisieren (falls requirements.txt geändert)
echo ""
echo "→ Schritt 3: Abhängigkeiten prüfen..."
pip install -r requirements.txt -q
echo "✓ Abhängigkeiten aktuell"

# 4. Browser öffnen (vor dem Server, damit er nicht blockiert)
echo ""
echo "→ Schritt 4: Browser öffnen..."
open http://localhost:8000 2>/dev/null || true

# 5. Backend-Server starten (blockiert das Terminal – immer zuletzt)
echo ""
echo "→ Schritt 5: Backend-Server starten..."
echo "   (Server läuft – zum Stoppen: CTRL+C)"
echo "──────────────────────────────────"
bash start.sh
