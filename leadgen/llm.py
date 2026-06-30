"""Thin OpenAI wrapper. Optional: if no OPENAI_API_KEY is configured, callers
fall back to deterministic templates, so the whole app works offline.

Set the key in env OPENAI_API_KEY or data/secrets.env.
Override the model with LEADGEN_MODEL (default below). If that model id isn't
available on the account, complete() automatically falls back down a chain so
the AI never silently degrades to templates because of one bad model name.
"""
from __future__ import annotations

import json
from typing import Any, Callable

import requests

from . import usage
from .config import get

ENDPOINT = "https://api.openai.com/v1/chat/completions"
PRIMARY_MODEL = "gpt-4o"
FALLBACK_MODELS = ["gpt-4o-mini", "gpt-4-turbo"]

_working_model: str | None = None  # cached after first success


def available() -> bool:
    return bool(get("OPENAI_API_KEY"))


def model_chain() -> list[str]:
    primary = get("LEADGEN_MODEL", PRIMARY_MODEL)
    chain = [primary] + [m for m in FALLBACK_MODELS if m != primary]
    if _working_model:
        chain = [_working_model] + [m for m in chain if m != _working_model]
    return chain


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get('OPENAI_API_KEY')}", "Content-Type": "application/json"}


def _call(model: str, payload: dict):
    return requests.post(
        ENDPOINT,
        headers=_headers(),
        json={**payload, "model": model},
        timeout=120,
    )


def complete(system: str, user: str, max_tokens: int = 700, temperature: float = 0.6) -> str | None:
    """Single-shot completion. Tries the model chain; returns text or None."""
    global _working_model
    if not available() or not usage.allowed("openai"):
        return None
    payload = {
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    for model in model_chain():
        try:
            r = _call(model, payload)
        except Exception:
            continue
        if r.status_code == 200:
            _working_model = model
            usage.record("openai")
            try:
                return (r.json()["choices"][0]["message"]["content"] or "").strip() or None
            except Exception:
                return None
        if r.status_code in (400, 403, 404):
            continue
        return None
    return None


def agent_model_chain() -> list[str]:
    """Prefer a fast model for tool routing; fall back to the global chain."""
    agent_model = get("LEADGEN_AGENT_MODEL", "gpt-4o-mini")
    return [agent_model] + [m for m in model_chain() if m != agent_model]


def complete_with_tools(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    max_tokens: int = 1200,
    temperature: float = 0.2,
    tool_choice: str | dict = "auto",
    models: list[str] | None = None,
) -> dict[str, Any] | None:
    """Chat completion with function-calling. Returns the assistant message dict
    (content and/or tool_calls) or None on failure / budget block."""
    global _working_model
    if not available() or not usage.allowed("openai"):
        return None
    payload: dict[str, Any] = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "tools": tools,
        "tool_choice": tool_choice,
    }
    chain = models if models is not None else model_chain()
    for model in chain:
        try:
            r = _call(model, payload)
        except Exception:
            continue
        if r.status_code == 200:
            _working_model = model
            usage.record("openai")
            try:
                return r.json()["choices"][0]["message"]
            except Exception:
                return None
        if r.status_code in (400, 403, 404):
            continue
        return None
    return None


def stream_chat(
    messages: list[dict[str, Any]],
    on_token: Callable[[str], None] | None = None,
    *,
    max_tokens: int = 2000,
    temperature: float = 0.5,
) -> str | None:
    """Stream a plain chat reply (no tools). Calls on_token for each delta."""
    if not available() or not usage.allowed("openai"):
        return None
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    for model in model_chain():
        try:
            r = requests.post(
                ENDPOINT,
                headers=_headers(),
                json={**payload, "model": model},
                timeout=120,
                stream=True,
            )
        except Exception:
            continue
        if r.status_code != 200:
            if r.status_code in (400, 403, 404):
                continue
            return None
        global _working_model
        _working_model = model
        usage.record("openai")
        parts: list[str] = []
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            chunk = line[6:]
            if chunk == "[DONE]":
                break
            try:
                delta = json.loads(chunk)["choices"][0].get("delta", {})
            except Exception:
                continue
            text = delta.get("content") or ""
            if text:
                parts.append(text)
                if on_token:
                    on_token(text)
        return "".join(parts).strip() or None
    return None


def status() -> dict:
    """For the UI: whether AI is on + which model is actually serving."""
    global _working_model
    if available() and _working_model is None:
        complete("ping", "ping", max_tokens=1)
    return {"ai": available(), "model": _working_model or get("LEADGEN_MODEL", PRIMARY_MODEL)}
