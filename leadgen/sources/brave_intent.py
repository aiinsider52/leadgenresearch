"""Discover companies showing current buying intent through Brave web search."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from ..brave import available, web_search
from ..identity import NON_COMPANY_DOMAINS, domain, normalize_text
from ..enrich.brave_intent import INTENT_PATTERNS
from .osm import Company

TITLE_SPLIT_RE = re.compile(r"\s+(?:[-–—|:])\s+")


def _company_name(title: str, host: str) -> str:
    candidate = TITLE_SPLIT_RE.split(title or "")[0].strip()
    if 2 <= len(candidate) <= 100:
        return candidate
    return host.split(".")[0].replace("-", " ").title()


def discover_brave_intent(category: str, city: str = "", country: str = "Ukraine",
                          limit: int = 50) -> list[Company]:
    if not available():
        raise RuntimeError("BRAVE_SEARCH_API_KEY not set (env or data/secrets.env).")
    queries = [
        f'"{city}" "{category}" (hiring OR vacancy OR tender OR procurement OR RFP)',
        f'"{city}" "{category}" (expansion OR "new office" OR automation)',
    ]
    out, seen = [], set()
    for query in queries:
        for item in web_search(query, count=min(20, limit), freshness="py"):
            url = item.get("url") or ""
            host = domain(url)
            if not host or host in NON_COMPANY_DOMAINS or host in seen:
                continue
            text = " ".join(str(x) for x in (
                item.get("title"), item.get("description"), *(item.get("extra_snippets") or [])
            ) if x)
            hits = [name for name, pattern in INTENT_PATTERNS.items() if pattern.search(text)]
            if not hits:
                continue
            name = _company_name(item.get("title") or "", host)
            if not normalize_text(name):
                continue
            seen.add(host)
            signals = {x: True for x in hits}
            signals["intent_evidence"] = [{
                "title": item.get("title"), "url": url, "signals": hits,
            }]
            out.append(Company(
                name=name, category=category, city=city, country=country,
                website=f"https://{host}", source="brave_intent",
                raw_tags={"_enrichment": {"signals": signals, "pages_crawled": [url]}},
            ))
            if len(out) >= limit:
                return out
    return out
