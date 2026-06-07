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
# Roles fanned out across one multi-term run to maximise C-level coverage.
# (No hyphens/punctuation — the actor rejects them inside a search term.)
PEOPLE_ROLES_EN = ["founder", "ceo", "cofounder", "owner", "managing director", "cmo"]
PEOPLE_ROLES_UK = ["засновник", "власник", "директор"]
# Characters the actor forbids inside a single search term.
_FORBIDDEN = re.compile(r"[!?.,:;\-+=*&%$#@/\\~^|<>()\[\]{}\"'`]")


def _sanitize_term(t: str) -> str:
    return re.sub(r"\s+", " ", _FORBIDDEN.sub(" ", t)).strip()


def _build_people_queries(category: str, city: str, max_terms: int = 16) -> list[str]:
    """Fan out role × niche-token × word-order variations (one Apify run takes
    them comma-separated). Instagram returns few personal accounts per exact
    query, so breadth of phrasings is what grows the union of real C-level."""
    cat = _sanitize_term(category)
    cty = _sanitize_term(city)
    # Niche tokens: whole phrase + individual words (e.g. marketing, agency).
    tokens = [cat] + [w for w in cat.split() if len(w) > 2]
    tokens = list(dict.fromkeys(tokens))[:3]
    roles = ["founder", "ceo", "owner", "засновник"]

    terms: list[str] = []
    for r in roles:
        for tok in tokens:
            terms.append(f"{r} {tok} {cty}".strip())   # role niche city
        terms.append(f"{r} {cty}".strip())             # role city (broad)
    # a few niche-first / no-city variants catch differently-ranked accounts
    terms.append(f"{cat} founder")
    terms.append(f"{cat} ceo {cty}".strip())

    terms = [_sanitize_term(t) for t in terms]
    return list(dict.fromkeys(t for t in terms if t))[:max_terms]


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
    if not rm:                       # must signal a role
        return None
    cm = COMPANY_HANDLE_RE.search(bio)
    person_full = _looks_like_person(full) and not GIMMICK_RE.search(full)
    # Addressable human name: a person-looking fullName, else a first_last handle.
    name = full if person_full else _humanize_username(username)
    if not name:                     # can't address them → skip
        return None
    role = re.sub(r"\s+", " ", rm.group(0)).strip()
    company = cm.group(1).strip(" .") if cm else None
    # Confidence: company @handle present = high; otherwise medium.
    confidence = "high" if cm else "medium"
    return {"name": name, "role": role, "company": company, "confidence": confidence}


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

    if mode == "people":
        # Fan out many role/niche variations in one comma-separated run.
        queries = _build_people_queries(category, city)
        term = ", ".join(queries)
        search_limit = 20  # per term → total pool ≈ terms × 20, then filtered
    else:
        term = f"{category} {city}".strip()
        search_limit = max(limit, 1)
    payload = {
        "search": term,
        "searchType": search_type,
        "searchLimit": search_limit,
        "enhanceUserSearchWithFacebookPage": True,  # adds email/FB to top results
    }
    r = requests.post(RUN_SYNC, params={"token": token}, json=payload, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"Apify IG run failed: HTTP {r.status_code} {r.text[:200]}")
    items = r.json()
    if isinstance(items, dict) and items.get("error"):
        raise RuntimeError(f"Apify IG error: {items['error']}")

    def _ctx(it):
        username = _first(it, "username", "ownerUsername")
        ig_url = it.get("url") or (f"https://instagram.com/{username}" if username else None)
        return username, ig_url, _to_enrichment(it, ig_url), \
            (_first(it, "externalUrl", "website") or ig_url), (it.get("businessAddress") or {})

    def build_person(it):
        username, ig_url, en, site, ba = _ctx(it)
        person = _extract_person(it, ig_url)
        if not person:
            return None, None
        en["decision_makers"] = [{
            "name": person["name"], "role": person["role"], "source_url": ig_url, "linkedin": None,
            "linkedin_search": f"https://www.linkedin.com/search/results/people/?keywords={quote(person['name'])}",
            "instagram": ig_url, "confidence": person.get("confidence", "medium"),
        }]
        key = (username or ig_url or person["name"]).lower()
        return key, Company(
            name=person["company"] or person["name"], category=category,
            city=ba.get("city_name") or city, country=country, website=site,
            phone=(en["phones"] or [None])[0], address=ba.get("city_name"), source="instagram",
            raw_tags={"size_band": en["profile"]["size_band"], "gmaps_category": en["profile"]["industry"],
                      "instagram": ig_url, "followers": _first(it, "followersCount", "followers"),
                      "person_role": person["role"], "lead_kind": "person", "_enrichment": en})

    def build_business(it):
        username, ig_url, en, site, ba = _ctx(it)
        name = _first(it, "fullName", "full_name", "name") or username
        if not name:
            return None, None
        return name.lower(), Company(
            name=name, category=category, city=ba.get("city_name") or city, country=country,
            website=site, phone=(en["phones"] or [None])[0],
            address=ba.get("city_name") or _first(it, "address", "addressStreet"), source="instagram",
            raw_tags={"size_band": en["profile"]["size_band"], "gmaps_category": en["profile"]["industry"],
                      "instagram": ig_url, "followers": _first(it, "followersCount", "followers"),
                      "verified": it.get("verified"), "lead_kind": "business", "_enrichment": en})

    # Niche tokens to keep the business fill on-topic (drops random global hits).
    niche_tokens = [w.lower() for w in re.split(r"\s+", category) if len(w) > 2]

    def _relevant(it) -> bool:
        if not niche_tokens:
            return True
        hay = " ".join(str(it.get(k, "")) for k in ("fullName", "biography", "businessCategoryName", "username")).lower()
        return any(tok in hay for tok in niche_tokens)

    seen: set[str] = set()
    if mode == "people":
        # People first (real C-level), then the remaining ON-TOPIC business
        # accounts — so a paid run isn't wasted on the ~half that are companies.
        people, biz = [], []
        for it in items:
            pk, pc = build_person(it)
            if pc and pk not in seen:
                seen.add(pk); people.append(pc); continue
            if not _relevant(it):
                continue
            bk, bc = build_business(it)
            if bc and bk not in seen:
                seen.add(bk); biz.append(bc)
        return (people + biz)[:limit]

    companies: list[Company] = []
    for it in items:
        if len(companies) >= limit:
            break
        bk, bc = build_business(it)
        if bc and bk not in seen:
            seen.add(bk); companies.append(bc)
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
