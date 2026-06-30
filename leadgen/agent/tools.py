"""Agent tools — wraps existing service/analyze/outreach functions for LLM function-calling."""
from __future__ import annotations

import json
from typing import Any, Callable, Optional

from .. import usage
from ..analyze.company import analyze
from ..analyze.qualify import qualify
from ..analyze.scoring import score_lead
from ..outreach.writer import write_message
from .. import service
from ..campaigns import (
    create_campaign,
    get_campaign,
    list_campaigns,
    run_campaign,
    pause_campaign,
)
from ..agent import memory
from ..signals.listeners import poll_signals, list_recent_signals

ProgressFn = Optional[Callable[[str], None]]

SEARCH_TOOLS = frozenset({
    "search_leads", "search_multi_city", "search_expanded_niche", "find_similar",
})

# Leaner schemas for the agent loop (same handlers, clearer descriptions).
AGENT_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_leads",
            "description": "Find leads in ONE city. Default: fast brave_places (~30s). Use source=all_sources only if user explicitly wants all sources or deep search. Set fast=false for full enrich.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Business niche or job role to search"},
                    "city": {"type": "string", "description": "City name e.g. Київ, Lviv"},
                    "country": {"type": "string", "default": "Ukraine"},
                    "limit": {"type": "integer", "default": 20, "description": "Max 40 for chat"},
                    "source": {"type": "string", "default": "brave_places",
                               "description": "brave_places (fast) | osm | gmaps | jobs | dou | all_sources (slow)"},
                    "fast": {"type": "boolean", "default": True, "description": "True=light enrich, ~1min. False=full pipeline"},
                    "require_email": {"type": "boolean", "default": False},
                    "min_tier": {"type": "string", "enum": ["hot", "warm", "cold", "any"], "default": "any"},
                },
                "required": ["category", "city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_multi_city",
            "description": "Search same category across 2-6 cities. Prefer fast=true unless user wants deep enrich.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "cities": {"type": "array", "items": {"type": "string"}},
                    "country": {"type": "string", "default": "Ukraine"},
                    "limit": {"type": "integer", "default": 25},
                    "source": {"type": "string", "default": "brave_places"},
                    "fast": {"type": "boolean", "default": True},
                },
                "required": ["category", "cities"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_expanded_niche",
            "description": "AI niche fan-out (~12 queries). SLOW (5-10 min). Only when user explicitly asks to expand niche or sweep a category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "city": {"type": "string", "default": ""},
                    "cities": {"type": "array", "items": {"type": "string"}},
                    "country": {"type": "string", "default": "Ukraine"},
                    "limit": {"type": "integer", "default": 30},
                    "source": {"type": "string", "default": "brave_places"},
                    "fast": {"type": "boolean", "default": True},
                },
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_leads",
            "description": "List leads from the database, optionally filtered by tier.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 20},
                    "tier": {"type": "string", "enum": ["hot", "warm", "cold", "any"], "default": "any"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_lead",
            "description": "Save/favorite a lead by id with optional tags and notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                },
                "required": ["lead_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_lead_status",
            "description": "Update pipeline status: new|contacted|replied|client|rejected",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {"type": "string"},
                    "status": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["lead_id", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_outreach",
            "description": "Generate personalized cold outreach message for a saved lead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {"type": "string"},
                    "channel": {"type": "string", "enum": ["email", "linkedin", "telegram"], "default": "email"},
                    "person_index": {"type": "integer", "default": 0},
                },
                "required": ["lead_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_lead",
            "description": "AI analysis of a company lead (summary, pains, automation angles).",
            "parameters": {
                "type": "object",
                "properties": {"lead_id": {"type": "string"}},
                "required": ["lead_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "qualify_lead",
            "description": "Score lead fit against ICP (0-100).",
            "parameters": {
                "type": "object",
                "properties": {"lead_id": {"type": "string"}},
                "required": ["lead_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stats",
            "description": "Dashboard stats: totals, funnel, sources, cities.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_usage",
            "description": "Monthly API budget usage (Apify, OpenAI, Brave).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_icp",
            "description": "Set Ideal Customer Profile text for qualification.",
            "parameters": {
                "type": "object",
                "properties": {"icp": {"type": "string"}},
                "required": ["icp"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_icp",
            "description": "Get current ICP text.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar",
            "description": "Find lookalike leads: same category/city as a reference lead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {"type": "string"},
                    "limit": {"type": "integer", "default": 15},
                },
                "required": ["lead_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_campaign",
            "description": "Create an autonomous lead-gen campaign with schedule (cron) and ICP.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {"type": "string"},
                    "cities": {"type": "array", "items": {"type": "string"}},
                    "source": {"type": "string", "default": "all_sources"},
                    "limit_per_run": {"type": "integer", "default": 30},
                    "cron": {"type": "string", "default": "0 7 * * *", "description": "Cron schedule, default 7am daily"},
                    "auto_outreach": {"type": "boolean", "default": False},
                },
                "required": ["name", "category", "cities"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_campaigns",
            "description": "List all campaigns and their status.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_campaign_now",
            "description": "Run a campaign immediately (don't wait for schedule).",
            "parameters": {
                "type": "object",
                "properties": {"campaign_id": {"type": "string"}},
                "required": ["campaign_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "queue_outreach",
            "description": "Queue outreach message for sending (email/linkedin).",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {"type": "string"},
                    "channel": {"type": "string", "default": "email"},
                    "person_index": {"type": "integer", "default": 0},
                },
                "required": ["lead_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "poll_signals",
            "description": "Check signal listeners (news/RSS) for buying triggers.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_insight",
            "description": "Store a learning for future campaigns (what worked / didn't).",
            "parameters": {
                "type": "object",
                "properties": {
                    "insight": {"type": "string"},
                    "category": {"type": "string", "default": "general"},
                },
                "required": ["insight"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "Recall past insights and campaign learnings.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "default": 10}},
            },
        },
    },
]

# Full schema list (tests / backwards compat).
TOOL_SCHEMAS = AGENT_TOOL_SCHEMAS


def _search_kwargs(args: dict[str, Any]) -> dict[str, Any]:
    fast = bool(args.get("fast", True))
    source = args.get("source") or ("brave_places" if fast else "all_sources")
    if source == "all_sources" and fast and not args.get("require_email"):
        source = "brave_places"
    limit = min(max(int(args.get("limit", 20)), 5), 40)
    return {
        "source": source,
        "limit": limit,
        "enrich": not fast,
        "discover_websites": not fast,
        "brave_people": not fast,
        "brave_news": False,
        "brave_intent": not fast,
    }


def _pack_search_result(full: list[dict], *, fast: bool) -> dict[str, Any]:
    return {
        "count": len(full),
        "fast": fast,
        "leads": [_lead_summary(l) for l in full[:12]],
    }


def _lead_summary(lead: dict) -> dict:
    c = lead.get("company", {}) or {}
    en = lead.get("enrichment", {}) or {}
    sc = lead.get("score", {}) or {}
    return {
        "_id": service._lead_id(lead),
        "name": c.get("name"),
        "city": c.get("city"),
        "website": c.get("website"),
        "source": c.get("source"),
        "score": sc.get("score"),
        "tier": sc.get("tier"),
        "emails": (en.get("emails") or [])[:2],
        "phones": (en.get("phones") or [])[:2],
        "decision_makers": [{"name": p.get("name"), "role": p.get("role")}
                            for p in (en.get("decision_makers") or [])[:2]],
        "hiring_for": (en.get("signals", {}) or {}).get("hiring_for", [])[:2],
    }


def _find_lead_by_id(lead_id: str) -> dict | None:
    for lead in service.load_leads(5000):
        if service._lead_id(lead) == lead_id:
            return lead
    for lead in service.list_favorites():
        if service._lead_id(lead) == lead_id:
            return lead
    return None


def _filter_leads(leads: list[dict], *, require_email: bool = False,
                  min_tier: str = "any") -> list[dict]:
    out = leads
    if require_email:
        out = [l for l in out if (l.get("enrichment", {}) or {}).get("emails")]
    if min_tier and min_tier != "any":
        tiers = {"hot": {"hot"}, "warm": {"hot", "warm"}, "cold": {"hot", "warm", "cold"}}
        allowed = tiers.get(min_tier, {min_tier})
        out = [l for l in out if (l.get("score", {}) or {}).get("tier") in allowed]
    return out


def _progress_msg(msg: str, progress: ProgressFn) -> None:
    if progress:
        progress(msg)


def execute_tool(name: str, args: dict[str, Any], *, lang: str = "uk",
                 progress: Optional[ProgressFn] = None) -> str:
    """Run a tool and return JSON string result for the LLM."""
    try:
        return json.dumps(_execute_tool_inner(name, args, lang=lang, progress=progress),
                          ensure_ascii=False, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _execute_tool_inner(name: str, args: dict[str, Any], *, lang: str,
                        progress: ProgressFn) -> Any:
    if name == "search_leads":
        sk = _search_kwargs(args)
        _progress_msg(f"discover:start:{args.get('category')}:{args.get('city')}", progress)
        result = service.find_leads(
            args["category"], args.get("city", ""),
            country=args.get("country", "Ukraine"),
            lang=lang,
            source=sk["source"],
            limit=sk["limit"],
            enrich=sk["enrich"],
            discover_websites=sk["discover_websites"],
            brave_people=sk["brave_people"],
            brave_news=sk["brave_news"],
            brave_intent=sk["brave_intent"],
            progress=lambda m: _progress_msg(m, progress),
        )
        full = [l.to_dict() for l in result.leads]
        full = _filter_leads(full, require_email=bool(args.get("require_email")),
                             min_tier=args.get("min_tier", "any"))
        _progress_msg(f"discover:done:{len(full)}", progress)
        return _pack_search_result(full, fast=bool(args.get("fast", True)))

    if name == "search_multi_city":
        sk = _search_kwargs(args)
        cities = args.get("cities") or service.UA_MAJOR_CITIES[:5]
        _progress_msg(f"discover:multi:{len(cities)}_cities", progress)
        result = service.find_leads_multi(
            args["category"], cities,
            country=args.get("country", "Ukraine"),
            limit=sk["limit"],
            lang=lang,
            source=sk["source"],
            enrich=sk["enrich"],
            discover_websites=sk["discover_websites"],
            brave_people=sk["brave_people"],
            brave_news=sk["brave_news"],
            brave_intent=sk["brave_intent"],
            progress=lambda m: _progress_msg(m, progress),
        )
        full = [l.to_dict() for l in result.leads]
        _progress_msg(f"discover:done:{len(full)}", progress)
        return _pack_search_result(full, fast=bool(args.get("fast", True)))

    if name == "search_expanded_niche":
        sk = _search_kwargs(args)
        _progress_msg("discover:expand_niche", progress)
        result = service.find_leads_expanded(
            args["category"],
            city=args.get("city", ""),
            country=args.get("country", "Ukraine"),
            limit=sk["limit"],
            lang=lang,
            source=sk["source"],
            enrich=sk["enrich"],
            discover_websites=sk["discover_websites"],
            brave_people=sk["brave_people"],
            brave_news=sk["brave_news"],
            brave_intent=sk["brave_intent"],
            cities=args.get("cities"),
            progress=lambda m: _progress_msg(m, progress),
        )
        full = [l.to_dict() for l in result.leads]
        _progress_msg(f"discover:done:{len(full)}", progress)
        return _pack_search_result(full, fast=bool(args.get("fast", True)))

    if name == "list_leads":
        leads = service.load_leads(int(args.get("limit", 20)))
        tier = args.get("tier", "any")
        if tier != "any":
            leads = [l for l in leads if (l.get("score", {}) or {}).get("tier") == tier]
        return {"count": len(leads), "leads": [_lead_summary(l) for l in leads]}

    if name == "save_lead":
        lead = _find_lead_by_id(args["lead_id"])
        if not lead:
            return {"error": "lead not found"}
        lid = service.save_favorite(lead)
        if args.get("tags") or args.get("notes"):
            service.update_favorite(lid, tags=args.get("tags"), notes=args.get("notes"))
        return {"saved": True, "id": lid}

    if name == "update_lead_status":
        ok = service.update_favorite(args["lead_id"], status=args["status"],
                                     notes=args.get("notes"))
        return {"updated": ok}

    if name == "write_outreach":
        lead = _find_lead_by_id(args["lead_id"])
        if not lead:
            return {"error": "lead not found"}
        msg = write_message(lead, int(args.get("person_index", 0)),
                            args.get("channel", "email"), lang)
        return msg

    if name == "analyze_lead":
        lead = _find_lead_by_id(args["lead_id"])
        if not lead:
            return {"error": "lead not found"}
        return analyze(lead, lang) or {"summary": "AI unavailable — set OPENAI_API_KEY"}

    if name == "qualify_lead":
        lead = _find_lead_by_id(args["lead_id"])
        if not lead:
            return {"error": "lead not found"}
        return qualify(lead, lang) or {"fit": None, "reason": "ICP not set or AI off"}

    if name == "get_stats":
        return service.stats()

    if name == "get_usage":
        return usage.summary()

    if name == "set_icp":
        service.set_icp(args["icp"])
        return {"saved": True}

    if name == "get_icp":
        return {"icp": service.get_icp()}

    if name == "find_similar":
        ref = _find_lead_by_id(args["lead_id"])
        if not ref:
            return {"error": "lead not found"}
        c = ref.get("company", {}) or {}
        cat = c.get("gmaps_category") or c.get("category") or "agency"
        city = c.get("city") or "Київ"
        _progress_msg(f"discover:lookalike:{cat}:{city}", progress)
        result = service.find_leads(cat, city, limit=int(args.get("limit", 15)),
                                   lang=lang, source="all_sources",
                                   progress=lambda m: _progress_msg(m, progress))
        full = [l.to_dict() for l in result.leads]
        return {"count": len(full), "leads": [_lead_summary(l) for l in full[:15]]}

    if name == "create_campaign":
        cid = create_campaign(
            name=args["name"],
            category=args["category"],
            cities=args.get("cities") or ["Київ"],
            source=args.get("source", "all_sources"),
            limit_per_run=int(args.get("limit_per_run", 50)),
            cron=args.get("cron", "0 7 * * *"),
            auto_outreach=bool(args.get("auto_outreach")),
            expand_niche=bool(args.get("expand_niche", True)),
            lang=lang,
        )
        return {"campaign_id": cid, "status": "active"}

    if name == "list_campaigns":
        return {"campaigns": list_campaigns()}

    if name == "run_campaign_now":
        return run_campaign(args["campaign_id"], progress=lambda m: _progress_msg(m, progress))

    if name == "queue_outreach":
        from ..outreach.queue import enqueue
        lead = _find_lead_by_id(args["lead_id"])
        if not lead:
            return {"error": "lead not found"}
        draft = write_message(lead, int(args.get("person_index", 0)),
                              args.get("channel", "email"), lang)
        qid = enqueue(lead_id=args["lead_id"], channel=args.get("channel", "email"),
                      subject=draft.get("subject", ""), body=draft.get("message", ""),
                      to_email=(lead.get("enrichment", {}) or {}).get("emails", [None])[0])
        return {"queued": True, "queue_id": qid, "preview": draft.get("message", "")[:200]}

    if name == "poll_signals":
        return poll_signals(progress=lambda m: _progress_msg(m, progress))

    if name == "remember_insight":
        memory.remember(args["insight"], category=args.get("category", "general"))
        return {"stored": True}

    if name == "recall_memory":
        return {"insights": memory.recall(int(args.get("limit", 10)))}

    return {"error": f"unknown tool: {name}"}
