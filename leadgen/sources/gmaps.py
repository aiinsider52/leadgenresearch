"""Google Maps / Places discovery (inspired by christivn/mapScraper).

Queries Google's Places tab directly (no browser) via the `udm=1` parameter,
which is faster than Selenium/Playwright. Returns companies with rating and
review counts — signals OSM lacks — plus a rough company-size band.

⚠️ Google scraping is against Google's ToS and may hit consent walls or
rate limits. OSM (sources/osm.py) stays the reliable default; this is an
optional richer source. Set GOOGLE_SEARCH_PROXY to route via a proxy if blocked.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

import requests

from .osm import Company  # reuse the same shape downstream

SEARCH_URL = "https://www.google.com/search"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "uk,en;q=0.8",
}

# Rough size band from review volume (proxy for footfall/maturity).
def _size_from_reviews(n: Optional[int]) -> Optional[str]:
    if n is None:
        return None
    if n < 20:
        return "micro"
    if n < 100:
        return "small"
    if n < 500:
        return "medium"
    return "large"


def discover_gmaps(
    category: str,
    city: str,
    country: Optional[str] = "Ukraine",
    limit: int = 20,
    hl: str = "uk",
    gl: str = "ua",
) -> list[Company]:
    """Discover businesses via Google Places tab. Best-effort / experimental."""
    query = f"{category} {city}"
    params = {"q": query, "udm": "1", "hl": hl, "gl": gl, "num": str(min(limit, 20))}
    proxies = None
    if os.environ.get("GOOGLE_SEARCH_PROXY"):
        proxies = {"http": os.environ["GOOGLE_SEARCH_PROXY"], "https": os.environ["GOOGLE_SEARCH_PROXY"]}

    r = requests.get(SEARCH_URL, params=params, headers=HEADERS, proxies=proxies, timeout=25)
    html = r.text
    if r.status_code != 200 or "did not match any documents" in html:
        return []
    if "consent.google.com" in r.url or "Before you continue" in html:
        raise RuntimeError("Google consent wall — set GOOGLE_SEARCH_PROXY or use OSM source.")

    results = _parse_places(html, category, city, country or "", limit)
    if not results and ("enablejs" in html or "noscript" in html.lower()):
        raise RuntimeError(
            "Google served a JS-gated page (no results in HTML). "
            "Use the OSM source, a SerpAPI key, or a JS-rendering proxy."
        )
    return results


# Business names sit near rating patterns like "4,7(123)" / "4.7(1.2K)".
RATING_RE = re.compile(r"(\d[.,]\d)\s*\((\d[\d.,]*\s*[KkТт]?)\)")
WEBSITE_RE = re.compile(r'https?://(?!\S*google\.)([^\s"\'<>]+)')


def _to_int_reviews(raw: str) -> Optional[int]:
    raw = raw.strip().replace("\xa0", "").replace(" ", "")
    mult = 1
    if raw[-1:] in ("K", "k", "Т", "т"):
        mult = 1000
        raw = raw[:-1]
    raw = raw.replace(",", ".")
    try:
        return int(float(raw) * mult)
    except ValueError:
        return None


def _parse_places(html: str, category: str, city: str, country: str, limit: int) -> list[Company]:
    """Heuristic parser for the Places SERP. Resilient to missing fields,
    fragile to Google markup changes — by design kept simple."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    text_blocks = soup.find_all(string=RATING_RE)
    companies: list[Company] = []
    seen: set[str] = set()

    for node in text_blocks:
        m = RATING_RE.search(str(node))
        if not m:
            continue
        rating = float(m.group(1).replace(",", "."))
        reviews = _to_int_reviews(m.group(2))
        # Walk up to a container that holds the business name (a heading-ish node).
        container = node.parent
        for _ in range(4):
            if container and container.parent:
                container = container.parent
        name = None
        if container:
            for h in container.find_all(["span", "div"], limit=12):
                t = h.get_text(" ", strip=True)
                if t and 2 < len(t) < 60 and not RATING_RE.search(t) and not t[0].isdigit():
                    name = t
                    break
        if not name or name in seen:
            continue
        seen.add(name)
        wm = WEBSITE_RE.search(str(container)) if container else None
        website = ("https://" + wm.group(1)) if wm else None
        companies.append(Company(
            name=name, category=category, city=city, country=country,
            website=website, phone=None, address=None,
            source="gmaps",
            raw_tags={"rating": rating, "reviews": reviews, "size_band": _size_from_reviews(reviews)},
        ))
        if len(companies) >= limit:
            break
    return companies


if __name__ == "__main__":
    import json
    import sys
    cat = sys.argv[1] if len(sys.argv) > 1 else "restaurant"
    town = sys.argv[2] if len(sys.argv) > 2 else "Львів"
    try:
        res = discover_gmaps(cat, town, limit=10)
        print(f"Found {len(res)}")
        for c in res:
            print("•", c.name, "|", c.raw_tags, "|", c.website)
    except RuntimeError as e:
        print("BLOCKED:", e)
