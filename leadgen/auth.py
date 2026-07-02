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
    "/reset-password",
    "/auth/callback",
    "/api/categories",
    "/api/ai_status",
    "/api/health",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/reset-password",
    "/api/auth/session",
    "/api/auth/email-hint",
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


def auth_landing_path() -> str:
    """Where unauthenticated visitors should land."""
    from .users import count_users

    try:
        if count_users() == 0:
            return "/register"
    except Exception:
        pass
    return "/login"


def is_dashboard_path(path: str) -> bool:
    return path in ("/", "/index.html")


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


def resolve_user(request: Request) -> Optional[str]:
    """Accept session from Bearer header, cookie, or ?token= — try each until one verifies."""
    candidates: list[str] = []
    auth_hdr = request.headers.get(TOKEN_HEADER) or ""
    if auth_hdr.lower().startswith("bearer "):
        candidates.append(auth_hdr[7:].strip())
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        candidates.append(cookie)
    qp = request.query_params.get("token")
    if qp:
        candidates.append(qp.strip())
    seen: set[str] = set()
    for token in candidates:
        if not token or token in seen:
            continue
        seen.add(token)
        user_id = verify_token(token)
        if user_id:
            return user_id
    return None


def require_user(request: Request) -> str:
    user_id = resolve_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


def check_request(request: Request) -> None:
    """Legacy hook — API key only."""
    check_api_key(request)
