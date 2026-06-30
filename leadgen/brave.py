"""Cached Brave Search API client for web, places, and news."""
from __future__ import annotations

import hashlib
import json
import time
import threading
from pathlib import Path
from typing import Any

import requests

from . import usage
from .config import data_dir, get

BASE = "https://api.search.brave.com/res/v1"
CACHE_DIR = data_dir("brave_cache")
TTL = {"web": 30 * 86400, "places": 30 * 86400, "news": 7 * 86400}
_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST = 0.0


def available() -> bool:
    return bool(get("BRAVE_SEARCH_API_KEY"))


def cache_allowed() -> bool:
    """Full API response caching requires a Brave plan with storage rights."""
    return str(get("BRAVE_ALLOW_CACHE", "false")).lower() in ("1", "true", "yes", "on")


def _cache_path(kind: str, params: dict) -> Path:
    raw = json.dumps(params, ensure_ascii=False, sort_keys=True)
    key = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{kind}_{key}.json"


def _request(kind: str, endpoint: str, params: dict, timeout: int = 25) -> dict:
    path = _cache_path(kind, params)
    if cache_allowed() and path.exists() and time.time() - path.stat().st_mtime < TTL[kind]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    if not available():
        return {}
    if not usage.allowed("brave"):
        raise RuntimeError("Brave budget exceeded for this month — raise BRAVE_BUDGET_USD.")
    global _LAST_REQUEST
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": get("BRAVE_SEARCH_API_KEY") or "",
    }
    with _REQUEST_LOCK:
        min_interval = float(get("BRAVE_MIN_INTERVAL_SECONDS", "1.05") or "1.05")
        wait = min_interval - (time.monotonic() - _LAST_REQUEST)
        if wait > 0:
            time.sleep(wait)
        r = requests.get(BASE + endpoint, params=params, headers=headers, timeout=timeout)
        _LAST_REQUEST = time.monotonic()
        usage.record("brave")
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 1.5))
            r = requests.get(BASE + endpoint, params=params, headers=headers, timeout=timeout)
            _LAST_REQUEST = time.monotonic()
            usage.record("brave")
    if r.status_code >= 400:
        raise RuntimeError(f"Brave {kind} failed: HTTP {r.status_code} {r.text[:200]}")
    data = r.json()
    if cache_allowed():
        try:
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return data


def web_search(query: str, *, count: int = 10, country: str = "ALL",
               search_lang: str = "en", freshness: str = "") -> list[dict]:
    params: dict[str, Any] = {
        "q": query, "count": min(max(count, 1), 20), "country": country,
        "search_lang": search_lang, "extra_snippets": "true",
        "text_decorations": "false", "result_filter": "web",
    }
    if freshness:
        params["freshness"] = freshness
    return ((_request("web", "/web/search", params).get("web") or {}).get("results") or [])


def place_search(query: str, *, location: str = "", latitude: float | None = None,
                 longitude: float | None = None, radius: int | None = None,
                 count: int = 50, country: str = "US", search_lang: str = "en") -> list[dict]:
    params: dict[str, Any] = {
        "q": query, "count": min(max(count, 1), 100), "country": country,
        "search_lang": search_lang, "units": "metric",
    }
    if location:
        params["location"] = location
    if latitude is not None and longitude is not None:
        params.update({"latitude": latitude, "longitude": longitude})
    if radius:
        params["radius"] = radius
    return _request("places", "/local/place_search", params).get("results") or []


def news_search(query: str, *, count: int = 10, country: str = "ALL",
                search_lang: str = "en", freshness: str = "py") -> list[dict]:
    params = {
        "q": query, "count": min(max(count, 1), 50), "country": country,
        "search_lang": search_lang, "freshness": freshness,
        "extra_snippets": "true",
    }
    return _request("news", "/news/search", params).get("results") or []


def status() -> dict:
    return {"available": available(), "cache_allowed": cache_allowed(),
            "cache_dir": str(CACHE_DIR)}
