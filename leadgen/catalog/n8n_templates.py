"""Live n8n template library client.

Instead of only our 8 hand-curated sellable automations, this pulls from
n8n's public template gallery (thousands of workflows) and recommends the
most relevant ready-made templates for a given company.

API: https://api.n8n.io/templates/search?search=<q>&rows=<n>
Template page: https://n8n.io/workflows/<id>
Results are cached on disk per query (TTL) to keep it fast and polite.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

API = "https://api.n8n.io/templates/search"
TEMPLATE_URL = "https://n8n.io/workflows/{id}"
HEADERS = {"User-Agent": "leadgen/0.1"}

from ..config import data_dir

CACHE_DIR = data_dir("n8n_cache")  # writable; /tmp on read-only hosts
CACHE_TTL = 60 * 60 * 24 * 7  # 7 days

# Map our company categories / pains to good n8n search terms.
CATEGORY_QUERIES = {
    "restaurant": ["restaurant", "review", "reservation"],
    "dental": ["appointment reminder", "patient", "booking"],
    "clinic": ["appointment", "patient", "healthcare"],
    "beauty": ["booking", "appointment", "instagram"],
    "fitness": ["membership", "booking", "reminder"],
    "law": ["document", "crm", "intake"],
    "real_estate": ["real estate", "lead", "crm"],
    "auto": ["quote", "booking", "crm"],
    "hotel": ["booking", "review", "guest"],
    "retail": ["ecommerce", "shopify", "inventory"],
    "agency": ["content", "social media", "lead"],
    "construction": ["quote", "invoice", "crm"],
    "education": ["enrollment", "email", "crm"],
}


@dataclass
class Template:
    id: int
    name: str
    description: str
    url: str
    nodes: list[str]
    views: int

    def to_dict(self) -> dict:
        return self.__dict__


def _cache_path(query: str) -> Path:
    safe = "".join(c if c.isalnum() else "_" for c in query.lower())[:60]
    return CACHE_DIR / f"{safe}.json"


def search_templates(query: str, rows: int = 8, use_cache: bool = True) -> list[Template]:
    cp = _cache_path(query)
    if use_cache and cp.exists() and (time.time() - cp.stat().st_mtime) < CACHE_TTL:
        try:
            raw = json.loads(cp.read_text(encoding="utf-8"))
            return [Template(**t) for t in raw]
        except (json.JSONDecodeError, TypeError):
            pass
    try:
        r = requests.get(API, params={"search": query, "rows": rows, "page": 1},
                         headers=HEADERS, timeout=20)
        r.raise_for_status()
        wfs = r.json().get("workflows", [])
    except (requests.RequestException, ValueError):
        return []

    out: list[Template] = []
    for w in wfs:
        out.append(Template(
            id=w["id"],
            name=w.get("name", ""),
            description=(w.get("description") or "").split("\n")[0][:200],
            url=TEMPLATE_URL.format(id=w["id"]),
            nodes=[n.get("displayName", "") for n in w.get("nodes", [])][:6],
            views=w.get("totalViews", 0),
        ))
    cp.write_text(json.dumps([t.to_dict() for t in out], ensure_ascii=False), encoding="utf-8")
    return out


def recommend_templates(category: str, pains: Optional[list[str]] = None, top_n: int = 6) -> list[Template]:
    """Recommend ready-made n8n templates for a company category/pains.

    Cheap: queries are cached, so calling this for every lead of the same
    category hits disk, not the network.
    """
    queries = list(CATEGORY_QUERIES.get(category, [category]))
    for p in (pains or []):
        if p and p not in queries:
            queries.append(p)

    terms = [q.lower() for q in queries]
    seen: dict[int, Template] = {}
    for q in queries[:4]:  # cap network/cache lookups
        for t in search_templates(q, rows=6):
            if t.id not in seen:
                seen[t.id] = t

    def relevance(t: Template) -> tuple:
        hay = (t.name + " " + t.description).lower()
        hits = sum(1 for term in terms if term in hay)
        return (hits, t.views)  # keyword overlap first, then popularity

    ranked = sorted(seen.values(), key=relevance, reverse=True)
    return ranked[:top_n]


if __name__ == "__main__":
    import sys
    cat = sys.argv[1] if len(sys.argv) > 1 else "restaurant"
    for t in recommend_templates(cat):
        print(f"[{t.views:>6}] {t.name}")
        print(f"         {t.url}  · nodes: {', '.join(t.nodes)}")
