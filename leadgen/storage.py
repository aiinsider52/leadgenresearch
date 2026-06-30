"""Structured DB mirror for leads and events.

When DATABASE_URL is set, PostgreSQL is the source of truth.
JSON files remain a local export path when the filesystem is writable.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .config import data_dir, get
from .db import backend, connect, init_schema
from . import tenant

DB_FILE = data_dir() / "leadgen.db"


def _connect():
    init_schema()
    return connect()


def _lead_where(user_id: str | None) -> tuple[str, tuple]:
    if user_id:
        return "WHERE user_id IS NULL OR user_id = ?", (user_id,)
    return "", ()


def upsert_lead(lead_id: str, lead: dict, *, user_id: str | None = None) -> None:
    company, score = lead.get("company", {}) or {}, lead.get("score", {}) or {}
    now = datetime.now(timezone.utc).isoformat()
    uid = user_id if user_id is not None else tenant.get_user_id()
    with _connect() as con:
        if uid:
            con.execute(
                """
                INSERT INTO leads(id,name,city,source,score,tier,status,data_json,updated_at,user_id)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                  name=excluded.name, city=excluded.city, source=excluded.source,
                  score=excluded.score, tier=excluded.tier, status=excluded.status,
                  data_json=excluded.data_json, updated_at=excluded.updated_at,
                  user_id=COALESCE(leads.user_id, excluded.user_id)
                """,
                (
                    lead_id,
                    company.get("name"),
                    company.get("city"),
                    company.get("source"),
                    score.get("score"),
                    score.get("tier"),
                    lead.get("status", "new"),
                    json.dumps(lead, ensure_ascii=False),
                    now,
                    uid,
                ),
            )
        else:
            con.execute(
                """
                INSERT INTO leads(id,name,city,source,score,tier,status,data_json,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                  name=excluded.name, city=excluded.city, source=excluded.source,
                  score=excluded.score, tier=excluded.tier, status=excluded.status,
                  data_json=excluded.data_json, updated_at=excluded.updated_at
                """,
                (
                    lead_id,
                    company.get("name"),
                    company.get("city"),
                    company.get("source"),
                    score.get("score"),
                    score.get("tier"),
                    lead.get("status", "new"),
                    json.dumps(lead, ensure_ascii=False),
                    now,
                ),
            )


def sync_leads(rows: list[tuple[str, dict]]) -> None:
    for lead_id, lead in rows:
        upsert_lead(lead_id, lead)


def record_event(lead_id: str, event: str, data: dict) -> None:
    with _connect() as con:
        con.execute(
            "INSERT INTO events(lead_id,event,data_json,created_at) VALUES(?,?,?,?)",
            (
                lead_id,
                event,
                json.dumps(data, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def load_all_leads(user_id: str | None = None) -> list[dict]:
    uid = user_id if user_id is not None else tenant.get_user_id()
    where, params = _lead_where(uid)
    with _connect() as con:
        cur = con.execute(
            f"SELECT data_json FROM leads {where} ORDER BY updated_at ASC",
            params,
        )
        rows = cur.fetchall()
    out = []
    for row in rows:
        try:
            out.append(json.loads(row[0]))
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
    return out


def count_leads(user_id: str | None = None) -> int:
    uid = user_id if user_id is not None else tenant.get_user_id()
    where, params = _lead_where(uid)
    with _connect() as con:
        cur = con.execute(f"SELECT COUNT(*) FROM leads {where}", params)
        return int(cur.fetchone()[0])


def lead_aggregates(user_id: str | None = None) -> dict[str, Any]:
    """DB-level counters for analytics (no row limit)."""
    leads = load_all_leads(user_id)
    by_tier = Counter((l.get("score", {}) or {}).get("tier", "cold") for l in leads)
    by_source = Counter((l.get("company", {}) or {}).get("source", "?") for l in leads)
    by_city = Counter((l.get("company", {}) or {}).get("city", "?") for l in leads)
    with_email = sum(1 for l in leads if (l.get("enrichment", {}) or {}).get("emails"))
    with_dm = sum(1 for l in leads if (l.get("enrichment", {}) or {}).get("decision_makers"))
    with_website = sum(1 for l in leads if (l.get("company", {}) or {}).get("website"))
    verified_email = sum(
        bool(((l.get("enrichment", {}) or {}).get("contact_quality") or {}).get("verified_email_count"))
        for l in leads
    )
    with_intent = sum(
        bool(
            set(((l.get("enrichment", {}) or {}).get("signals") or {}))
            & {"hiring", "funding", "expansion", "tender", "automation_need"}
        )
        for l in leads
    )
    return {
        "total_leads": count_leads(user_id) if get("DATABASE_URL") else len(leads),
        "by_tier": dict(by_tier),
        "by_source": dict(by_source),
        "by_city": dict(by_city.most_common(8)),
        "with_email": with_email,
        "with_dm": with_dm,
        "with_website": with_website,
        "verified_email": verified_email,
        "with_intent": with_intent,
        "_sample": leads,
    }


def status() -> dict:
    with _connect() as con:
        cur = con.execute("SELECT COUNT(*) FROM leads")
        leads = cur.fetchone()[0]
        cur = con.execute("SELECT COUNT(*) FROM events")
        events = cur.fetchone()[0]
    return {
        "database": "postgresql" if get("DATABASE_URL") else str(DB_FILE),
        "backend": backend(),
        "leads": leads,
        "events": events,
    }
