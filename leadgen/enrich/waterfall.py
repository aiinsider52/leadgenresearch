"""Waterfall contact enrichment — free crawl → Brave → Apify → optional Apollo/Hunter."""
from __future__ import annotations

from typing import Any

from ..config import get
from .. import usage
from ..enrich.site import enrich_site
from ..enrich.brave_people import enrich_people_brave
from ..enrich.contact_quality import assess_contacts
from ..identity import domain as identity_domain


def _has_contacts(enrichment: dict) -> bool:
    return bool(enrichment.get("emails") or enrichment.get("phones")
                or enrichment.get("decision_makers"))


def _apollo_enrich(company_name: str, domain: str | None) -> dict:
    key = get("APOLLO_API_KEY")
    if not key or not usage.allowed("apollo"):
        return {}
    import requests
    try:
        r = requests.post(
            "https://api.apollo.io/v1/organizations/enrich",
            headers={"Content-Type": "application/json", "Cache-Control": "no-cache"},
            params={"api_key": key},
            json={"domain": domain} if domain else {"name": company_name},
            timeout=25,
        )
        if r.status_code != 200:
            return {}
        usage.record("apollo", 0.05)
        org = r.json().get("organization") or {}
        emails = []
        if org.get("primary_domain"):
            pass  # Apollo doesn't give emails on org enrich free tier reliably
        people = []
        for p in (org.get("people") or [])[:3]:
            if p.get("email"):
                emails.append(p["email"])
            people.append({
                "name": p.get("name", ""),
                "role": p.get("title", ""),
                "email": p.get("email"),
                "linkedin": p.get("linkedin_url"),
            })
        return {"emails": emails, "decision_makers": people, "source": "apollo"}
    except Exception:
        return {}


def _hunter_enrich(domain: str) -> dict:
    key = get("HUNTER_API_KEY")
    if not key or not domain or not usage.allowed("hunter"):
        return {}
    import requests
    try:
        r = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": key, "limit": 5},
            timeout=20,
        )
        if r.status_code != 200:
            return {}
        usage.record("hunter", 0.02)
        emails = [e.get("value") for e in (r.json().get("data", {}).get("emails") or [])
                  if e.get("value")]
        return {"emails": emails, "source": "hunter"}
    except Exception:
        return {}


def waterfall_enrich(
    company_name: str,
    website: str | None,
    base_enrichment: dict | None = None,
    *,
    brave_people: bool = True,
) -> dict:
    """Cascade providers until we have contacts or exhaust budget."""
    out = dict(base_enrichment or {})
    dom = identity_domain(website) if website else None

    # Step 1: site crawl (caller may have done this already)
    if website and dom and not _has_contacts(out):
        try:
            crawled = enrich_site(website, max_pages=6).to_dict()
            out = {**out, **{k: v for k, v in crawled.items() if v}}
        except Exception:
            pass

    # Step 2: Brave people
    if brave_people and not _has_contacts(out) and usage.allowed("brave"):
        out = enrich_people_brave(out, company_name, website, search_lang="en")

    # Step 3: Hunter domain search
    if dom and not out.get("emails") and get("HUNTER_API_KEY"):
        hunter = _hunter_enrich(dom)
        if hunter.get("emails"):
            out["emails"] = list(dict.fromkeys((out.get("emails") or []) + hunter["emails"]))
            out.setdefault("sources", []).append("hunter")

    # Step 4: Apollo org enrich
    if not _has_contacts(out) and get("APOLLO_API_KEY"):
        apollo = _apollo_enrich(company_name, dom)
        if apollo.get("emails"):
            out["emails"] = list(dict.fromkeys((out.get("emails") or []) + apollo["emails"]))
        if apollo.get("decision_makers"):
            out["decision_makers"] = (out.get("decision_makers") or []) + apollo["decision_makers"]

    return assess_contacts(out, website)
