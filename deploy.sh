#!/bin/bash
# deploy.sh
# Setzt Version, committed und pusht auf GitHub.
# GitHub Pages (Frontend) und Render.com (Backend) deployen automatisch.

PROJECT_DIR=~/Desktop/hslu-seo-audit

echo "──────────────────────────────────"
echo "  SEO Audit Tool – Deploy"
echo "──────────────────────────────────"

cd "$PROJECT_DIR" || { echo "✗ Projektordner nicht gefunden: $PROJECT_DIR"; exit 1; }

# 1. Build (Version setzen + git push)
echo ""
echo "→ Schritt 1: Build starten..."
bash build.sh || { echo "✗ build.sh fehlgeschlagen"; exit 1; }
echo "✓ Build abgeschlossen"

echo ""
echo "✓ Fertig – GitHub Pages und Render.com deployen automatisch."
echo "  Frontend: https://ux-miesch.github.io/hslu-seo-audit"
echo "  Backend:  https://hslu-seo-audit.onrender.com"
echo "──────────────────────────────────"
