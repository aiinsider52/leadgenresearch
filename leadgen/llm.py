"""Thin OpenAI wrapper. Optional: if no OPENAI_API_KEY is configured, callers
fall back to deterministic templates, so the whole app works offline.

Set the key in env OPENAI_API_KEY or data/secrets.env. Override the model with
LEADGEN_MODEL (default: gpt-4o-mini). Uses the REST API directly — no SDK.
"""
from __future__ import annotations

import requests

from .config import get

DEFAULT_MODEL = "gpt-4o-mini"
ENDPOINT = "https://api.openai.com/v1/chat/completions"


def available() -> bool:
    return bool(get("OPENAI_API_KEY"))


def complete(system: str, user: str, max_tokens: int = 700, temperature: float = 0.6) -> str | None:
    """Single-shot completion. Returns text, or None on any failure (caller
    then uses its template fallback)."""
    key = get("OPENAI_API_KEY")
    if not key:
        return None
    try:
        model = get("LEADGEN_MODEL", DEFAULT_MODEL)
        r = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=40,
        )
        if r.status_code != 200:
            return None
        return (r.json()["choices"][0]["message"]["content"] or "").strip() or None
    except Exception:
        return None
