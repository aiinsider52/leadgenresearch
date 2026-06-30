"""Outreach message queue — pending sends with daily limits."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import date, datetime, timezone

from ..config import data_dir, get

QUEUE_FILE = data_dir() / "outreach_queue.jsonl"
_LOCK = threading.Lock()
DAILY_LIMIT = int(get("OUTREACH_DAILY_LIMIT", "50") or "50")


def _today_sent() -> int:
    if not QUEUE_FILE.exists():
        return 0
    today = date.today().isoformat()
    count = 0
    for line in QUEUE_FILE.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("status") == "sent" and (row.get("sent_at") or "").startswith(today):
            count += 1
    return count


def enqueue(
    *,
    lead_id: str,
    channel: str,
    subject: str,
    body: str,
    to_email: str | None = None,
    sequence_id: str | None = None,
    step: int = 0,
) -> str:
    qid = str(uuid.uuid4())[:12]
    row = {
        "id": qid,
        "lead_id": lead_id,
        "channel": channel,
        "subject": subject,
        "body": body,
        "to_email": to_email,
        "sequence_id": sequence_id,
        "step": step,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sent_at": None,
        "error": None,
    }
    with _LOCK:
        with QUEUE_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return qid


def list_queue(status: str | None = None, limit: int = 100) -> list[dict]:
    if not QUEUE_FILE.exists():
        return []
    rows: list[dict] = []
    for line in QUEUE_FILE.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if status and row.get("status") != status:
            continue
        rows.append(row)
    return rows[-limit:][::-1]


def _rewrite_queue(rows: list[dict]) -> None:
    with _LOCK:
        with QUEUE_FILE.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")


def update_status(queue_id: str, status: str, *, error: str | None = None) -> bool:
    if not QUEUE_FILE.exists():
        return False
    rows = []
    found = False
    for line in QUEUE_FILE.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("id") == queue_id:
            row["status"] = status
            if status == "sent":
                row["sent_at"] = datetime.now(timezone.utc).isoformat()
            if error:
                row["error"] = error
            found = True
        rows.append(row)
    if found:
        _rewrite_queue(rows)
    return found


def pending_count() -> int:
    return len(list_queue(status="pending"))


def can_send_today() -> bool:
    return _today_sent() < DAILY_LIMIT
