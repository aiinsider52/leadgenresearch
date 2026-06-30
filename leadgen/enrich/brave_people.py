"""Find public decision-makers through Brave web search."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from ..brave import web_search
from ..identity import normalize_text
from .linkedin import enrich_people
from .people import EXEC_RE

BAD_NAME_WORDS = {
    "ceo", "founder", "owner", "director", "chief", "executive", "managing",
    "president", "partner", "head", "vice", "cmo", "cto", "coo", "cro", "cfo",
    "leadership", "team", "company", "profile", "official", "linkedin",
    "and", "at", "of", "leads", "керівник", "директор", "засновник",
}

NAME_ROLE_RE = re.compile(
    r"([A-ZА-ЯІЇЄҐ][A-Za-zА-Яа-яІіЇїЄєҐґ'’.\-]+(?:\s+[A-ZА-ЯІЇЄҐ][A-Za-zА-Яа-яІіЇїЄєҐґ'’.\-]+){1,3})"
    r".{0,80}?\b(founder|co-?founder|owner|ceo|chief executive|managing director|director|"
    r"president|partner|vp|vice president|head of|cmo|cto|coo|cro|cfo|"
    r"geschäftsführer|inhaber|засновник|власник|директор|керівник|партнер|основатель|владелец|руководитель)\b",
    re.I,
)
ROLE_NAME_RE = re.compile(
    r"\b(founder|co-?founder|owner|ceo|chief executive|managing director|director|"
    r"president|partner|vp|vice president|head of|cmo|cto|coo|cro|cfo|"
    r"geschäftsführer|inhaber|засновник|власник|директор|керівник|партнер|основатель|владелец|руководитель)\b"
    r".{0,50}?([A-ZА-ЯІЇЄҐ][A-Za-zА-Яа-яІіЇїЄєҐґ'’.\-]+(?:\s+[A-ZА-ЯІЇЄҐ][A-Za-zА-Яа-яІіЇїЄєҐґ'’.\-]+){1,3})",
    re.I,
)


def _text(result: dict) -> str:
    return " ".join(str(x) for x in (
        result.get("title"), result.get("description"), *(result.get("extra_snippets") or [])
    ) if x)


def _valid_name(name: str, company_name: str) -> bool:
    parts = name.split()
    low = {normalize_text(x) for x in parts}
    title_case = all(p[:1].isupper() for p in parts)
    return (
        2 <= len(parts) <= 4
        and title_case
        and not low & BAD_NAME_WORDS
        and normalize_text(name) != normalize_text(company_name)
        and normalize_text(company_name) not in normalize_text(name)
    )


def _people_from_results(results: list[dict], company_name: str) -> list[dict]:
    people, seen = [], set()
    company_norm = normalize_text(company_name)
    for result in results:
        text, url = _text(result), result.get("url")
        if company_norm and company_norm not in normalize_text(text):
            continue
        candidates = [(m.group(1), m.group(2)) for m in NAME_ROLE_RE.finditer(text)]
        candidates += [(m.group(2), m.group(1)) for m in ROLE_NAME_RE.finditer(text)]
        for name, role in candidates:
            name = re.sub(r"\s+", " ", name).strip(" -|,.:")
            if not _valid_name(name, company_name):
                continue
            key = normalize_text(name)
            if key in seen:
                continue
            seen.add(key)
            host = urlparse(url or "").netloc.lower()
            people.append({
                "name": name, "role": role, "source_url": url,
                "linkedin": url if "linkedin.com/in/" in (url or "") else None,
                "confidence": "high" if "linkedin.com/in/" in (url or "") else "medium",
                "source": "brave_web", "source_domain": host,
            })
    return people


def enrich_people_brave(enrichment: dict, company_name: str, website: str | None = None,
                        country: str = "ALL", search_lang: str = "en",
                        max_queries: int = 4) -> dict:
    if enrichment.get("decision_makers"):
        return enrichment
    queries = [
        f'"{company_name}" founder CEO owner director head',
        f'site:linkedin.com/in "{company_name}" founder OR CEO OR owner OR director',
        f'"{company_name}" interview founder',
    ]
    if website:
        host = urlparse(website).netloc.removeprefix("www.")
        queries.insert(0, f"site:{host} founder OR CEO OR owner OR director OR team")
    people: list[dict] = []
    for query in queries[:max_queries]:
        try:
            people.extend(_people_from_results(
                web_search(query, count=10, country=country, search_lang=search_lang), company_name
            ))
        except Exception:
            continue
    by_name = {}
    for person in people:
        by_name.setdefault(normalize_text(person["name"]), person)
    dms = list(by_name.values())[:6]
    enrich_people(dms, company_name, enrichment.get("linkedin_profiles") or [])
    enrichment["decision_makers"] = dms
    return enrichment
