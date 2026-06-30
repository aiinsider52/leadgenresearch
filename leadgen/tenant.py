"""Per-request tenant context for multi-user data scoping."""
from __future__ import annotations

from contextvars import ContextVar

_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)


def set_user(user_id: str | None) -> None:
    _user_id.set(user_id)


def get_user_id() -> str | None:
    return _user_id.get()


def scoped_kv_key(base: str) -> str:
    uid = get_user_id()
    if uid:
        return f"u:{uid}:{base}"
    return base
