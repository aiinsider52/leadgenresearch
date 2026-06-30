"""Structured SQLite mirror for leads and events.

JSON files remain compatible exports; SQLite enables indexed queries and a
clean migration path to PostgreSQL.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .config import data_dir

DB_FILE = data_dir() / "leadgen.db"


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_FILE, timeout=20)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            id TEXT PRIMARY KEY,
            name TEXT,
            city TEXT,
            source TEXT,
            score INTEGER,
            tier TEXT,
            status TEXT,
            data_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score DESC);
        CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);
        CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id TEXT NOT NULL,
            event TEXT NOT NULL,
            data_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_lead ON events(lead_id, created_at DESC);
    """)
    return con


def upsert_lead(lead_id: str, lead: dict) -> None:
    company, score = lead.get("company", {}) or {}, lead.get("score", {}) or {}
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as con:
        con.execute("""
            INSERT INTO leads(id,name,city,source,score,tier,status,data_json,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name, city=excluded.city, source=excluded.source,
              score=excluded.score, tier=excluded.tier, status=excluded.status,
              data_json=excluded.data_json, updated_at=excluded.updated_at
        """, (
            lead_id, company.get("name"), company.get("city"), company.get("source"),
            score.get("score"), score.get("tier"), lead.get("status", "new"),
            json.dumps(lead, ensure_ascii=False), now,
        ))


def sync_leads(rows: list[tuple[str, dict]]) -> None:
    for lead_id, lead in rows:
        upsert_lead(lead_id, lead)


def record_event(lead_id: str, event: str, data: dict) -> None:
    with _connect() as con:
        con.execute(
            "INSERT INTO events(lead_id,event,data_json,created_at) VALUES(?,?,?,?)",
            (lead_id, event, json.dumps(data, ensure_ascii=False),
             datetime.now(timezone.utc).isoformat()),
        )


def status() -> dict:
    with _connect() as con:
        leads = con.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        events = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    return {"database": str(DB_FILE), "leads": leads, "events": events}
