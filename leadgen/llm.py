"""Thin OpenAI wrapper. Optional: if no OPENAI_API_KEY is configured, callers
fall back to deterministic templates, so the whole app works offline.

Set the key in env OPENAI_API_KEY or data/secrets.env.
Override the model with LEADGEN_MODEL (default below). If that model id isn't
available on the account, complete() automatically falls back down a chain so
the AI never silently degrades to templates because of one bad model name.
"""
from __future__ import annotations

import requests

from . import usage
from .config import get

ENDPOINT = "https://api.openai.com/v1/chat/completions"
PRIMARY_MODEL = "gpt-5.5"          # requested default
FALLBACK_MODELS = ["gpt-4o", "gpt-4o-mini"]  # used if the primary id is invalid

_working_model: str | None = None  # cached after first success


def available() -> bool:
    return bool(get("OPENAI_API_KEY"))


def model_chain() -> list[str]:
    primary = get("LEADGEN_MODEL", PRIMARY_MODEL)
    chain = [primary] + [m for m in FALLBACK_MODELS if m != primary]
    if _working_model:  # prefer the model we already know works
        chain = [_working_model] + [m for m in chain if m != _working_model]
    return chain


def _call(model: str, system: str, user: str, max_tokens: int, temperature: float):
    return requests.post(
        ENDPOINT,
        headers={"Authorization": f"Bearer {get('OPENAI_API_KEY')}", "Content-Type": "application/json"},
        json={"model": model, "max_tokens": max_tokens, "temperature": temperature,
              "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        timeout=45,
    )


def complete(system: str, user: str, max_tokens: int = 700, temperature: float = 0.6) -> str | None:
    """Single-shot completion. Tries the model chain; returns text or None
    (caller then uses its template fallback)."""
    global _working_model
    if not available() or not usage.allowed("openai"):
        return None
    for model in model_chain():
        try:
            r = _call(model, system, user, max_tokens, temperature)
        except Exception:
            continue
        if r.status_code == 200:
            _working_model = model
            usage.record("openai")
            try:
                return (r.json()["choices"][0]["message"]["content"] or "").strip() or None
            except Exception:
                return None
        # 400/403/404 = model unknown / no access on this project → try next.
        if r.status_code in (400, 403, 404):
            continue
        # 401 auth / 429 rate / 5xx server → stop, fall back to template.
        return None
    return None


def status() -> dict:
    """For the UI: whether AI is on + which model is actually serving.
    Probes once (cheap) to resolve the real working model if not known yet."""
    if available() and _working_model is None:
        complete("ping", "ping", max_tokens=1)  # populates _working_model
    return {"ai": available(), "model": _working_model or get("LEADGEN_MODEL", PRIMARY_MODEL)}
