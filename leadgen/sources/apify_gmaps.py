"""Google Maps business leads via the Apify actor
`xmiso_scrapers/millions-us-businesses-leads-with-emails-from-google-maps`.

Returns rich, ready leads (email + socials + reviews) from a pre-scraped
database — no site crawl needed. Fast and clean.

⚠️ LIMITATION: this actor's database covers 26 countries (US, GB, most of
the EU, PL, TR, …) but NOT Ukraine. For Ukraine use the Playwright Google
Maps worker (sources/gmaps_playwright.py) or OSM.

Token is read from config (env APIFY_TOKEN or data/secrets.env), never hardcoded.
"""
from __future__ import annotations

from typing import Optional

import requests

from ..config import get as cfg
from .osm import Company

ACTOR = "xmiso_scrapers~millions-us-businesses-leads-with-emails-from-google-maps"
RUN_SYNC = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"

SUPPORTED = {"ALL", "US", "GB", "AE", "AR", "AU", "BE", "BR", "CA", "ES", "FR",
             "IE", "IN", "IT", "JP", "KR", "MX", "NL", "PL", "SA", "SE", "TH",
             "TR", "DK", "NO", "FI", "PT"}

# Map full names / our defaults to ISO codes the actor accepts.
COUNTRY_ALIASES = {
    "united states": "US", "usa": "US", "us": "US",
    "united kingdom": "GB", "uk": "GB", "britain": "GB",
    "poland": "PL", "polska": "PL", "pl": "PL",
    "germany": "DE", "deutschland": "DE",  # note: DE not supported by actor
    "france": "FR", "spain": "ES", "italy": "IT", "netherlands": "NL",
    "ireland": "IE", "canada": "CA", "australia": "AU", "turkey": "TR",
    "sweden": "SE", "norway": "NO", "denmark": "DK", "finland": "FI",
    "portugal": "PT", "brazil": "BR", "india": "IN", "japan": "JP",
    "ukraine": "UA", "україна": "UA", "украина": "UA",  # unsupported -> guarded
}


def resolve_country(country: str) -> str:
    c = (country or "").strip()
    if len(c) == 2:
        return c.upper()
    return COUNTRY_ALIASES.get(c.lower(), c.upper())


def is_supported(country: str) -> bool:
    return resolve_country(country) in SUPPORTED


def _to_enrichment(item: dict) -> dict:
    """Build our enrichment dict straight from the actor's fields."""
    socials = {}
    for net in ("facebook", "instagram", "linkedin"):
        if item.get(net):
            socials[net] = item[net]
    emails = [item["email"]] if item.get("email") else []
    phones = [item["phone_number"]] if item.get("phone_number") else []
    return {
        "emails": emails,
        "phones": phones,
        "socials": socials,
        "telegram": [],
        "decision_makers": [],
        "staff": [],
        "profile": {"size_band": _size(item.get("reviews_number")),
                    "founded": item.get("opening_date")},
        "signals": {},
        "linkedin_profiles": [item["linkedin"]] if item.get("linkedin") else [],
        "pages_crawled": [],
        "source": "apify",
    }


def _size(reviews) -> Optional[str]:
    try:
        n = int(reviews)
    except (TypeError, ValueError):
        return None
    return "micro" if n < 20 else "small" if n < 100 else "medium" if n < 500 else "large"


def discover_apify(
    category: str,
    city: str = "",
    country: str = "US",
    limit: int = 25,
    use_keyword: bool = True,
    timeout: int = 240,
) -> list[Company]:
    token = cfg("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN not set (env or data/secrets.env).")
    code = resolve_country(country)
    if code not in SUPPORTED:
        raise RuntimeError(
            f"Apify actor does not cover '{country}' ({code}). "
            f"Supported: {', '.join(sorted(SUPPORTED - {'ALL'}))}. Use Playwright/OSM."
        )

    payload: dict = {"country": code, "max_results": max(limit, 1)}
    if use_keyword:
        payload["keyword"] = category
    else:
        payload["category"] = category
    if city:
        payload["city"] = city

    r = requests.post(RUN_SYNC, params={"token": token}, json=payload, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"Apify run failed: HTTP {r.status_code} {r.text[:200]}")
    items = r.json()
    if isinstance(items, dict) and items.get("error"):
        raise RuntimeError(f"Apify error: {items['error']}")

    companies: list[Company] = []
    for it in items[:limit]:
        name = it.get("name")
        if not name:
            continue
        addr = ", ".join(p for p in (it.get("street"), it.get("city")) if p)
        companies.append(Company(
            name=name, category=category, city=it.get("city") or city,
            country=it.get("country_code") or code,
            website=it.get("url"), phone=it.get("phone_number"), address=addr or None,
            source="apify",
            raw_tags={
                "rating": it.get("review_score"),
                "reviews": it.get("reviews_number"),
                "size_band": _size(it.get("reviews_number")),
                "gmaps_category": (it.get("google_business_categories") or "").split("|")[0] or None,
                "google_maps_url": it.get("google_maps_url"),
                "_enrichment": _to_enrichment(it),  # prebuilt, consumed by service
            },
        ))
    return companies


if __name__ == "__main__":
    import json
    import sys
    cat = sys.argv[1] if len(sys.argv) > 1 else "restaurant"
    country = sys.argv[2] if len(sys.argv) > 2 else "US"
    city = sys.argv[3] if len(sys.argv) > 3 else ""
    res = discover_apify(cat, city=city, country=country, limit=5)
    print(f"Found {len(res)}")
    for c in res:
        en = c.raw_tags["_enrichment"]
        print("•", c.name, "|", c.raw_tags.get("reviews"), "reviews |",
              en["emails"], "|", list(en["socials"].keys()), "|", c.website)
