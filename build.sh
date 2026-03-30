#!/bin/bash
# build.sh
# Schreibt Datum/Uhrzeit als Version in index.html und pusht auf GitHub.

VERSION=$(date +"%y%m%d-%H%M")
echo "→ Build-Version: $VERSION"

# Version in index.html ersetzen
sed -i '' "s/const VERSION='[^']*'/const VERSION='$VERSION'/" index.html

# Git push
git add index.html
git commit -m "build: $VERSION"
git push

echo "✓ Fertig – Version $VERSION deployed."
