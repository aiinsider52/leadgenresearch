"""AI-tailored automation recommendations.

Instead of the same 8 curated offers for every lead, GPT looks at THIS
company and proposes specific automations, then we back each with a real
template pulled live from the n8n.io library (9000+). Falls back to the
deterministic matcher when no API key.
"""
from __future__ import annotations

import json
import re

from .. import llm
from .n8n_templates import search_templates

_LANG = {"uk": "Ukrainian", "ru": "Russian", "en": "English"}


def _facts(lead: dict) -> dict:
    c = lead.get("company", {})
    en = lead.get("enrichment", {})
    return {
        "name": c.get("name"),
        "industry": c.get("gmaps_category") or c.get("category"),
        "city": c.get("city"),
        "size": (en.get("profile", {}) or {}).get("size_band") or c.get("size_band"),
        "rating": c.get("rating"),
        "reviews": c.get("reviews"),
        "hiring": (en.get("signals", {}) or {}).get("hiring"),
        "has_email": bool(en.get("emails")),
        "socials": list((en.get("socials", {}) or {}).keys()),
        "has_website": bool(c.get("website")),
    }


def ai_recommend(lead: dict, lang: str = "uk", n: int = 3) -> list[dict] | None:
    """Returns [{name, pitch, search, template:{name,url,nodes}|None}] or None
    (no key / failure → caller uses the deterministic recommender)."""
    if not llm.available():
        return None
    facts = _facts(lead)
    raw = llm.complete(
        system=(
            f"You are an n8n automation consultant. Recommend {n} automations tailored to THIS "
            f"specific business. Reply in {_LANG.get(lang,'Ukrainian')}. "
            "Output ONLY a valid JSON array, no prose. Each item: "
            '{"title": short name, "pitch": one sentence on the concrete value FOR THIS company, '
            '"search": 2-4 English keywords to find a matching n8n template}. '
            "Be specific to the company's industry, size and signals — avoid generic suggestions."
        ),
        user=f"Company: {json.dumps(facts, ensure_ascii=False)}",
        max_tokens=600,
        temperature=0.7,
    )
    if not raw:
        return None
    items = _parse_json_array(raw)
    if not items:
        return None

    out: list[dict] = []
    for it in items[:n]:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        tmpl = None
        kw = (it.get("search") or title).strip()
        try:
            hits = search_templates(kw, rows=1)
            if hits:
                tmpl = hits[0].to_dict()
        except Exception:
            tmpl = None
        out.append({
            "name": title,
            "pitch": (it.get("pitch") or "").strip(),
            "search": kw,
            "template": tmpl,
            "ai": True,
        })
    return out or None


def _parse_json_array(text: str):
    """Tolerant JSON-array extraction (handles ```json fences / stray prose)."""
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        return None
