"""Thin Claude wrapper. Optional: if no ANTHROPIC_API_KEY is configured,
callers fall back to deterministic templates, so the whole app works offline.

Set the key in env ANTHROPIC_API_KEY or data/secrets.env. Override the model
with LEADGEN_MODEL (default: claude-3-5-sonnet).
"""
from __future__ import annotations

from .config import get

DEFAULT_MODEL = "claude-3-5-sonnet-20240620"
_client = None


def available() -> bool:
    return bool(get("ANTHROPIC_API_KEY"))


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(api_key=get("ANTHROPIC_API_KEY"))
    return _client


def complete(system: str, user: str, max_tokens: int = 700, temperature: float = 0.6) -> str | None:
    """Single-shot completion. Returns text, or None on any failure (caller
    then uses its template fallback)."""
    if not available():
        return None
    try:
        model = get("LEADGEN_MODEL", DEFAULT_MODEL)
        resp = _get_client().messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        return "\n".join(parts).strip() or None
    except Exception:
        return None
