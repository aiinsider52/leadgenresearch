"""LinkedIn company employees via Apify."""
from __future__ import annotations

import requests

from ..config import get as cfg
from .. import usage
from .osm import Company

DEFAULT_ACTOR = cfg("APIFY_LINKEDIN_COMPANY_ACTOR", "curious_coder/linkedin-company-employees-scraper")


def discover_linkedin_company(
    company_query: str,
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

    payload = {"companyName": company_query, "maxResults": max(limit, 10)}
    actor = DEFAULT_ACTOR.replace("/", "~")
    url = f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
    r = requests.post(url, params={"token": token}, json=payload, timeout=timeout)
    usage.record("apify")
    if r.status_code >= 400:
        raise RuntimeError(f"LinkedIn company Apify failed: HTTP {r.status_code}")

    items = r.json() if isinstance(r.json(), list) else []
    staff = []
    company_name = company_query
    website = None
    for it in items[:limit]:
        name = it.get("name") or it.get("fullName")
        if not name:
            continue
        staff.append({
            "name": name,
            "role": it.get("title") or it.get("headline") or "",
            "linkedin": it.get("linkedinUrl") or it.get("profileUrl"),
        })
        company_name = it.get("companyName") or company_name
        website = website or it.get("companyWebsite")

    enrichment = {
        "staff": staff,
        "decision_makers": staff[:5],
        "emails": [], "phones": [], "socials": {},
        "signals": {"linkedin_employees": len(staff)},
    }
    c = Company(
        name=company_name,
        category="linkedin_company",
        city=city,
        country=country,
        website=website,
        source="linkedin_company",
        raw_tags={"_enrichment": enrichment},
    )
    return [c] if staff else []
