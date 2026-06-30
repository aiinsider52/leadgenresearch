"""Lightweight usage + budget tracking for paid operations (Apify, OpenAI).

Records rough cost estimates per month and blocks new paid calls once a cap is
hit. Caps come from config: APIFY_BUDGET_USD / OPENAI_BUDGET_USD /
BRAVE_BUDGET_USD (default 25/10/5).
Estimates are approximate — meant to prevent runaway spend, not for billing.
"""
from __future__ import annotations

import json
import threading
from datetime import date

from .config import data_dir, get

USAGE_FILE = data_dir() / "usage.json"

# Rough per-unit cost estimates (USD).
APIFY_RUN_USD = 0.12          # one Instagram/Maps actor run
OPENAI_CALL_USD = 0.01        # one gpt-4o completion (short)
BRAVE_CALL_USD = 0.005        # Search plan: $5 / 1,000 requests
_LOCK = threading.Lock()


def _month() -> str:
    return date.today().strftime("%Y-%m")


def _read() -> dict:
    if USAGE_FILE.exists():
        try:
            return json.loads(USAGE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write(d: dict) -> None:
    USAGE_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _cur(d: dict) -> dict:
    m = _month()
    if d.get("month") != m:                 # reset at month boundary
        d.clear()
        d.update({"month": m, "apify_runs": 0, "apify_usd": 0.0,
                  "openai_calls": 0, "openai_usd": 0.0,
                  "brave_calls": 0, "brave_usd": 0.0,
                  "apollo_calls": 0, "apollo_usd": 0.0,
                  "hunter_calls": 0, "hunter_usd": 0.0})
    d.setdefault("brave_calls", 0)
    d.setdefault("brave_usd", 0.0)
    d.setdefault("apollo_calls", 0)
    d.setdefault("apollo_usd", 0.0)
    d.setdefault("hunter_calls", 0)
    d.setdefault("hunter_usd", 0.0)
    return d


def _cap(kind: str) -> float:
    keys = {
        "apify": ("APIFY_BUDGET_USD", "25"),
        "openai": ("OPENAI_BUDGET_USD", "10"),
        "brave": ("BRAVE_BUDGET_USD", "5"),
        "apollo": ("APOLLO_BUDGET_USD", "20"),
        "hunter": ("HUNTER_BUDGET_USD", "10"),
    }
    key, default = keys[kind]
    try:
        return float(get(key, default))
    except (TypeError, ValueError):
        return float(default)


def allowed(kind: str) -> bool:
    """Is a paid call of this kind still within budget this month?"""
    d = _cur(_read())
    key = f"{kind}_usd"
    spent = d.get(key, 0)
    return spent < _cap(kind)


# Paid providers required by discovery source (for UI disable + banners).
SOURCE_REQUIRES: dict[str, list[str]] = {
    "brave_places": ["brave"],
    "brave_intent": ["brave"],
    "web_discovery": ["brave"],
    "instagram": ["apify"],
    "facebook": ["apify"],
    "jobs": ["apify"],
    "linkedin_people": ["apify"],
    "linkedin_company": ["apify"],
    "apify_gmaps": ["apify"],
}

ALL_SOURCES_PROVIDERS = ("apify", "brave", "openai")


def _provider_row(kind: str, d: dict) -> dict:
    cap = _cap(kind)
    spent = float(d.get(f"{kind}_usd", 0) or 0)
    blocked = spent >= cap
    return {
        "kind": kind,
        "spent_usd": round(spent, 2),
        "cap_usd": cap,
        "blocked": blocked,
        "allowed": not blocked,
        "pct": min(100.0, round(100 * spent / cap, 1)) if cap > 0 else 100.0,
    }


def budget_status() -> dict:
    """Expose monthly caps for dashboard banners and source availability."""
    d = _cur(_read())
    providers = {
        kind: _provider_row(kind, d)
        for kind in ("apify", "openai", "brave", "apollo", "hunter")
    }
    blocked = [k for k, row in providers.items() if row["blocked"]]
    unavailable_sources = [
        src for src, reqs in SOURCE_REQUIRES.items()
        if any(providers[r]["blocked"] for r in reqs if r in providers)
    ]
    degraded_all = any(providers[k]["blocked"] for k in ALL_SOURCES_PROVIDERS if k in providers)
    return {
        "providers": providers,
        "blocked_providers": blocked,
        "unavailable_sources": sorted(unavailable_sources),
        "degraded_all_sources": degraded_all,
        "enrich_brave_disabled": providers["brave"]["blocked"],
        "enrich_openai_disabled": providers["openai"]["blocked"],
        "source_requires": SOURCE_REQUIRES,
    }


def is_source_available(source: str) -> bool:
    """True if every paid provider required by `source` is within budget."""
    if source == "all_sources":
        return True  # always runnable — free sources still work (degraded mode)
    reqs = SOURCE_REQUIRES.get(source, [])
    if not reqs:
        return True
    return all(allowed(r) for r in reqs)


def record(kind: str, usd: float | None = None) -> None:
    with _LOCK:
        d = _cur(_read())
        if kind == "apify":
            d["apify_runs"] += 1
            d["apify_usd"] = round(d["apify_usd"] + (usd or APIFY_RUN_USD), 4)
        elif kind == "openai":
            d["openai_calls"] += 1
            d["openai_usd"] = round(d["openai_usd"] + (usd or OPENAI_CALL_USD), 4)
        elif kind == "apollo":
            d["apollo_calls"] += 1
            d["apollo_usd"] = round(d["apollo_usd"] + (usd or 0.05), 4)
        elif kind == "hunter":
            d["hunter_calls"] += 1
            d["hunter_usd"] = round(d["hunter_usd"] + (usd or 0.02), 4)
        else:
            d["brave_calls"] += 1
            d["brave_usd"] = round(d["brave_usd"] + (usd or BRAVE_CALL_USD), 4)
        _write(d)


def summary() -> dict:
    d = _cur(_read())
    budget = budget_status()
    return {
        "month": d["month"],
        "apify": {
            "runs": d["apify_runs"], "usd": round(d["apify_usd"], 2), "cap": _cap("apify"),
            "blocked": budget["providers"]["apify"]["blocked"],
        },
        "openai": {
            "calls": d["openai_calls"], "usd": round(d["openai_usd"], 2), "cap": _cap("openai"),
            "blocked": budget["providers"]["openai"]["blocked"],
        },
        "brave": {
            "calls": d["brave_calls"], "usd": round(d["brave_usd"], 2), "cap": _cap("brave"),
            "blocked": budget["providers"]["brave"]["blocked"],
        },
        "apollo": {
            "calls": d.get("apollo_calls", 0), "usd": round(d.get("apollo_usd", 0), 2),
            "cap": _cap("apollo"),
            "blocked": budget["providers"]["apollo"]["blocked"],
        },
        "hunter": {
            "calls": d.get("hunter_calls", 0), "usd": round(d.get("hunter_usd", 0), 2),
            "cap": _cap("hunter"),
            "blocked": budget["providers"]["hunter"]["blocked"],
        },
        "budget": budget,
    }
