# LeadGen — free-tier B2B lead engine + n8n automation matcher

Finds companies by **geo** (Ukraine-ready), enriches contacts (incl. C-level),
matches ready-to-sell **n8n AI automations**, and is driven from a **web
dashboard** or a **Telegram bot**. UI and pitches in **uk / ru / en**.
Pure Python monolith. Free sources work without paid APIs; optional Apify
sources add Instagram, LinkedIn Jobs, and a prebuilt Google Maps database.

## Pipeline

```
all_sources      Maps + OSM + Instagram + Jobs + DOU    ✅ parallel discovery
                 + Brave Places + Brave Intent
   ↓
identity.py      domain/phone/name cross-source merge   ✅ before enrichment
   ↓
enrich/website.py missing site → verified official site ✅ optional
   ↓
enrich/site.py   cached parallel site crawl             ✅ contacts + growth signals
enrich/people.py staff → decision-makers                ✅ role-based promotion
Brave Web/News   public executives + buying signals     ✅ cached + budgeted
pre_score        cheap rank → deep-enrich best leads    ✅ budget-aware
contact_quality  syntax + domain + MX + evidence        ✅ no email guessing
lead_history     snapshots + pipeline change events     ✅ append-only
storage.py       indexed SQLite mirror                  ✅ PostgreSQL-ready path
   ↓
catalog/match.py pains/signals → n8n automations        ✅ uk/ru/en, free scorer
   ↓
service.py       atomic upsert + pipeline metrics        ✅ one path for UI + bot
   ↓
app.py (dashboard)   ·   bot.py (Telegram)              ✅ both live
```

## Run

```bash
pip install -r requirements.txt

# 1) Web dashboard (uk/ru/en switcher, geo search, AI agent chat)
uvicorn leadgen.app:app --reload --port 8000      # → http://localhost:8000

# 2) Telegram bot
export BOT_TOKEN=123:abc...        # from @BotFather
python3 -m leadgen.bot
#   /find restaurant Львів   ·   /lang uk|ru|en   ·   /cats   ·   /help

# 3) CLI smoke tests (no key)
python3 -m leadgen.sources.osm law "Київ"
python3 -m leadgen.service "ресторан" "Львів"
python3 -m leadgen.enrich.site https://example-gmbh.de

# 4) Autopilot cron (schedules + campaigns + outreach + signals)
python3 run_scheduled.py
```

## AI Agent (Autopilot)

Open the **Агент** tab in the dashboard or call the API:

```bash
# Sync chat
curl -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"знайди 20 digital agency у Києві з email","lang":"uk"}'

# Streaming (SSE)
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"запусти кампанію по SaaS у Києві","lang":"uk"}'
```

The agent uses OpenAI function-calling with 20+ tools (search, enrich, score, outreach, campaigns, memory).

## New sources

| Source | Description |
|--------|-------------|
| `djinni` | Djinni.co IT jobs (free scrape) |
| `workua` | Work.ua vacancies |
| `robota` | Robota.ua vacancies |
| `linkedin_people` | LinkedIn people search (Apify) |
| `facebook` | Facebook pages search (Apify) — email, website, phone |
| `linkedin_company` | LinkedIn company employees (Apify) |
| `web_discovery` | Brave + LLM extraction (any company) |

## Campaigns & outreach

**UI:** Analytics → **Автокампанії** — create from current search, pause/resume, run now, run due.

**Cron:**
```bash
0 * * * * cd /path/to/leadgen && python3 run_scheduled.py >> data/cron.log 2>&1
```

```bash
# Create campaign
curl -X POST http://localhost:8000/api/campaigns \
  -H 'Content-Type: application/json' \
  -d '{"name":"SaaS Kyiv","category":"marketing agency","cities":["Київ","Львів"],"limit_per_run":80,"cron":"0 7 * * *","expand_niche":true}'

# Run only cron-due campaigns
curl -X POST http://localhost:8000/api/campaigns/run_due

# Process outreach queue
curl -X POST http://localhost:8000/api/outreach/process
```

Set `SMTP_*` or `RESEND_API_KEY` for email sending, `N8N_OUTREACH_WEBHOOK` for n8n push.

Optional: `USE_WATERFALL=true` enables cascade enrichment (crawl → Brave → Hunter → Apollo).

## Geo & language

- **Geo:** any city OSM knows. Category typed in any language is mapped to an
  OSM tag set (`i18n.resolve_category`): `ресторан/restaurant/кафе` → restaurant.
- **Categories:** restaurant, dental, clinic, beauty, fitness, law, real_estate,
  auto, hotel, retail, agency, construction, education.
- **Languages:** uk (default), ru, en — UI strings, automation pitches, and
  bot replies. Triggers include uk/ru/en synonyms so matching works on
  Ukrainian-language company data.

## Status

| Module | State |
|--------|-------|
| `sources/osm.py` geo discovery | ✅ working (retries across Overpass mirrors) |
| `all_sources` parallel discovery + early merge | ✅ working |
| official website discovery + 30-day crawl cache | ✅ working |
| pipeline metrics (`/api/pipeline_metrics`) | ✅ working |
| Brave Places + Web people + News signals | ✅ working with `BRAVE_SEARCH_API_KEY` |

## Brave Search

```bash
BRAVE_SEARCH_API_KEY=...
BRAVE_BUDGET_USD=5
BRAVE_MIN_INTERVAL_SECONDS=1.05
BRAVE_DEEP_LIMIT=25
DEEP_ENRICH_MULTIPLIER=2
```

Full Brave API response caching stays off by default. Enable
`BRAVE_ALLOW_CACHE=true` only when your Brave plan grants storage rights.
Normalized leads, detected signals, and source URLs still persist normally.
Email addresses are never generated or guessed. Contact quality only validates
addresses found in public sources. MX is checked through DNS-over-HTTPS; SMTP
recipient probing stays disabled because it is unreliable and can trigger abuse
controls.
| `enrich/site.py` | ✅ working (emails, grouped phones, socials, Telegram, C-level) |
| `catalog/` (9 automations) + `match.py` | ✅ working, multilingual |
| `service.py` orchestration | ✅ working, persists `data/leads.jsonl` |
| `app.py` FastAPI dashboard | ✅ working (`/`, `/api/find`, `/api/leads`, `/api/categories`) |
| `bot.py` Telegram bot | ✅ working (needs `BOT_TOKEN`) |
| `analyze/` Claude analysis + score 0-100 | ⏳ next (needs `ANTHROPIC_API_KEY`) |
| `outreach/` Claude per-person message | ⏳ next |

## Outreach & legal note

Email + LinkedIn are the safe, high-converting B2B channels. **Telegram is
opt-in only** — used solely where a public `t.me/@handle` is found on the
company's own site, never number-guessing. Cold Telegram DMs risk account bans
(Telegram ToS) and GDPR exposure; treat it as a bonus channel.
