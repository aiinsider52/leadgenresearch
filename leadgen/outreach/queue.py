"""Outreach message queue — pending sends with daily limits (kv-backed for PG)."""
from __future__ import annotations

import threading
import uuid
from datetime import date, datetime, timezone

from ..config import data_dir, get
from .. import kv

QUEUE_FILE = data_dir() / "outreach_queue.jsonl"
KV_KEY = "outreach_queue"
_LOCK = threading.Lock()
DAILY_LIMIT = int(get("OUTREACH_DAILY_LIMIT", "50") or "50")


def _all_rows() -> list[dict]:
    if get("DATABASE_URL"):
        return kv.read_jsonl(KV_KEY, QUEUE_FILE)
    if QUEUE_FILE.exists():
        import json
        rows = []
        for line in QUEUE_FILE.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return rows
    return []


def _save_rows(rows: list[dict]) -> None:
    if get("DATABASE_URL"):
        kv.save_json(KV_KEY, QUEUE_FILE, rows)
    else:
        import json
        try:
            with _LOCK:
                with QUEUE_FILE.open("w", encoding="utf-8") as f:
                    for row in rows:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            kv.save_json(KV_KEY, QUEUE_FILE, rows)


def _today_sent() -> int:
    today = date.today().isoformat()
    return sum(
        1 for row in _all_rows()
        if row.get("status") == "sent" and (row.get("sent_at") or "").startswith(today)
    )


def _is_due(row: dict) -> bool:
    send_after = row.get("send_after")
    if not send_after:
        return True
    try:
        return datetime.fromisoformat(send_after.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    except (ValueError, TypeError):
        return True


def enqueue(
    *,
    lead_id: str,
    channel: str,
    subject: str,
    body: str,
    to_email: str | None = None,
    sequence_id: str | None = None,
    step: int = 0,
    send_after: str | None = None,
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
        "send_after": send_after,
        "error": None,
    }
    with _LOCK:
        if get("DATABASE_URL"):
            kv.append_jsonl(KV_KEY, QUEUE_FILE, row)
        else:
            import json
            try:
                with QUEUE_FILE.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            except OSError:
                kv.append_jsonl(KV_KEY, QUEUE_FILE, row)
    return qid


def list_queue(status: str | None = None, limit: int = 100) -> list[dict]:
    rows = _all_rows()
    if status:
        rows = [r for r in rows if r.get("status") == status]
    rows = [r for r in rows if r.get("status") != "pending" or _is_due(r)]
    return rows[-limit:][::-1]


def update_status(queue_id: str, status: str, *, error: str | None = None) -> bool:
    rows = _all_rows()
    found = False
    for row in rows:
        if row.get("id") == queue_id:
            row["status"] = status
            if status == "sent":
                row["sent_at"] = datetime.now(timezone.utc).isoformat()
            if error:
                row["error"] = error
            found = True
            break
    if found:
        _save_rows(rows)
    return found


def pending_count() -> int:
    return len([r for r in list_queue(status="pending", limit=5000) if _is_due(r)])


def can_send_today() -> bool:
    return _today_sent() < DAILY_LIMIT
