#!/usr/bin/env bash
# Copy static assets to public/ so Vercel CDN serves them (no StaticFiles mount).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
rm -rf "$ROOT/public/static"
mkdir -p "$ROOT/public"
cp -R "$ROOT/leadgen/static/." "$ROOT/public/static/"
echo "Vercel build: copied static assets to public/static/"
