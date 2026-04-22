#!/bin/bash
# build.sh
# Schreibt Datum/Uhrzeit als Version in index.html und pusht auf GitHub.

VERSION=$(date +"%y%m%d-%H%M")
echo "→ Build-Version: $VERSION"

PROD_API="https://hslu-seo-audit.onrender.com"

# Version + API-URL in allen HTML-Dateien ersetzen
sed -i '' "s/const VERSION='[^']*'/const VERSION='$VERSION'/" index.html projects.html report.html spelling.html single-audits.html
sed -i '' "s|http://localhost:8000|$PROD_API|g" index.html projects.html report.html spelling.html admin.html single-audits.html

# Git push – lokaler Stand hat immer Vorrang
git add -A
git commit -m "build: $VERSION"
git push --force-with-lease

# API-URL lokal wieder auf localhost zurücksetzen
sed -i '' "s|$PROD_API|http://localhost:8000|g" index.html projects.html report.html spelling.html admin.html single-audits.html

echo "✓ Fertig – Version $VERSION deployed."
