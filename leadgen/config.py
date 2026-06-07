"""Lightweight config / secrets loader.

Reads from environment first, then data/secrets.env (gitignored). Keeps API
tokens out of source code and out of version control.
"""
from __future__ import annotations

import os
from pathlib import Path

_SECRETS = Path(__file__).resolve().parent.parent / "data" / "secrets.env"
_cache: dict[str, str] = {}
_cache_mtime: float = -1.0


def _load() -> dict[str, str]:
    """Read secrets.env, re-reading when the file changes (so a token added
    while the server runs is picked up without a restart)."""
    global _cache, _cache_mtime
    if not _SECRETS.exists():
        return {}
    mtime = _SECRETS.stat().st_mtime
    if mtime != _cache_mtime:
        parsed: dict[str, str] = {}
        for line in _SECRETS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                parsed[k.strip()] = v.strip()
        _cache, _cache_mtime = parsed, mtime
    return _cache


def get(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key) or _load().get(key) or default


def data_dir(sub: str = "") -> Path:
    """Return a writable data directory.

    On serverless hosts (Vercel) the project FS is read-only except /tmp, so
    fall back there. Locally it stays alongside the project.
    """
    base = Path(__file__).resolve().parent.parent / "data"
    try:
        base.mkdir(parents=True, exist_ok=True)
        (base / ".write_test").touch()
        (base / ".write_test").unlink()
    except OSError:
        base = Path("/tmp/leadgen_data")
        base.mkdir(parents=True, exist_ok=True)
    target = base / sub if sub else base
    if sub:
        target.mkdir(parents=True, exist_ok=True)
    return target
