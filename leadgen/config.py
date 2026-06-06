"""Lightweight config / secrets loader.

Reads from environment first, then data/secrets.env (gitignored). Keeps API
tokens out of source code and out of version control.
"""
from __future__ import annotations

import os
from pathlib import Path

_SECRETS = Path(__file__).resolve().parent.parent / "data" / "secrets.env"
_cache: dict[str, str] | None = None


def _load() -> dict[str, str]:
    global _cache
    if _cache is not None:
        return _cache
    _cache = {}
    if _SECRETS.exists():
        for line in _SECRETS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                _cache[k.strip()] = v.strip()
    return _cache


def get(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key) or _load().get(key) or default
