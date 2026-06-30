# Production deploy: Vercel + Render Postgres

LeadGen stores leads, saved pipeline, campaigns, and schedules in **PostgreSQL**
when `DATABASE_URL` is set. Without it, data lives in `/tmp` on Vercel and is
lost on cold starts.

## 1. Create Postgres on Render

### Option A — Blueprint (recommended)

1. Open [Render Dashboard](https://dashboard.render.com/) → **New +** → **Blueprint**
2. Connect repo `aiinsider52/leadgenresearch` (or your fork)
3. Render reads `render.yaml` and creates:
   - **leadgen-db** (free Postgres, `frankfurt`)
   - **leadgenresearch** web service with `DATABASE_URL` wired automatically

### Option B — Manual

1. **New +** → **PostgreSQL** → name `leadgen-db`, plan **Free**, region **Frankfurt**
2. After create: **Connect** → copy **External Database URL**

## 2. Vercel environment variables

Project: `leadgenresearch.vercel.app` (or `vladyslavais-projects/leadgen`)

| Variable | Required | Notes |
|----------|----------|-------|
| `DATABASE_URL` | **Yes** | External URL from Render, `?sslmode=require` appended automatically |
| `OPENAI_API_KEY` | **Yes** | Agent + analysis |
| `APIFY_TOKEN` | Recommended | Instagram, LinkedIn, GMaps |
| `BRAVE_SEARCH_API_KEY` | Recommended | Brave enrich + web discovery |
| `LEADGEN_API_KEY` | Optional | If set, all `/api/*` require `X-API-Key` header |

### CLI (linked project in `leadgen/`)

```bash
cd leadgen
vercel link          # team + project
vercel env add DATABASE_URL production
vercel env add OPENAI_API_KEY production
vercel env add APIFY_TOKEN production
vercel env add BRAVE_SEARCH_API_KEY production
vercel deploy --prod
```

Paste values when prompted. Or use Render **Internal** URL only if the app runs on Render, not Vercel.

## 3. Verify

```bash
curl https://leadgenresearch.vercel.app/api/health
# {"ok":true,"vercel":true}

curl https://leadgenresearch.vercel.app/api/db/status
# {"backend":"postgresql"}

curl https://leadgenresearch.vercel.app/api/storage/status
# {"backend":"postgresql","leads":N,...}
```

Run a search, refresh — lead count should **persist** across page reloads and cold starts.

## 4. What is stored in Postgres

| Data | Table / key |
|------|-------------|
| All leads | `leads` |
| Saved / pipeline | `app_kv` key `saved` |
| Campaigns | `app_kv` key `campaigns` |
| Schedules | `app_kv` key `schedules` |
| ICP text | `app_kv` key `icp` |
| Campaign runs | `app_kv` key `campaign_runs` |
| Jobs (async search) | `jobs` |
| Events | `events` |

## 5. Render CLI (optional)

```bash
render login
render services list
render postgres list
```

MCP Render tools in Cursor can create DB when authenticated.

## 6. Free tier limits

- **Render Postgres free**: 1 GB, expires after 90 days of inactivity (check Render docs)
- **Vercel serverless**: 60s max duration (`vercel.json`), ephemeral `/tmp` without `DATABASE_URL`

For always-on + disk-only (no Postgres), use Render web + paid disk per `render.yaml` comments.
