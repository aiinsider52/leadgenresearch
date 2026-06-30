"""Djinni.co job board — Ukrainian tech hiring signals (free scrape)."""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from .osm import Company

LISTING = "https://djinni.co/jobs/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; leadgen/0.1)",
    "Accept-Language": "uk,en;q=0.8",
}


def discover_djinni(role: str, city: str = "", country: str = "Ukraine",
                    limit: int = 25, timeout: int = 25) -> list[Company]:
    params = {"primary_keyword": role}
    if city:
        params["region"] = "UKR"
    try:
        r = requests.get(LISTING, params=params, headers=HEADERS, timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError(f"Djinni unreachable: {exc}")
    if r.status_code != 200:
        raise RuntimeError(f"Djinni HTTP {r.status_code}")

    soup = BeautifulSoup(r.text, "html.parser")
    companies: list[Company] = []
    by_name: dict[str, Company] = {}

    for card in soup.select("li.list-jobs__item, div.job-list-item"):
        title_el = card.select_one("a.job-list-item__link, a[href*='/jobs/']")
        comp_el = card.select_one("a[href*='/jobs/company/'], .job-list-item__company")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        name = comp_el.get_text(strip=True) if comp_el else title.split("—")[0].strip()
        if not name or len(name) < 2:
            continue
        job_url = title_el.get("href", "")
        if job_url and not job_url.startswith("http"):
            job_url = "https://djinni.co" + job_url

        key = name.lower()
        if key in by_name:
            roles = by_name[key].raw_tags["signals"].setdefault("hiring_for", [])
            if title not in roles:
                roles.append(title)
            continue

        signals = {"hiring": True, "hiring_for": [title], "job_url": job_url}
        enrichment = {
            "emails": [], "phones": [], "socials": {}, "signals": signals,
            "decision_makers": [], "staff": [], "source": "djinni",
        }
        c = Company(
            name=name, category=role, city=city or "Remote UA", country=country,
            website=None, source="djinni",
            raw_tags={"signals": signals, "_enrichment": enrichment},
        )
        by_name[key] = c
        companies.append(c)
        if len(companies) >= limit:
            break
    return companies
