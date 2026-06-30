"""API key + user session authentication."""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional

from fastapi import HTTPException, Request

from .config import get

_PUBLIC_PATHS = {
    "/login",
    "/register",
    "/api/categories",
    "/api/ai_status",
    "/api/health",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/status",
    "/favicon.ico",
}

_PUBLIC_PREFIXES = ("/static/",)

SESSION_COOKIE = "lg_session"
TOKEN_HEADER = "Authorization"


def _valid_key(provided: str | None) -> bool:
    expected = get("LEADGEN_API_KEY")
    if not expected:
        return True
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


def check_api_key(request: Request) -> None:
    if not get("LEADGEN_API_KEY"):
        return
    key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if not _valid_key(key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def auth_required() -> bool:
    mode = (get("REQUIRE_AUTH") or "auto").lower()
    if mode in ("0", "false", "no", "off"):
        return False
    if mode in ("1", "true", "yes", "on"):
        return True
    from .users import count_users

    return count_users() > 0


def is_public_path(path: str) -> bool:
    if path in _PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in _PUBLIC_PREFIXES)


def make_token(user_id: str, secret: str | None = None) -> str:
    secret = secret or get("JWT_SECRET") or "leadgen-dev-secret"
    ts = str(int(time.time()))
    sig = hashlib.sha256(f"{user_id}:{ts}:{secret}".encode()).hexdigest()[:32]
    return f"{user_id}.{ts}.{sig}"


def verify_token(token: str, secret: str | None = None) -> Optional[str]:
    secret = secret or get("JWT_SECRET") or "leadgen-dev-secret"
    try:
        user_id, ts, sig = token.split(".", 2)
        expected = hashlib.sha256(f"{user_id}:{ts}:{secret}".encode()).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected):
            return None
        if int(time.time()) - int(ts) > 86400 * 30:
            return None
        return user_id
    except (ValueError, TypeError):
        return None


def extract_token(request: Request) -> Optional[str]:
    auth = request.headers.get(TOKEN_HEADER) or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        return cookie
    return request.query_params.get("token")


def resolve_user(request: Request) -> Optional[str]:
    token = extract_token(request)
    if not token:
        return None
    return verify_token(token)


def require_user(request: Request) -> str:
    user_id = resolve_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


def check_request(request: Request) -> None:
    """Legacy hook — API key only."""
    check_api_key(request)
