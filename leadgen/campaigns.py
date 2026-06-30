"""Autonomous lead-gen campaigns — scheduled multi-source discovery runs."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from .config import data_dir
from . import service
from .agent import memory
from .cron_util import cron_is_due

CAMPAIGNS_FILE = data_dir() / "campaigns.json"
RUNS_FILE = data_dir() / "campaign_runs.jsonl"
_LOCK = threading.Lock()

CRON_PRESETS = {
    "daily_7": "0 7 * * *",
    "daily_8": "0 8 * * *",
    "weekdays_8": "0 8 * * 1-5",
    "every_6h": "0 */6 * * *",
    "every_12h": "0 */12 * * *",
}


def _read_campaigns() -> dict:
    if CAMPAIGNS_FILE.exists():
        try:
            return json.loads(CAMPAIGNS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"campaigns": {}}


def _write_campaigns(data: dict) -> None:
    CAMPAIGNS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def create_campaign(
    name: str,
    category: str,
    cities: list[str],
    *,
    source: str = "all_sources",
    limit_per_run: int = 50,
    cron: str = "0 7 * * *",
    auto_outreach: bool = False,
    expand_niche: bool = True,
    lang: str = "uk",
    icp: str = "",
    discover_websites: bool = True,
    brave_people: bool = True,
    brave_news: bool = True,
    brave_intent: bool = True,
) -> str:
    cid = str(uuid.uuid4())[:12]
    with _LOCK:
        data = _read_campaigns()
        data["campaigns"][cid] = {
            "id": cid,
            "name": name,
            "category": category,
            "cities": cities,
            "source": source,
            "limit_per_run": limit_per_run,
            "cron": cron,
            "auto_outreach": auto_outreach,
            "expand_niche": expand_niche,
            "lang": lang,
            "icp": icp or service.get_icp(),
            "discover_websites": discover_websites,
            "brave_people": brave_people,
            "brave_news": brave_news,
            "brave_intent": brave_intent,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_run": None,
            "totals": {"leads": 0, "hot": 0, "runs": 0},
        }
        _write_campaigns(data)
    return cid


def get_campaign(campaign_id: str) -> dict | None:
    return _read_campaigns().get("campaigns", {}).get(campaign_id)


def list_campaigns() -> list[dict]:
    return list(_read_campaigns().get("campaigns", {}).values())


def pause_campaign(campaign_id: str) -> bool:
    with _LOCK:
        data = _read_campaigns()
        c = data["campaigns"].get(campaign_id)
        if not c:
            return False
        c["status"] = "paused"
        _write_campaigns(data)
    return True


def resume_campaign(campaign_id: str) -> bool:
    with _LOCK:
        data = _read_campaigns()
        c = data["campaigns"].get(campaign_id)
        if not c:
            return False
        c["status"] = "active"
        _write_campaigns(data)
    return True


def delete_campaign(campaign_id: str) -> bool:
    with _LOCK:
        data = _read_campaigns()
        if campaign_id not in data.get("campaigns", {}):
            return False
        del data["campaigns"][campaign_id]
        _write_campaigns(data)
    return True


def _record_run(campaign_id: str, result: dict) -> None:
    row = {"campaign_id": campaign_id, "ts": datetime.now(timezone.utc).isoformat(), **result}
    with _LOCK:
        with RUNS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _discover_for_campaign(camp: dict, progress: Optional[Callable[[str], None]] = None) -> list:
    lang = camp.get("lang", "uk")
    cities = camp.get("cities") or ["Київ"]
    limit = camp.get("limit_per_run", 50)
    source = camp.get("source", "all_sources")
    common = dict(
        country=camp.get("country", "Ukraine"),
        limit=limit,
        lang=lang,
        source=source,
        discover_websites=camp.get("discover_websites", True),
        brave_people=camp.get("brave_people", True),
        brave_news=camp.get("brave_news", True),
        brave_intent=camp.get("brave_intent", True),
        progress=progress,
    )
    if camp.get("expand_niche", True):
        return service.find_leads_expanded(
            camp["category"],
            city=cities[0] if len(cities) == 1 else "",
            cities=cities if len(cities) > 1 else None,
            **common,
        ).leads
    if len(cities) == 1:
        return service.find_leads(camp["category"], cities[0], **common).leads
    return service.find_leads_multi(camp["category"], cities, **common).leads


def run_campaign(campaign_id: str, progress: Optional[Callable[[str], None]] = None) -> dict:
    camp = get_campaign(campaign_id)
    if not camp:
        return {"error": "campaign not found"}
    if camp.get("status") == "paused":
        return {"error": "campaign paused"}

    if progress:
        progress(f"campaign:start:{camp['name']}")

    leads = _discover_for_campaign(camp, progress=progress)
    lead_dicts = [l.to_dict() for l in leads]
    hot = sum(1 for l in lead_dicts if (l.get("score", {}) or {}).get("tier") == "hot")
    drafts = 0

    if camp.get("auto_outreach"):
        from .outreach.queue import enqueue
        from .outreach.writer import write_message
        for ld in lead_dicts[:5]:
            if (ld.get("score", {}) or {}).get("tier") not in ("hot", "warm"):
                continue
            emails = (ld.get("enrichment", {}) or {}).get("emails") or []
            if not emails:
                continue
            draft = write_message(ld, 0, "email", camp.get("lang", "uk"))
            lid = service._lead_id(ld)
            service.save_favorite(ld)
            enqueue(lead_id=lid, channel="email", subject=draft.get("subject", ""),
                    body=draft.get("message", ""), to_email=emails[0])
            drafts += 1

    result = {
        "leads_found": len(lead_dicts),
        "hot": hot,
        "drafts_queued": drafts,
        "cities": camp.get("cities") or [],
    }
    _record_run(campaign_id, result)

    with _LOCK:
        data = _read_campaigns()
        c = data["campaigns"].get(campaign_id)
        if c:
            c["last_run"] = datetime.now(timezone.utc).isoformat()
            t = c.setdefault("totals", {"leads": 0, "hot": 0, "runs": 0})
            t["leads"] += len(lead_dicts)
            t["hot"] += hot
            t["runs"] += 1
            _write_campaigns(data)

    memory.remember(
        f"Campaign '{camp['name']}': +{len(lead_dicts)} leads, {hot} hot",
        category=camp.get("category", "general"),
        source="campaign",
    )

    if progress:
        progress(f"campaign:done:+{len(lead_dicts)}_hot_{hot}")

    return {"campaign_id": campaign_id, **result}


def run_due_campaigns(progress: Optional[Callable[[str], None]] = None) -> list[dict]:
    """Run active campaigns whose cron schedule is due since last_run."""
    results = []
    for camp in list_campaigns():
        if camp.get("status") != "active":
            continue
        if not cron_is_due(camp.get("cron", "0 7 * * *"), camp.get("last_run")):
            if progress:
                progress(f"campaign:skip:{camp['name']}")
            continue
        results.append(run_campaign(camp["id"], progress=progress))
    return results


def recent_runs(limit: int = 20) -> list[dict]:
    if not RUNS_FILE.exists():
        return []
    rows = []
    for line in RUNS_FILE.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows[::-1]
