"""Instagram discovery via the Apify actor `apify/instagram-search-scraper`.

Strong for IG-native niches (agencies, beauty, coaches, e-commerce) where the
account is often a personal brand — so full_name is frequently the founder and
the FB-enhanced result carries a direct email.

searchType="user"  → accounts matching a keyword (people + business profiles)
searchType="place" → business locations

Needs an Apify token (env APIFY_TOKEN or data/secrets.env). Honest limits:
Instagram is NOT a corporate directory — it won't reliably map "the CEO of
company X". It finds IG-native businesses and personal-brand founders by keyword.
"""
from __future__ import annotations

import re
from typing import Optional

import requests

from ..config import get as cfg
from .osm import Company

ACTOR = "apify~instagram-search-scraper"
RUN_SYNC = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"

ROLE_RE = re.compile(r"\b(CEO|Founder|Co-?founder|Owner|Director|CMO|CTO|засновник|власник|директор|керівник|основатель|владелец)\b", re.I)


def _first(d: dict, *keys):
    for k in keys:
        if d.get(k):
            return d[k]
    return None


def _looks_like_person(name: str) -> bool:
    parts = [p for p in name.split() if len(p) > 1]
    return 2 <= len(parts) <= 3 and not any(ch.isdigit() for ch in name)


def _size_from_followers(n) -> Optional[str]:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    return "micro" if n < 2000 else "small" if n < 20000 else "medium" if n < 100000 else "large"


def _clean_category(raw) -> Optional[str]:
    if not raw:
        return None
    parts = [p.strip() for p in str(raw).split(",") if p.strip() and p.strip().lower() != "none"]
    return parts[-1] if parts else None


def _to_enrichment(item: dict, ig_url: Optional[str]) -> dict:
    email = _first(item, "email", "publicEmail", "businessEmail")
    phone = _first(item, "phone", "publicPhoneNumber", "businessPhoneNumber")
    full = _first(item, "fullName", "full_name", "name") or ""
    bio = _first(item, "biography", "bio") or ""
    socials = {}
    if ig_url:
        socials["instagram"] = ig_url
    if item.get("facebookPage"):
        socials["facebook"] = item["facebookPage"]

    # Only treat as a decision-maker when there's an explicit role mention
    # (CEO/Founder/Owner) — IG fullName is usually the brand, not a person.
    dms = []
    role_m = ROLE_RE.search(bio) or ROLE_RE.search(full)
    if role_m and full and _looks_like_person(full):
        dms.append({"name": full, "role": role_m.group(0), "source_url": ig_url})
    return {
        "emails": [email] if email else [],
        "phones": [phone] if phone else [],
        "socials": socials,
        "telegram": [],
        "decision_makers": dms,
        "staff": [],
        "profile": {"size_band": _size_from_followers(_first(item, "followersCount", "followers")),
                    "industry": _clean_category(item.get("businessCategoryName"))},
        "signals": {},
        "linkedin_profiles": [],
        "pages_crawled": [],
        "source": "instagram",
    }


def discover_instagram(
    category: str,
    city: str = "",
    country: str = "Ukraine",
    limit: int = 25,
    search_type: str = "user",
    timeout: int = 240,
) -> list[Company]:
    token = cfg("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN not set (env or data/secrets.env) — needed for Instagram source.")

    term = f"{category} {city}".strip()
    payload = {
        "search": term,
        "searchType": search_type,
        "searchLimit": max(limit, 1),
        "enhanceUserSearchWithFacebookPage": True,  # adds email/FB to top-10
    }
    r = requests.post(RUN_SYNC, params={"token": token}, json=payload, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"Apify IG run failed: HTTP {r.status_code} {r.text[:200]}")
    items = r.json()
    if isinstance(items, dict) and items.get("error"):
        raise RuntimeError(f"Apify IG error: {items['error']}")

    companies: list[Company] = []
    seen: set[str] = set()
    for it in items[:limit]:
        username = _first(it, "username", "ownerUsername")
        name = _first(it, "fullName", "full_name", "name") or username
        if not name or name in seen:
            continue
        seen.add(name)
        ig_url = it.get("url") or (f"https://instagram.com/{username}" if username else None)
        en = _to_enrichment(it, ig_url)
        # Real website (externalUrl) drives enrichment → email/decision-makers
        # come from the actual site. Fall back to the IG profile if no site.
        site = _first(it, "externalUrl", "website") or ig_url
        ba = it.get("businessAddress") or {}
        companies.append(Company(
            name=name, category=category,
            city=ba.get("city_name") or city, country=country,
            website=site,
            phone=(en["phones"] or [None])[0],
            address=ba.get("city_name") or _first(it, "address", "addressStreet"),
            source="instagram",
            raw_tags={
                "size_band": en["profile"]["size_band"],
                "gmaps_category": en["profile"]["industry"],
                "instagram": ig_url,
                "followers": _first(it, "followersCount", "followers"),
                "verified": it.get("verified"),
                "_enrichment": en,
            },
        ))
    return companies


if __name__ == "__main__":
    import json
    import sys
    cat = sys.argv[1] if len(sys.argv) > 1 else "marketing agency"
    city = sys.argv[2] if len(sys.argv) > 2 else "Kyiv"
    try:
        res = discover_instagram(cat, city, limit=8)
        print(f"Found {len(res)}")
        for c in res:
            en = c.raw_tags["_enrichment"]
            print("•", c.name, "|", c.raw_tags.get("followers"), "foll |",
                  en["emails"], "| DM:", [d["name"] for d in en["decision_makers"]])
    except RuntimeError as e:
        print("NEEDS TOKEN:", e)
