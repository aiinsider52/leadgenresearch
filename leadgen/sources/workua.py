"""Work.ua job board — Ukrainian hiring signals."""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

from .osm import Company

BASE = "https://www.work.ua/ru/jobs/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; leadgen/0.1)", "Accept-Language": "uk"}


def discover_workua(role: str, city: str = "", country: str = "Ukraine",
                    limit: int = 25, timeout: int = 25) -> list[Company]:
    path = quote(role.replace(" ", "+"))
    url = f"{BASE}{path}/"
    if city:
        url += f"?city={quote(city)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError(f"Work.ua unreachable: {exc}")
    if r.status_code != 200:
        raise RuntimeError(f"Work.ua HTTP {r.status_code}")

    soup = BeautifulSoup(r.text, "html.parser")
    companies: list[Company] = []
    by_name: dict[str, Company] = {}

    for card in soup.select("div.card, article.card"):
        title_el = card.select_one("h2 a, a.link-hover")
        comp_el = card.select_one("span.add-top-xs span, .nowrap")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        # Work.ua often shows company in subtitle
        comp_span = card.select_one("span.strong-600, span[class*='company']")
        name = comp_span.get_text(strip=True) if comp_span else title
        job_url = title_el.get("href", "")
        if job_url and not job_url.startswith("http"):
            job_url = "https://www.work.ua" + job_url

        key = name.lower()
        if key in by_name:
            by_name[key].raw_tags["signals"].setdefault("hiring_for", []).append(title)
            continue

        signals = {"hiring": True, "hiring_for": [title], "job_url": job_url}
        enrichment = {"signals": signals, "emails": [], "phones": [], "decision_makers": []}
        c = Company(
            name=name, category=role, city=city or "", country=country,
            source="workua", raw_tags={"signals": signals, "_enrichment": enrichment},
        )
        by_name[key] = c
        companies.append(c)
        if len(companies) >= limit:
            break
    return companies
