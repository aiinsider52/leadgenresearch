"""LinkedIn people search via Apify (no direct LinkedIn scraping)."""
from __future__ import annotations

from urllib.parse import quote

import requests

from ..config import get as cfg
from .. import usage
from .osm import Company

# harvestapi/linkedin-profile-search — configurable via env
DEFAULT_ACTOR = "2SyF0bVxmgGr8IVCZ"
ACTOR = cfg("APIFY_LINKEDIN_PEOPLE_ACTOR", DEFAULT_ACTOR)


def discover_linkedin_people(
    title: str,
    city: str = "",
    country: str = "Ukraine",
    limit: int = 25,
    timeout: int = 300,
) -> list[Company]:
    token = cfg("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN not set")
    if not usage.allowed("apify"):
        raise RuntimeError("Apify budget exceeded")

    location = f"{city}, {country}" if city else country
    payload = {
        "searchQuery": f"{title} {location}".strip(),
        "maxResults": max(limit, 10),
    }
    url = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"
    r = requests.post(url, params={"token": token}, json=payload, timeout=timeout)
    usage.record("apify")
    if r.status_code >= 400:
        raise RuntimeError(f"LinkedIn people Apify failed: HTTP {r.status_code}")

    companies: list[Company] = []
    seen: set[str] = set()
    for it in r.json() if isinstance(r.json(), list) else []:
        name = it.get("fullName") or it.get("name") or ""
        company_name = it.get("company") or it.get("companyName") or name
        if not name:
            continue
        key = (company_name or name).lower()
        if key in seen:
            continue
        seen.add(key)

        role = it.get("headline") or it.get("title") or title
        linkedin = it.get("linkedinUrl") or it.get("url")
        dm = [{
            "name": name,
            "role": role,
            "linkedin": linkedin,
            "source_url": linkedin,
        }]
        enrichment = {
            "emails": [], "phones": [],
            "socials": {"linkedin": linkedin} if linkedin else {},
            "decision_makers": dm,
            "staff": [], "signals": {"linkedin_people": True},
            "linkedin_profiles": [linkedin] if linkedin else [],
        }
        c = Company(
            name=company_name,
            category=title,
            city=city or (it.get("location") or ""),
            country=country,
            website=it.get("companyWebsite"),
            source="linkedin_people",
            raw_tags={"_enrichment": enrichment, "person_name": name},
        )
        companies.append(c)
        if len(companies) >= limit:
            break
    return companies
