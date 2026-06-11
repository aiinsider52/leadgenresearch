"""AI niche fan-out: expand one category into many related search terms so a
single user query sweeps the whole niche (marketing agency → SMM, digital,
branding, PPC, performance, …). Cached per niche; falls back to [category].
"""
from __future__ import annotations

import json

from .. import llm
from ..config import data_dir

_CACHE = data_dir() / "niche_cache.json"


def _load() -> dict:
    if _CACHE.exists():
        try:
            return json.loads(_CACHE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save(d: dict) -> None:
    _CACHE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def expand_niche(category: str, lang: str = "uk", n: int = 12) -> list[str]:
    """Return [category] + related search terms. GPT when available, cached."""
    cat = category.strip()
    if not cat:
        return []
    cache = _load()
    if cat.lower() in cache:
        return cache[cat.lower()]
    if not llm.available():
        return [cat]

    raw = llm.complete(
        system=(
            "You expand a business niche into closely-related search terms used to find "
            "more companies of the same kind on maps/social/job sites. "
            "Output ONLY a JSON array of short search phrases (2-3 words each), in the same "
            "language as the input, including the original. No prose."
        ),
        user=f"Niche: {cat}. Give up to {n} related search terms.",
        max_tokens=300, temperature=0.7,
    )
    terms = [cat]
    if raw:
        m = raw[raw.find("["): raw.rfind("]") + 1]
        try:
            arr = json.loads(m)
            for t in arr:
                t = str(t).strip()
                if t and t.lower() not in (x.lower() for x in terms):
                    terms.append(t)
        except (json.JSONDecodeError, ValueError):
            pass
    terms = terms[:n]
    cache[cat.lower()] = terms
    _save(cache)
    return terms
