"""Lightweight usage + budget tracking for paid operations (Apify, OpenAI).

Records rough cost estimates per month and blocks new paid calls once a cap is
hit. Caps come from config: APIFY_BUDGET_USD / OPENAI_BUDGET_USD (default 25/10).
Estimates are approximate — meant to prevent runaway spend, not for billing.
"""
from __future__ import annotations

import json
from datetime import date

from .config import data_dir, get

USAGE_FILE = data_dir() / "usage.json"

# Rough per-unit cost estimates (USD).
APIFY_RUN_USD = 0.12          # one Instagram/Maps actor run
OPENAI_CALL_USD = 0.01        # one gpt-4o completion (short)


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
                  "openai_calls": 0, "openai_usd": 0.0})
    return d


def _cap(kind: str) -> float:
    key = "APIFY_BUDGET_USD" if kind == "apify" else "OPENAI_BUDGET_USD"
    try:
        return float(get(key, "25" if kind == "apify" else "10"))
    except (TypeError, ValueError):
        return 25.0 if kind == "apify" else 10.0


def allowed(kind: str) -> bool:
    """Is a paid call of this kind still within budget this month?"""
    d = _cur(_read())
    spent = d["apify_usd"] if kind == "apify" else d["openai_usd"]
    return spent < _cap(kind)


def record(kind: str, usd: float | None = None) -> None:
    d = _cur(_read())
    if kind == "apify":
        d["apify_runs"] += 1
        d["apify_usd"] = round(d["apify_usd"] + (usd or APIFY_RUN_USD), 4)
    else:
        d["openai_calls"] += 1
        d["openai_usd"] = round(d["openai_usd"] + (usd or OPENAI_CALL_USD), 4)
    _write(d)


def summary() -> dict:
    d = _cur(_read())
    return {
        "month": d["month"],
        "apify": {"runs": d["apify_runs"], "usd": round(d["apify_usd"], 2), "cap": _cap("apify")},
        "openai": {"calls": d["openai_calls"], "usd": round(d["openai_usd"], 2), "cap": _cap("openai")},
    }
