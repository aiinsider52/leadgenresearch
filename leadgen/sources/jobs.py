"""Hiring-signal lead discovery via LinkedIn Jobs (Apify actor
curious_coder/linkedin-jobs-scraper).

A company posting a job for a role = active intent + budget for that work.
Instead of applying, we pitch automating it. Each job yields a lead with the
company, its website (→ email via enrichment), size, AND the job poster as a
decision-maker (name, title, LinkedIn). The job title drives the outreach angle.

Token from config (APIFY_TOKEN). Respects the monthly Apify budget.
"""
from __future__ import annotations

from urllib.parse import quote
from typing import Optional

import requests

from ..config import get as cfg
from .osm import Company

ACTOR = "hKByXkMQaC5Qt9UMN"  # curious_coder/linkedin-jobs-scraper
RUN_SYNC = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"


def _size_from_employees(n) -> Optional[str]:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    return "micro" if n <= 10 else "small" if n <= 50 else "medium" if n <= 250 else "large"


def _jobs_url(role: str, location: str) -> str:
    q = quote(role.strip())
    loc = quote(location.strip()) if location else ""
    url = f"https://www.linkedin.com/jobs/search/?keywords={q}"
    if loc:
        url += f"&location={loc}"
    return url


def discover_jobs(role: str, city: str = "", country: str = "Ukraine",
                  limit: int = 25, timeout: int = 300) -> list[Company]:
    token = cfg("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN not set — needed for the Jobs source.")
    from .. import usage
    if not usage.allowed("apify"):
        raise RuntimeError("Apify budget exceeded for this month — raise APIFY_BUDGET_USD.")

    location = city or country
    payload = {"urls": [_jobs_url(role, location)], "scrapeCompany": True,
               "count": max(limit, 10)}
    r = requests.post(RUN_SYNC, params={"token": token}, json=payload, timeout=timeout)
    usage.record("apify")
    if r.status_code >= 400:
        raise RuntimeError(f"Apify Jobs run failed: HTTP {r.status_code} {r.text[:200]}")
    items = r.json()
    if isinstance(items, dict) and items.get("error"):
        raise RuntimeError(f"Apify Jobs error: {items['error']}")

    companies: list[Company] = []
    by_company: dict[str, Company] = {}
    for it in items:
        name = it.get("companyName")
        if not name:
            continue
        key = (it.get("companyWebsite") or name).lower()
        title = it.get("title")
        if key in by_company:  # same company hiring for several roles → merge titles
            roles = by_company[key].raw_tags["signals"].setdefault("hiring_for", [])
            if title and title not in roles:
                roles.append(title)
            continue

        poster = []
        if it.get("jobPosterName"):
            poster.append({
                "name": it["jobPosterName"], "role": it.get("jobPosterTitle") or "Hiring manager",
                "source_url": it.get("jobPosterProfileUrl"),
                "linkedin": it.get("jobPosterProfileUrl"), "instagram": None,
            })
        socials = {}
        if it.get("companyLinkedinUrl"):
            socials["linkedin"] = it["companyLinkedinUrl"]

        signals = {"hiring": True, "hiring_for": [title] if title else [],
                   "posted_at": it.get("postedAt"), "job_url": it.get("link")}
        enrichment = {
            "emails": [], "phones": [], "socials": socials, "telegram": [],
            "decision_makers": poster, "staff": [],
            "profile": {"size_band": _size_from_employees(it.get("companyEmployeesCount")),
                        "employees": str(it.get("companyEmployeesCount") or "") or None},
            "signals": signals, "linkedin_profiles": [], "pages_crawled": [], "source": "jobs",
        }
        addr = it.get("companyAddress")
        if isinstance(addr, dict):  # actor returns a structured address object
            addr = ", ".join(str(v) for v in (addr.get("streetAddress"), addr.get("addressLocality"),
                                              addr.get("addressCountry")) if v)
        c = Company(
            name=name, category=role, city=it.get("location") or location, country=country,
            website=it.get("companyWebsite"), phone=None,
            address=addr or it.get("location"), source="jobs",
            raw_tags={"size_band": enrichment["profile"]["size_band"],
                      "gmaps_category": (it.get("industries") or [None])[0] if isinstance(it.get("industries"), list) else it.get("industries"),
                      "employees": enrichment["profile"]["employees"],
                      "company_linkedin": it.get("companyLinkedinUrl"),
                      "signals": signals, "_enrichment": enrichment},
        )
        by_company[key] = c
        companies.append(c)
        if len(companies) >= limit:
            break
    return companies


if __name__ == "__main__":
    import sys
    role = sys.argv[1] if len(sys.argv) > 1 else "marketing manager"
    city = sys.argv[2] if len(sys.argv) > 2 else "Ukraine"
    res = discover_jobs(role, city, limit=10)
    print(f"Found {len(res)} hiring companies")
    for c in res:
        dm = c.raw_tags["_enrichment"]["decision_makers"]
        print("•", c.name[:30], "| hiring:", c.raw_tags["signals"]["hiring_for"][:2],
              "| poster:", (dm[0]["name"] if dm else "—"), "|", c.website or "")
