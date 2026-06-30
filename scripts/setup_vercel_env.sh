#!/usr/bin/env bash
# Push secrets from data/secrets.env + DATABASE_URL to Vercel (production).
# Usage:
#   export DATABASE_URL='postgresql://...'   # from Render External URL
#   bash scripts/setup_vercel_env.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v vercel >/dev/null; then
  echo "Install Vercel CLI: npm i -g vercel"
  exit 1
fi

if [[ ! -f .vercel/project.json ]]; then
  echo "Run: vercel link"
  exit 1
fi

add_env() {
  local key="$1" val="$2"
  if [[ -z "$val" ]]; then return 0; fi
  printf '%s' "$val" | vercel env add "$key" production --force 2>/dev/null || \
    printf '%s' "$val" | vercel env add "$key" production
  echo "  + $key"
}

echo "Setting Vercel production env for $(jq -r .projectName .vercel/project.json)..."

if [[ -f data/secrets.env ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="$(echo "$line" | xargs)"
    [[ -z "$line" || "$line" != *"="* ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    add_env "$key" "$val"
  done < data/secrets.env
fi

if [[ -n "${DATABASE_URL:-}" ]]; then
  add_env "DATABASE_URL" "$DATABASE_URL"
else
  echo "  ! DATABASE_URL not set — create Render Postgres first (see docs/DEPLOY.md)"
fi

if [[ -n "${JWT_SECRET:-}" ]]; then
  add_env "JWT_SECRET" "$JWT_SECRET"
else
  JWT_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  add_env "JWT_SECRET" "$JWT_SECRET"
  echo "  (generated JWT_SECRET)"
fi

add_env "REQUIRE_AUTH" "${REQUIRE_AUTH:-auto}"

echo "Done. Redeploy: vercel deploy --prod"
