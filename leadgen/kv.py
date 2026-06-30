"""Key-value persistence — PostgreSQL app_kv when DATABASE_URL is set, else JSON files."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import get
from .db import backend, connect, init_schema
from . import tenant


def _scoped(key: str) -> str:
    return tenant.scoped_kv_key(key)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pg_get(key: str) -> Any | None:
    init_schema()
    with connect() as con:
        cur = con.execute("SELECT value_json FROM app_kv WHERE key=?", (key,))
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row[0])


def _pg_set(key: str, value: Any) -> None:
    init_schema()
    now = _now()
    payload = json.dumps(value, ensure_ascii=False)
    with connect() as con:
        if backend() == "postgresql":
            con.execute(
                """
                INSERT INTO app_kv(key,value_json,updated_at) VALUES(?,?,?)
                ON CONFLICT(key) DO UPDATE SET
                  value_json=EXCLUDED.value_json, updated_at=EXCLUDED.updated_at
                """,
                (key, payload, now),
            )
        else:
            con.execute(
                """
                INSERT INTO app_kv(key,value_json,updated_at) VALUES(?,?,?)
                ON CONFLICT(key) DO UPDATE SET
                  value_json=excluded.value_json, updated_at=excluded.updated_at
                """,
                (key, payload, now),
            )


def load_json(key: str, path: Path, default: Any) -> Any:
    """Load JSON from PG kv or fallback file."""
    key = _scoped(key)
    if get("DATABASE_URL"):
        val = _pg_get(key)
        if val is not None:
            return val
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return default


def save_json(key: str, path: Path, value: Any) -> None:
    """Persist JSON to PG kv and mirror to file when writable."""
    key = _scoped(key)
    if get("DATABASE_URL"):
        _pg_set(key, value)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def load_text(key: str, path: Path, default: str = "") -> str:
    key = _scoped(key)
    if get("DATABASE_URL"):
        val = _pg_get(key)
        if isinstance(val, str):
            return val
        if val is not None:
            return str(val)
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            pass
    return default


def save_text(key: str, path: Path, text: str) -> None:
    key = _scoped(key)
    if get("DATABASE_URL"):
        _pg_set(key, text)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError:
        pass


def append_jsonl(key: str, path: Path, row: dict) -> None:
    """Append one JSONL row; in PG mode store as list under key (read-modify-write)."""
    key = _scoped(key)
    if get("DATABASE_URL"):
        rows = _pg_get(key) or []
        if not isinstance(rows, list):
            rows = []
        rows.append(row)
        _pg_set(key, rows)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_jsonl(key: str, path: Path) -> list[dict]:
    key = _scoped(key)
    if get("DATABASE_URL"):
        val = _pg_get(key)
        if isinstance(val, list):
            return [r for r in val if isinstance(r, dict)]
    if not path.exists():
        return []
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    except OSError:
        pass
    return rows
