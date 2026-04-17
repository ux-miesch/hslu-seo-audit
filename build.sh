#!/bin/bash
# build.sh
# Schreibt Datum/Uhrzeit als Version in index.html und pusht auf GitHub.

VERSION=$(date +"%y%m%d-%H%M")
echo "→ Build-Version: $VERSION"

# Version in allen HTML-Dateien ersetzen
sed -i '' "s/const VERSION='[^']*'/const VERSION='$VERSION'/" index.html projects.html report.html spelling.html login.html

# Git push – lokaler Stand hat immer Vorrang
git add -A
git commit -m "build: $VERSION"
git push --force-with-lease

echo "✓ Fertig – Version $VERSION deployed."
