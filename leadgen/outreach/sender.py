"""Outreach sender — SMTP, Resend API, or n8n webhook push."""
from __future__ import annotations

import json
from typing import Callable, Optional

import requests

from ..config import get
from .queue import can_send_today, list_queue, update_status

ProgressFn = Optional[Callable[[str], None]]


def _send_smtp(to_email: str, subject: str, body: str) -> None:
    import smtplib
    from email.mime.text import MIMEText

    host = get("SMTP_HOST")
    port = int(get("SMTP_PORT", "587") or "587")
    user = get("SMTP_USER")
    password = get("SMTP_PASSWORD")
    from_addr = get("SMTP_FROM", user)
    if not all([host, user, password, from_addr]):
        raise RuntimeError("SMTP not configured (SMTP_HOST, SMTP_USER, SMTP_PASSWORD)")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(from_addr, [to_email], msg.as_string())


def _send_resend(to_email: str, subject: str, body: str) -> None:
    key = get("RESEND_API_KEY")
    from_addr = get("RESEND_FROM", "onboarding@resend.dev")
    if not key:
        raise RuntimeError("RESEND_API_KEY not set")
    r = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"from": from_addr, "to": [to_email], "subject": subject, "text": body},
        timeout=30,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Resend failed: {r.status_code} {r.text[:200]}")


def _push_n8n(payload: dict) -> None:
    url = get("N8N_OUTREACH_WEBHOOK")
    if not url:
        return
    r = requests.post(url, json=payload, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"n8n webhook failed: {r.status_code}")


def send_one(queue_id: str) -> dict:
    pending = [q for q in list_queue(status="pending", limit=500) if q["id"] == queue_id]
    if not pending:
        return {"error": "not found or not pending"}
    item = pending[0]
    if not can_send_today():
        return {"error": "daily limit reached"}

    to_email = item.get("to_email")
    if item.get("channel") == "email" and not to_email:
        update_status(queue_id, "failed", error="no email")
        return {"error": "no email"}

    try:
        if item.get("channel") == "email":
            if get("RESEND_API_KEY"):
                _send_resend(to_email, item.get("subject", ""), item.get("body", ""))
            else:
                _send_smtp(to_email, item.get("subject", ""), item.get("body", ""))
        _push_n8n({
            "event": "outreach_sent",
            "queue_id": queue_id,
            "lead_id": item.get("lead_id"),
            "channel": item.get("channel"),
            "to": to_email,
            "subject": item.get("subject"),
            "body": item.get("body"),
        })
        update_status(queue_id, "sent")
        from .. import service
        service.update_favorite(item["lead_id"], status="contacted")
        return {"sent": True, "queue_id": queue_id}
    except Exception as exc:
        update_status(queue_id, "failed", error=str(exc))
        return {"error": str(exc)}


def process_queue(limit: int = 10, progress: ProgressFn = None) -> dict:
    """Send up to `limit` pending messages respecting daily cap."""
    sent, failed = 0, 0
    for item in list_queue(status="pending", limit=limit):
        if not can_send_today():
            break
        if progress:
            progress(f"outreach:send:{item['id']}")
        res = send_one(item["id"])
        if res.get("sent"):
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed}
