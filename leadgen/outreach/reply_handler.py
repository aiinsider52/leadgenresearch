"""Reply handling — classify inbound replies and update pipeline."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from .. import llm
from ..config import data_dir
from .. import service
from .writer import write_message

REPLIES_FILE = data_dir() / "outreach_replies.jsonl"

_INTEREST = re.compile(
    r"\b(цікав|інтерес|давайте|зустр|call|demo|так|yes|interested|готов|обговор)\b", re.I
)
_REJECT = re.compile(
    r"\b(ні|no|not interested|відмов|unsubscribe|стоп|stop|спам|spam)\b", re.I
)
_LATER = re.compile(r"\b(пізніш|later|наступн|next month|потім|remind)\b", re.I)


def classify_reply(text: str) -> dict:
    """Rule-based + optional LLM classification."""
    text = (text or "").strip()
    if not text:
        return {"class": "unknown", "confidence": 0}

    if _REJECT.search(text):
        return {"class": "rejected", "confidence": 0.85}
    if _INTEREST.search(text):
        return {"class": "interested", "confidence": 0.8}
    if _LATER.search(text):
        return {"class": "later", "confidence": 0.75}

    if llm.available():
        raw = llm.complete(
            system="Classify B2B email reply. Reply with ONE word: interested|rejected|later|neutral",
            user=text[:1500],
            max_tokens=10,
            temperature=0,
        )
        if raw:
            w = raw.strip().lower().split()[0]
            if w in ("interested", "rejected", "later", "neutral"):
                return {"class": w, "confidence": 0.7, "ai": True}

    return {"class": "neutral", "confidence": 0.5}


def handle_reply(lead_id: str, reply_text: str, *, lang: str = "uk") -> dict:
    """Classify reply, move pipeline, optionally draft follow-up."""
    result = classify_reply(reply_text)
    status_map = {
        "interested": "replied",
        "rejected": "rejected",
        "later": "contacted",
        "neutral": "replied",
    }
    new_status = status_map.get(result["class"], "replied")
    service.update_favorite(lead_id, status=new_status, notes=f"Reply: {reply_text[:200]}")

    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "lead_id": lead_id,
        "reply": reply_text[:2000],
        "classification": result,
        "new_status": new_status,
    }
    with REPLIES_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    follow_up = None
    if result["class"] == "interested":
        lead = None
        for l in service.list_favorites():
            if service._lead_id(l) == lead_id:
                lead = l
                break
        if lead:
            follow_up = write_message(lead, 0, "email", lang)

    return {"classification": result, "status": new_status, "follow_up_draft": follow_up}


def recent_replies(limit: int = 50) -> list[dict]:
    if not REPLIES_FILE.exists():
        return []
    rows = []
    for line in REPLIES_FILE.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows[::-1]
