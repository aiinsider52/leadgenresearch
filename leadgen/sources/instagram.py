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
from urllib.parse import quote

import requests

from ..config import get as cfg
from .osm import Company

ACTOR = "apify~instagram-search-scraper"
RUN_SYNC = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"

ROLE_RE = re.compile(r"\b(Co-?founder(?:\s*(?:&|and|/|\+)\s*CEO)?|Founder(?:\s*(?:&|and|/|\+)\s*CEO)?|CEO|Owner|Managing Director|Director|CMO|CTO|COO|засновни(?:к|ця)|власни(?:к|ця)|директор|керівни(?:к|ця)|основатель|владелец)\b", re.I)
# The company a person leads, mentioned in bio as an @handle: "CEO at @acme".
COMPANY_HANDLE_RE = re.compile(r"(?:at|of|@|в|у)\s*@([A-Za-z0-9_.]{3,30})", re.I)
# Role-gimmick accounts ("ceomindset", "founder.life") — not real operators.
GIMMICK_RE = re.compile(r"(ceo|founder|owner|director)", re.I)
# "founder" alone surfaces real personal accounts best (tested).
PEOPLE_TERMS = "founder"


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


def _humanize_username(username: str) -> Optional[str]:
    """'katrin_trofimova__' -> 'Katrin Trofimova'. None if it doesn't look
    like a personal handle (no separators / too long)."""
    base = re.sub(r"\d+", "", username).strip("._")
    parts = [p for p in re.split(r"[._]+", base) if len(p) > 1]
    if not (2 <= len(parts) <= 3):
        return None
    if any(GIMMICK_RE.fullmatch(p) for p in parts):
        return None
    return " ".join(p.capitalize() for p in parts)


def _extract_person(item: dict, ig_url):
    """Pull (name, role, company) only when the account is plausibly a real
    operator: a role keyword AND a company @handle in the bio. Returns None
    otherwise (filters out gimmick/influencer accounts)."""
    full = _first(item, "fullName", "full_name") or ""
    username = item.get("username") or ""
    bio = _first(item, "biography", "bio") or ""

    # Drop role-gimmick handles like "ceomindset", "founder.life".
    if GIMMICK_RE.search(username.split("_")[0].split(".")[0]):
        return None

    hay = f"{full} | {bio}"
    rm = ROLE_RE.search(hay)
    if not rm:
        return None
    cm = COMPANY_HANDLE_RE.search(bio)
    person_full = _looks_like_person(full) and not GIMMICK_RE.search(full)
    # Accept if we have a concrete company @handle OR a clear human full name.
    if not cm and not person_full:
        return None
    role = re.sub(r"\s+", " ", rm.group(0)).strip()
    company = cm.group(1).strip(" .") if cm else None
    name = full if person_full else _humanize_username(username)
    if not name:
        return None
    return {"name": name, "role": role, "company": company}


def discover_instagram(
    category: str,
    city: str = "",
    country: str = "Ukraine",
    limit: int = 25,
    search_type: str = "user",
    mode: str = "business",   # "business" = accounts; "people" = C-level persons
    timeout: int = 240,
) -> list[Company]:
    token = cfg("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN not set (env or data/secrets.env) — needed for Instagram source.")

    term = f"{category} {city}".strip()
    if mode == "people":  # bias the search toward founder/CEO personal accounts
        term = f"{PEOPLE_TERMS} {term}".strip()
    payload = {
        "search": term,
        "searchType": search_type,
        "searchLimit": max(limit * 2 if mode == "people" else limit, 1),  # over-fetch, filter
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
    for it in items:
        if len(companies) >= limit:
            break
        username = _first(it, "username", "ownerUsername")
        ig_url = it.get("url") or (f"https://instagram.com/{username}" if username else None)
        en = _to_enrichment(it, ig_url)
        site = _first(it, "externalUrl", "website") or ig_url
        ba = it.get("businessAddress") or {}

        if mode == "people":
            person = _extract_person(it, ig_url)
            if not person:          # keep only real C-level/people accounts
                continue
            # The lead is the company they lead (or their personal brand).
            lead_name = person["company"] or person["name"]
            if lead_name in seen:
                continue
            seen.add(lead_name)
            en["decision_makers"] = [{
                "name": person["name"], "role": person["role"],
                "source_url": ig_url, "linkedin": None,
                "linkedin_search": f"https://www.linkedin.com/search/results/people/?keywords={quote(person['name'])}",
                "instagram": ig_url,
            }]
            companies.append(Company(
                name=lead_name, category=category,
                city=ba.get("city_name") or city, country=country,
                website=site, phone=(en["phones"] or [None])[0],
                address=ba.get("city_name"), source="instagram",
                raw_tags={"size_band": en["profile"]["size_band"], "gmaps_category": en["profile"]["industry"],
                          "instagram": ig_url, "followers": _first(it, "followersCount", "followers"),
                          "person_role": person["role"], "_enrichment": en},
            ))
            continue

        # --- business mode ---
        name = _first(it, "fullName", "full_name", "name") or username
        if not name or name in seen:
            continue
        seen.add(name)
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
