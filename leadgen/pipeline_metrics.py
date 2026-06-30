"""Persist aggregate search funnel metrics."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .config import data_dir

METRICS_FILE = data_dir() / "pipeline_metrics.jsonl"


def summarize(leads: list[dict], **context) -> dict:
    def has(key: str) -> int:
        return sum(bool((x.get("enrichment") or {}).get(key)) for x in leads)
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        **context,
        "unique": len(leads),
        "website": sum(bool((x.get("company") or {}).get("website")) for x in leads),
        "email": has("emails"),
        "phone": has("phones"),
        "decision_maker": has("decision_makers"),
        "verified_email": sum(bool(((x.get("enrichment") or {}).get("contact_quality") or {}).get("verified_email_count")) for x in leads),
        "intent": sum(bool(set(((x.get("enrichment") or {}).get("signals") or {})) &
                               {"hiring", "funding", "expansion", "tender", "automation_need"}) for x in leads),
        "hot": sum((x.get("score") or {}).get("tier") == "hot" for x in leads),
    }


def record(metrics: dict) -> None:
    with METRICS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(metrics, ensure_ascii=False) + "\n")


def recent(limit: int = 50) -> list[dict]:
    if not METRICS_FILE.exists():
        return []
    rows = []
    for line in METRICS_FILE.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows[-limit:]
