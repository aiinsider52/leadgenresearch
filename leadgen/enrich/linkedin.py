"""LinkedIn enrichment for decision-makers — ToS-safe by design.

We do NOT scrape LinkedIn (against their ToS, gets accounts banned and is
legally risky). Instead we:
  1. harvest personal /in/ profile links the company already published
     on its own site (team/about pages frequently link them);
  2. build ready-made *search* URLs (LinkedIn people search + Google
     site-search) so a human can open and verify the right profile in one click.

This keeps outreach research fast while staying on the right side of ToS/GDPR.
"""
from __future__ import annotations

import re
from urllib.parse import quote_plus

PROFILE_RE = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/[A-Za-z0-9\-_%]+/?", re.I)
COMPANY_RE = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/company/[A-Za-z0-9\-_%]+/?", re.I)


def extract_profiles(html: str) -> dict:
    """Pull LinkedIn personal + company URLs that the site itself links."""
    profiles = sorted({m.rstrip("/") for m in PROFILE_RE.findall(html)})
    companies = sorted({m.rstrip("/") for m in COMPANY_RE.findall(html)})
    return {"profiles": profiles, "company": companies[0] if companies else None}


def people_search_url(name: str, company: str = "") -> str:
    kw = quote_plus(f"{name} {company}".strip())
    return f"https://www.linkedin.com/search/results/people/?keywords={kw}"


def google_profile_search_url(name: str, company: str = "") -> str:
    q = quote_plus(f'site:linkedin.com/in "{name}" {company}'.strip())
    return f"https://www.google.com/search?q={q}"


def _slug_match(profile_url: str, name: str) -> bool:
    """Does a /in/<slug> look like it belongs to `name`?"""
    slug = profile_url.rstrip("/").rsplit("/in/", 1)[-1].lower()
    slug = re.sub(r"[-_]\w{4,}$", "", slug)  # drop trailing hash segments
    parts = [p for p in re.split(r"[^a-zа-яёїієґ]+", name.lower()) if len(p) > 1]
    return sum(1 for p in parts if p in slug) >= min(2, len(parts))


def enrich_people(decision_makers: list[dict], company_name: str, html_profiles: list[str]) -> list[dict]:
    """Attach a LinkedIn profile (if linked on-site) + search links to each
    decision-maker. Mutates and returns the list of dicts."""
    for dm in decision_makers:
        name = dm.get("name", "")
        matched = next((p for p in html_profiles if _slug_match(p, name)), None)
        dm["linkedin"] = matched or dm.get("linkedin")
        dm["linkedin_search"] = people_search_url(name, company_name)
        dm["google_search"] = google_profile_search_url(name, company_name)
    return decision_makers


if __name__ == "__main__":
    html = '<a href="https://www.linkedin.com/in/max-mustermann-12ab34/">Max</a>'
    print(extract_profiles(html))
    dms = [{"name": "Max Mustermann", "role": "CEO"}]
    print(enrich_people(dms, "Acme GmbH", extract_profiles(html)["profiles"])[0])
