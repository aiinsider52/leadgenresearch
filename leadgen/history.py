"""Append-only lead events and snapshots for change detection."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .config import data_dir
from .storage import record_event

HISTORY_FILE = data_dir() / "lead_history.jsonl"


def record(lead_id: str, event: str, *, lead: dict | None = None, changes: dict | None = None) -> None:
    row = {
        "at": datetime.now(timezone.utc).isoformat(),
        "lead_id": lead_id,
        "event": event,
        "changes": changes or {},
    }
    if lead:
        company, enrichment = lead.get("company", {}) or {}, lead.get("enrichment", {}) or {}
        row["snapshot"] = {
            "name": company.get("name"),
            "website": company.get("website"),
            "score": (lead.get("score") or {}).get("score"),
            "emails": enrichment.get("emails") or [],
            "phones": enrichment.get("phones") or [],
            "decision_makers": enrichment.get("decision_makers") or [],
            "signals": enrichment.get("signals") or {},
        }
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    record_event(lead_id, event, row)


def recent(lead_id: str | None = None, limit: int = 100) -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    rows = []
    for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not lead_id or row.get("lead_id") == lead_id:
            rows.append(row)
    return rows[-limit:]
