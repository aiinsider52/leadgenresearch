#!/usr/bin/env bash
# Copy static assets to public/ for Vercel CDN (FastAPI also serves leadgen/static/).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/leadgen/static"
DEST="$ROOT/public/static"
rm -rf "$DEST"
mkdir -p "$ROOT/public"
cp -R "$SRC/." "$DEST/"
if command -v npm >/dev/null 2>&1; then
  (cd "$ROOT" && npm run build 2>/dev/null) && mkdir -p "$DEST/dist" && cp -f "$ROOT/dist/app.js" "$ROOT/dist/app.css" "$DEST/dist/" 2>/dev/null || true
fi
COUNT="$(find "$DEST" -type f | wc -l | tr -d ' ')"
echo "Vercel build: copied $COUNT files from leadgen/static -> public/static/"
test "$COUNT" -gt 0
