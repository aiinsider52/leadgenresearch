"""AI lead qualification against the user's Ideal Customer Profile (ICP).

GPT rates how well a company fits the ICP (0-100) with a one-line reason —
a smarter complement to the deterministic 0-100 reachability score.
"""
from __future__ import annotations

import re

from .. import llm
from ..service import get_icp

_LANG = {"uk": "Ukrainian", "ru": "Russian", "en": "English"}


def qualify(lead: dict, lang: str = "uk") -> dict | None:
    icp = get_icp()
    if not icp or not llm.available():
        return None
    c = lead.get("company", {})
    en = lead.get("enrichment", {})
    facts = {
        "name": c.get("name"), "industry": c.get("gmaps_category") or c.get("category"),
        "city": c.get("city"), "size": (en.get("profile", {}) or {}).get("size_band") or c.get("size_band"),
        "rating": c.get("rating"), "reviews": c.get("reviews"),
        "hiring": (en.get("signals", {}) or {}).get("hiring"),
    }
    raw = llm.complete(
        system=(
            f"You qualify B2B leads against an Ideal Customer Profile. Reply in {_LANG.get(lang,'Ukrainian')}. "
            "Output exactly: a fit score 0-100 on the first line as 'FIT: <n>', then one short line 'WHY: <reason>'."
        ),
        user=f"ICP:\n{icp}\n\nCompany:\n{facts}",
        max_tokens=120, temperature=0.3,
    )
    if not raw:
        return None
    m = re.search(r"FIT:\s*(\d{1,3})", raw)
    fit = max(0, min(100, int(m.group(1)))) if m else None
    why = ""
    wm = re.search(r"WHY:\s*(.+)", raw)
    if wm:
        why = wm.group(1).strip()
    if fit is None:
        return None
    return {"fit": fit, "reason": why, "ai": True}
