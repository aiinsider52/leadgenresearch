"""Database adapter — SQLite default, PostgreSQL when DATABASE_URL is set."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

from .config import data_dir, get

DB_FILE = data_dir() / "leadgen.db"


def backend() -> str:
    return "postgresql" if get("DATABASE_URL") else "sqlite"


@contextmanager
def connect() -> Generator[Any, None, None]:
    url = get("DATABASE_URL")
    if url:
        try:
            import psycopg2  # type: ignore
            con = psycopg2.connect(url)
            try:
                yield _PgWrapper(con)
            finally:
                con.close()
            return
        except ImportError:
            pass
    con = sqlite3.connect(DB_FILE, timeout=20)
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
    finally:
        con.close()


class _PgWrapper:
    """Minimal psycopg2 → sqlite-like API."""

    def __init__(self, con):
        self._con = con

    def execute(self, sql: str, params=()):
        sql = sql.replace("?", "%s")
        cur = self._con.cursor()
        cur.execute(sql, params)
        self._con.commit()
        return cur

    def executemany(self, sql: str, params):
        sql = sql.replace("?", "%s")
        cur = self._con.cursor()
        cur.executemany(sql, params)
        self._con.commit()
        return cur


def init_schema() -> None:
    sqlite_ddl = """
        CREATE TABLE IF NOT EXISTS leads (
            id TEXT PRIMARY KEY,
            name TEXT, city TEXT, source TEXT,
            score INTEGER, tier TEXT, status TEXT,
            data_json TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id TEXT NOT NULL, event TEXT NOT NULL,
            data_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL, payload_json TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL,
            started_at TEXT, finished_at TEXT, result_json TEXT, error TEXT
        );
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, value REAL, tags_json TEXT,
            created_at TEXT NOT NULL
        );
    """
    pg_ddl = sqlite_ddl.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    with connect() as con:
        if backend() == "postgresql":
            for stmt in pg_ddl.split(";"):
                if stmt.strip():
                    con.execute(stmt)
        else:
            con.executescript(sqlite_ddl)


def record_metric(name: str, value: float, tags: dict | None = None) -> None:
    init_schema()
    now = datetime.now(timezone.utc).isoformat()
    with connect() as con:
        con.execute(
            "INSERT INTO metrics(name,value,tags_json,created_at) VALUES(?,?,?,?)",
            (name, value, json.dumps(tags or {}), now),
        )
