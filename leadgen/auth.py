"""Optional API authentication — API key or JWT."""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional

from fastapi import HTTPException, Request

from .config import get

_PUBLIC_PATHS = {"/", "/api/categories", "/api/ai_status", "/api/health"}


def _valid_key(provided: str | None) -> bool:
    expected = get("LEADGEN_API_KEY")
    if not expected:
        return True  # auth disabled
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


def check_request(request: Request) -> None:
    if request.url.path in _PUBLIC_PATHS:
        return
    if not get("LEADGEN_API_KEY"):
        return
    key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if not _valid_key(key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def make_token(user_id: str, secret: str | None = None) -> str:
    secret = secret or get("JWT_SECRET", "leadgen-dev-secret")
    ts = str(int(time.time()))
    sig = hashlib.sha256(f"{user_id}:{ts}:{secret}".encode()).hexdigest()[:32]
    return f"{user_id}.{ts}.{sig}"


def verify_token(token: str, secret: str | None = None) -> Optional[str]:
    secret = secret or get("JWT_SECRET", "leadgen-dev-secret")
    try:
        user_id, ts, sig = token.split(".", 2)
        expected = hashlib.sha256(f"{user_id}:{ts}:{secret}".encode()).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected):
            return None
        if int(time.time()) - int(ts) > 86400 * 7:
            return None
        return user_id
    except (ValueError, TypeError):
        return None
