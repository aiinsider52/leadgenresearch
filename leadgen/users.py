"""User accounts — email/password stored in Postgres or SQLite."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

import bcrypt

from .db import connect, init_schema

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def count_users() -> int:
    init_schema()
    with connect() as con:
        cur = con.execute("SELECT COUNT(*) FROM users")
        return int(cur.fetchone()[0])


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    init_schema()
    with connect() as con:
        cur = con.execute(
            "SELECT id, email, name, role, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "email": row[1], "name": row[2], "role": row[3] or "member", "created_at": row[4]}


def get_user_by_email(email: str) -> dict[str, Any] | None:
    init_schema()
    norm = email.strip().lower()
    with connect() as con:
        cur = con.execute(
            "SELECT id, email, name, password_hash, created_at FROM users WHERE email = ?",
            (norm,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "email": row[1],
        "name": row[2],
        "password_hash": row[3],
        "created_at": row[4],
    }


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def validate_email(email: str) -> str | None:
    e = email.strip().lower()
    if not e or not _EMAIL_RE.match(e):
        return "Invalid email address"
    return None


def validate_password(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters"
    return None


def create_user(email: str, password: str, name: str = "") -> dict[str, Any]:
    err = validate_email(email) or validate_password(password)
    if err:
        raise ValueError(err)
    if get_user_by_email(email):
        raise ValueError("Email already registered")
    uid = str(uuid.uuid4())
    norm = email.strip().lower()
    display = (name or norm.split("@")[0]).strip()[:120]
    now = _now()
    role = "admin" if count_users() == 0 else "member"
    init_schema()
    with connect() as con:
        con.execute(
            "INSERT INTO users(id,email,name,password_hash,role,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (uid, norm, display, _hash_password(password), role, now, now),
        )
    return get_user_by_id(uid) or {
        "id": uid, "email": norm, "name": display, "role": role, "created_at": now,
    }


def authenticate(email: str, password: str) -> dict[str, Any] | None:
    user = get_user_by_email(email)
    if not user or not _verify_password(password, user["password_hash"]):
        return None
    return {k: v for k, v in user.items() if k != "password_hash"}
