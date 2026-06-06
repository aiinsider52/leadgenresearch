# LeadGen — free-tier B2B lead engine + n8n automation matcher

Finds companies by **geo** (Ukraine-ready), enriches contacts (incl. C-level),
matches ready-to-sell **n8n AI automations**, and is driven from a **web
dashboard** or a **Telegram bot**. UI and pitches in **uk / ru / en**.
Pure Python monolith. Core runs with **no paid APIs** (no Apollo/Apify).

## Pipeline

```
sources/osm.py   geo discovery (OSM Overpass, free)     ✅ company + website/phone/addr
   ↓
enrich/site.py   site → emails, phones, socials,        ✅ incl. Impressum C-level
                 Telegram handles
   ↓
catalog/match.py pains/signals → n8n automations        ✅ uk/ru/en, free scorer
   ↓
service.py       orchestration + data/leads.jsonl       ✅ one path for UI + bot
   ↓
app.py (dashboard)   ·   bot.py (Telegram)              ✅ both live
```

## Run

```bash
pip install -r requirements.txt

# 1) Web dashboard (uk/ru/en switcher, geo search, results)
uvicorn leadgen.app:app --reload --port 8000      # → http://localhost:8000

# 2) Telegram bot
export BOT_TOKEN=123:abc...        # from @BotFather
python3 -m leadgen.bot
#   /find restaurant Львів   ·   /lang uk|ru|en   ·   /cats   ·   /help

# 3) CLI smoke tests (no key)
python3 -m leadgen.sources.osm law "Київ"
python3 -m leadgen.service "ресторан" "Львів"
python3 -m leadgen.enrich.site https://example-gmbh.de
```

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
