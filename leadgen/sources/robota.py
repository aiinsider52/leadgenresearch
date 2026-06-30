"""Robota.ua job board — Ukrainian hiring signals."""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

from .osm import Company

SEARCH = "https://robota.ua/zapros/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; leadgen/0.1)", "Accept-Language": "uk"}


def discover_robota(role: str, city: str = "", country: str = "Ukraine",
                    limit: int = 25, timeout: int = 25) -> list[Company]:
    params = {"keyWords": role}
    if city:
        params["cityId"] = city  # Robota uses IDs; text search still works via keyWords
    try:
        r = requests.get(SEARCH, params=params, headers=HEADERS, timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError(f"Robota.ua unreachable: {exc}")
    if r.status_code != 200:
        raise RuntimeError(f"Robota.ua HTTP {r.status_code}")

    soup = BeautifulSoup(r.text, "html.parser")
    companies: list[Company] = []
    by_name: dict[str, Company] = {}

    for card in soup.select("div[data-id], article, div.vacancy"):
        title_el = card.select_one("a[href*='vacancy'], h2 a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        comp_el = card.select_one("a[href*='company'], span.company-name")
        name = comp_el.get_text(strip=True) if comp_el else title
        job_url = title_el.get("href", "")
        if job_url and not job_url.startswith("http"):
            job_url = "https://robota.ua" + job_url

        key = name.lower()
        if key in by_name:
            by_name[key].raw_tags["signals"].setdefault("hiring_for", []).append(title)
            continue

        signals = {"hiring": True, "hiring_for": [title], "job_url": job_url}
        enrichment = {"signals": signals, "emails": [], "phones": [], "decision_makers": []}
        c = Company(
            name=name, category=role, city=city or "", country=country,
            source="robota", raw_tags={"signals": signals, "_enrichment": enrichment},
        )
        by_name[key] = c
        companies.append(c)
        if len(companies) >= limit:
            break
    return companies
