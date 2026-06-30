"""Company identity and early cross-source deduplication."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, Optional
from urllib.parse import urlparse

from .sources.osm import Company

NON_COMPANY_DOMAINS = {
    "instagram.com", "t.me", "telegram.me", "facebook.com", "fb.com",
    "linktr.ee", "linkedin.com", "youtube.com", "tiktok.com", "expz.link",
}
LEGAL_WORDS = {
    "llc", "ltd", "inc", "gmbh", "ag", "sa", "sarl", "company", "co",
    "тов", "тзов", "ооо", "фоп", "пп", "group", "група", "группа",
}


def domain(url: object) -> Optional[str]:
    if not url:
        return None
    raw = str(url).strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    host = urlparse(raw).netloc.lower().split("@")[-1].split(":")[0]
    host = host[4:] if host.startswith("www.") else host
    return host or None


def normalize_phone(phone: object) -> Optional[str]:
    digits = re.sub(r"\D", "", str(phone or ""))
    return digits[-10:] if len(digits) >= 10 else None


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    words = re.findall(r"[a-zа-яёіїєґ0-9]+", text)
    return " ".join(w for w in words if w not in LEGAL_WORDS)


def company_keys(company: Company | dict) -> set[str]:
    get = company.get if isinstance(company, dict) else lambda k, d=None: getattr(company, k, d)
    keys: set[str] = set()
    d = domain(get("website"))
    if d and d not in NON_COMPANY_DOMAINS:
        keys.add("d:" + d)
    phone = normalize_phone(get("phone"))
    if phone:
        keys.add("p:" + phone)
    raw = get("raw_tags", {}) or {}
    place_id = raw.get("place_id") or raw.get("google_place_id")
    if place_id:
        keys.add("g:" + str(place_id))
    name, city = normalize_text(get("name")), normalize_text(get("city"))
    if name:
        keys.add(f"n:{name}|{city}")
    return keys


def _same_company(a: Company, b: Company) -> bool:
    if company_keys(a) & company_keys(b):
        return True
    an, bn = normalize_text(a.name), normalize_text(b.name)
    if not an or not bn:
        return False
    city_match = not a.city or not b.city or normalize_text(a.city) == normalize_text(b.city)
    return city_match and SequenceMatcher(None, an, bn).ratio() >= 0.92


def _merge_lists(a: list, b: list) -> list:
    return list(dict.fromkeys((a or []) + (b or [])))


def _merge_prebuilt(a: dict, b: dict) -> dict:
    out = dict(a or {})
    for key in ("emails", "phones", "telegram", "linkedin_profiles", "pages_crawled"):
        out[key] = _merge_lists(out.get(key, []), (b or {}).get(key, []))
    out["socials"] = {**((b or {}).get("socials") or {}), **(out.get("socials") or {})}
    out["signals"] = {**(out.get("signals") or {}), **((b or {}).get("signals") or {})}
    for key in ("decision_makers", "staff"):
        people, seen = [], set()
        for person in (out.get(key) or []) + ((b or {}).get(key) or []):
            pid = normalize_text(person.get("name"))
            if pid and pid not in seen:
                seen.add(pid)
                people.append(person)
        out[key] = people
    profile = dict(out.get("profile") or {})
    for key, value in ((b or {}).get("profile") or {}).items():
        if value and not profile.get(key):
            profile[key] = value
    out["profile"] = profile
    return out


def merge_companies(a: Company, b: Company) -> Company:
    """Merge richer fields and source metadata into first Company."""
    for field in ("website", "phone", "address", "lat", "lon", "osm_id"):
        if not getattr(a, field) and getattr(b, field):
            setattr(a, field, getattr(b, field))
    sources = set(a.raw_tags.get("_sources", [])) | set(b.raw_tags.get("_sources", []))
    sources.update(x for x in (a.source, b.source) if x)
    a.raw_tags["_sources"] = sorted(sources)
    for key, value in b.raw_tags.items():
        if key == "_enrichment":
            a.raw_tags[key] = _merge_prebuilt(a.raw_tags.get(key, {}), value)
        elif value and not a.raw_tags.get(key):
            a.raw_tags[key] = value
    return a


def dedupe_companies(companies: Iterable[Company]) -> list[Company]:
    out: list[Company] = []
    key_index: dict[str, Company] = {}
    for company in companies:
        company.raw_tags.setdefault("_sources", [company.source])
        match = next((key_index[k] for k in company_keys(company) if k in key_index), None)
        if match is None:
            match = next((x for x in out if _same_company(x, company)), None)
        if match is not None:
            merge_companies(match, company)
            for key in company_keys(match):
                key_index[key] = match
            continue
        out.append(company)
        for key in company_keys(company):
            key_index[key] = company
    return out
