"""Web-search-as-source — Brave search + LLM company extraction."""
from __future__ import annotations

import json
import re

from .. import brave
from .. import llm
from .. import usage
from .osm import Company


def _extract_companies_llm(query: str, snippets: list[dict], limit: int = 15) -> list[dict]:
    if not llm.available() or not snippets:
        return _extract_companies_heuristic(snippets, limit)
    blob = "\n".join(
        f"- {s.get('title','')}: {s.get('description','')[:200]} ({s.get('url','')})"
        for s in snippets[:20]
    )
    raw = llm.complete(
        system=(
            "Extract B2B companies from search snippets. Return JSON array only: "
            '[{"name":"...","website":"... or null","city":"... or null","description":"..."}]'
        ),
        user=f"Query: {query}\n\nSnippets:\n{blob}",
        max_tokens=1200,
        temperature=0.2,
    )
    if not raw:
        return _extract_companies_heuristic(snippets, limit)
    m = re.search(r"\[[\s\S]*\]", raw)
    if not m:
        return _extract_companies_heuristic(snippets, limit)
    try:
        return json.loads(m.group())[:limit]
    except json.JSONDecodeError:
        return _extract_companies_heuristic(snippets, limit)


def _extract_companies_heuristic(snippets: list[dict], limit: int) -> list[dict]:
    out = []
    for s in snippets[:limit]:
        title = s.get("title", "")
        name = title.split("—")[0].split("|")[0].split("-")[0].strip()
        if len(name) < 3:
            continue
        out.append({
            "name": name[:80],
            "website": s.get("url"),
            "city": "",
            "description": s.get("description", "")[:200],
        })
    return out


def discover_web(
    query: str,
    city: str = "",
    country: str = "Ukraine",
    limit: int = 20,
) -> list[Company]:
    if not brave.available():
        raise RuntimeError("BRAVE_SEARCH_API_KEY required for web discovery")
    if not usage.allowed("brave"):
        raise RuntimeError("Brave budget exceeded")

    full_query = f"{query} {city} {country}".strip()
    from ..brave import web_search
    results = web_search(full_query, count=min(20, limit * 2)) or []
    extracted = _extract_companies_llm(full_query, results, limit=limit)

    companies: list[Company] = []
    seen: set[str] = set()
    for item in extracted:
        name = (item.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        website = item.get("website")
        if website and not website.startswith("http"):
            website = "https://" + website.lstrip("/")
        enrichment = {
            "emails": [], "phones": [], "socials": {},
            "signals": {"web_discovery": True, "query": query},
            "decision_makers": [],
        }
        c = Company(
            name=name,
            category=query,
            city=item.get("city") or city,
            country=country,
            website=website,
            source="web_discovery",
            raw_tags={"description": item.get("description"), "_enrichment": enrichment},
        )
        companies.append(c)
        if len(companies) >= limit:
            break
    return companies
