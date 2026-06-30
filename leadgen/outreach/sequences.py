"""Multi-step outreach sequences (day 0, 3, 7 follow-ups)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from ..config import data_dir
from .. import service
from .queue import enqueue
from .writer import write_message

SEQUENCES_FILE = data_dir() / "outreach_sequences.json"
DEFAULT_STEPS = [0, 3, 7]  # days after first touch


def _read() -> dict:
    if SEQUENCES_FILE.exists():
        try:
            return json.loads(SEQUENCES_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"sequences": {}}


def _write(data: dict) -> None:
    SEQUENCES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def start_sequence(lead_id: str, *, channel: str = "email", lang: str = "uk",
                   steps_days: list[int] | None = None) -> str:
    lead = None
    for l in service.load_leads(5000):
        if service._lead_id(l) == lead_id:
            lead = l
            break
    if not lead:
        for l in service.list_favorites():
            if service._lead_id(l) == lead_id:
                lead = l
                break
    if not lead:
        raise ValueError("lead not found")

    sid = str(uuid.uuid4())[:12]
    steps = steps_days or DEFAULT_STEPS
    drafts = []
    for i, day in enumerate(steps):
        draft = write_message(lead, 0, channel, lang)
        emails = (lead.get("enrichment", {}) or {}).get("emails") or []
        send_after = (datetime.now(timezone.utc) + timedelta(days=day)).isoformat() if day > 0 else None
        qid = enqueue(
            lead_id=lead_id,
            channel=channel,
            subject=draft.get("subject", f"Follow-up {i + 1}"),
            body=draft.get("message", ""),
            to_email=emails[0] if emails else None,
            sequence_id=sid,
            step=i,
            send_after=send_after,
        )
        drafts.append({
            "queue_id": qid,
            "step": i,
            "send_after": send_after,
        })

    data = _read()
    data["sequences"][sid] = {
        "id": sid,
        "lead_id": lead_id,
        "channel": channel,
        "lang": lang,
        "steps": drafts,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write(data)
    return sid


def list_sequences() -> list[dict]:
    return list(_read().get("sequences", {}).values())
