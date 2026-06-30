"""Database adapter — SQLite default, PostgreSQL when DATABASE_URL is set."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

from .config import data_dir, get

DB_FILE = data_dir() / "leadgen.db"


def _database_url() -> str | None:
    url = get("DATABASE_URL")
    if not url:
        return None
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if "sslmode=" not in url and ("render.com" in url or "neon.tech" in url):
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


def backend() -> str:
    return "postgresql" if _database_url() else "sqlite"


@contextmanager
def connect() -> Generator[Any, None, None]:
    url = _database_url()
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
    con = sqlite3.connect(DB_FILE, timeout=20, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.row_factory = sqlite3.Row
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

    def executescript(self, sql: str):
        for stmt in sql.split(";"):
            if stmt.strip():
                self.execute(stmt)


_DDL = """
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    name TEXT, city TEXT, source TEXT,
    score INTEGER, tier TEXT, status TEXT,
    data_json TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score DESC);
CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT NOT NULL, event TEXT NOT NULL,
    data_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_lead ON events(lead_id, created_at DESC);
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
CREATE TABLE IF NOT EXISTS app_kv (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
"""


def init_schema() -> None:
    pg_ddl = (
        _DDL.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        .replace("CREATE INDEX IF NOT EXISTS", "CREATE INDEX IF NOT EXISTS")
    )
    with connect() as con:
        if backend() == "postgresql":
            for stmt in pg_ddl.split(";"):
                if stmt.strip():
                    try:
                        con.execute(stmt)
                    except Exception as exc:
                        if "already exists" not in str(exc).lower():
                            raise
            for stmt in (
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS user_id TEXT",
                "CREATE INDEX IF NOT EXISTS idx_leads_user ON leads(user_id)",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'member'",
            ):
                try:
                    con.execute(stmt)
                except Exception:
                    pass
        else:
            con.executescript(_DDL)
            _sqlite_migrate(con)


def _sqlite_migrate(con) -> None:
    cols = {row[1] for row in con.execute("PRAGMA table_info(leads)").fetchall()}
    if "user_id" not in cols:
        try:
            con.execute("ALTER TABLE leads ADD COLUMN user_id TEXT")
        except Exception:
            pass
    ucols = {row[1] for row in con.execute("PRAGMA table_info(users)").fetchall()}
    if "role" not in ucols:
        try:
            con.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'member'")
        except Exception:
            pass


def record_metric(name: str, value: float, tags: dict | None = None) -> None:
    init_schema()
    now = datetime.now(timezone.utc).isoformat()
    with connect() as con:
        con.execute(
            "INSERT INTO metrics(name,value,tags_json,created_at) VALUES(?,?,?,?)",
            (name, value, json.dumps(tags or {}), now),
        )
