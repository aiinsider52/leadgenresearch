"""Automation playbook templates and ROI estimates for sales workflows."""
from __future__ import annotations

from .config import data_dir
from . import kv

PLAYBOOK_FILE = data_dir() / "playbook.json"

DEFAULT_STEPS = [
    {
        "id": "discover",
        "title": "Discover",
        "description": "Run AI search across OSM, Brave, Maps, Instagram",
        "action": "search",
        "kpi": "leads_found",
    },
    {
        "id": "qualify",
        "title": "Qualify",
        "description": "Score leads vs ICP, filter hot/warm with email",
        "action": "qualify",
        "kpi": "qualified_leads",
    },
    {
        "id": "enrich",
        "title": "Enrich",
        "description": "Decision-makers, intent signals, contact quality",
        "action": "enrich",
        "kpi": "with_dm",
    },
    {
        "id": "outreach",
        "title": "Outreach",
        "description": "Draft personalized messages, queue email sequence",
        "action": "outreach",
        "kpi": "messages_queued",
    },
    {
        "id": "followup",
        "title": "Follow-up",
        "description": "Day 3 / Day 7 sequence + pipeline status updates",
        "action": "sequence",
        "kpi": "contacted",
    },
    {
        "id": "close",
        "title": "Convert",
        "description": "Track replies → client in CRM pipeline",
        "action": "pipeline",
        "kpi": "clients",
    },
]


def get_playbook() -> dict:
    data = kv.load_json("playbook", PLAYBOOK_FILE, {"steps": DEFAULT_STEPS, "version": 1})
    if not data.get("steps"):
        data["steps"] = DEFAULT_STEPS
    return data


def save_playbook(data: dict) -> None:
    kv.save_json("playbook", PLAYBOOK_FILE, data)


def roi_estimate(
    *,
    leads: int,
    conversion_pct: float = 2.0,
    deal_usd: float = 1500.0,
    hourly_cost: float = 35.0,
    hours_per_lead_manual: float = 0.75,
) -> dict:
    """Estimate pipeline value and time saved vs manual prospecting."""
    conv = max(0.0, min(conversion_pct, 100.0)) / 100.0
    clients = round(leads * conv, 2)
    pipeline_value = round(clients * deal_usd, 2)
    hours_saved = round(leads * hours_per_lead_manual * 0.65, 1)
    labor_saved = round(hours_saved * hourly_cost, 2)
    return {
        "leads": leads,
        "conversion_pct": conversion_pct,
        "deal_usd": deal_usd,
        "expected_clients": clients,
        "pipeline_value_usd": pipeline_value,
        "hours_saved": hours_saved,
        "labor_saved_usd": labor_saved,
        "roi_multiple": round(pipeline_value / max(labor_saved, 1), 2),
    }
