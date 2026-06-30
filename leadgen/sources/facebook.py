"""Facebook page discovery via Apify `apify/facebook-search-scraper`.

Finds local businesses / pages by keyword + location — email, website, phone,
follower count. Needs APIFY_TOKEN.
"""
from __future__ import annotations

import re

import requests

from .. import usage
from ..config import get as cfg
from .osm import Company

ACTOR = cfg("APIFY_FACEBOOK_ACTOR", "apify~facebook-search-scraper")
RUN_SYNC = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"


def _first(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


def discover_facebook(
    category: str,
    city: str = "",
    country: str = "Ukraine",
    limit: int = 25,
    timeout: int = 300,
) -> list[Company]:
    token = cfg("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN not set — needed for Facebook source.")
    if not usage.allowed("apify"):
        raise RuntimeError("Apify budget exceeded for this month.")

    location = f"{city}, {country}".strip(", ")
    terms = [t.strip() for t in re.split(r"[,;]", category) if t.strip()] or [category]
    payload = {
        "categories": terms[:5],
        "resultsLimit": max(limit, 10),
    }
    if location:
        payload["locations"] = [location]

    r = requests.post(RUN_SYNC, params={"token": token}, json=payload, timeout=timeout)
    usage.record("apify")
    if r.status_code >= 400:
        raise RuntimeError(f"Facebook Apify failed: HTTP {r.status_code} {r.text[:200]}")

    items = r.json()
    if not isinstance(items, list):
        items = []

    companies: list[Company] = []
    seen: set[str] = set()
    for it in items:
        name = _first(it, "title", "name", "pageName", "page_name")
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        page_url = _first(it, "pageUrl", "facebookUrl", "url", "link")
        website = _first(it, "website", "websiteUrl", "externalUrl")
        email = _first(it, "email")
        phone = _first(it, "phone", "phoneNumber")
        address = _first(it, "address", "location", "street")
        followers = _first(it, "likes", "followers", "followerCount", "fanCount")
        category_name = _first(it, "category", "pageCategory")

        enrichment: dict = {}
        if email:
            enrichment["emails"] = [email] if isinstance(email, str) else list(email)
        if phone:
            enrichment["phones"] = [str(phone)]
        if page_url:
            enrichment["socials"] = {"facebook": page_url}

        companies.append(
            Company(
                name=name,
                category=category,
                city=city,
                country=country,
                website=website or page_url,
                phone=str(phone) if phone else None,
                address=address,
                source="facebook",
                raw_tags={
                    "gmaps_category": category_name,
                    "facebook": page_url,
                    "followers": followers,
                    "_enrichment": enrichment,
                },
            )
        )
        if len(companies) >= limit:
            break
    return companies
