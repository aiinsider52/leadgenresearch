"""DOU.ua hiring-signal source — Ukrainian job board, free, no API.

Each vacancy = a Ukrainian company actively hiring for a role (buying signal
for the 'instead of hiring, automate it' pitch). DOU exposes company name +
role + city (not the company site/contact), so these are breadth leads: they
fill the database and get enriched when the same company appears in OSM/Maps/IG
(cross-source merge), or you can pitch via the role.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .osm import Company

LISTING = "https://jobs.dou.ua/vacancies/"
HEADERS = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
           "Accept-Language": "uk,en;q=0.8"}


def discover_dou(role: str, city: str = "", country: str = "Ukraine",
                 limit: int = 25, timeout: int = 25) -> list[Company]:
    params = {"search": role}
    if city:
        params["city"] = city
    try:
        r = requests.get(LISTING, params=params, headers=HEADERS, timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError(f"DOU unreachable: {exc}")
    if r.status_code != 200:
        raise RuntimeError(f"DOU HTTP {r.status_code}")

    soup = BeautifulSoup(r.text, "html.parser")
    companies: list[Company] = []
    by_company: dict[str, Company] = {}
    for card in soup.select("li.l-vacancy"):
        title_el = card.select_one("a.vt")
        comp_el = card.select_one("a.company")
        if not comp_el:
            continue
        name = comp_el.get_text(strip=True)
        title = title_el.get_text(strip=True) if title_el else None
        job_url = title_el.get("href") if title_el else comp_el.get("href")
        cities = card.select_one(".cities")
        loc = cities.get_text(strip=True) if cities else city

        key = name.lower()
        if key in by_company:  # same company, several roles → merge titles
            roles = by_company[key].raw_tags["signals"].setdefault("hiring_for", [])
            if title and title not in roles:
                roles.append(title)
            continue

        signals = {"hiring": True, "hiring_for": [title] if title else [], "job_url": job_url}
        enrichment = {
            "emails": [], "phones": [], "socials": {}, "telegram": [],
            "decision_makers": [], "staff": [], "profile": {}, "signals": signals,
            "linkedin_profiles": [], "pages_crawled": [], "source": "dou",
        }
        c = Company(name=name, category=role, city=loc or city, country=country,
                    website=None, phone=None, address=loc, source="dou",
                    raw_tags={"signals": signals, "dou_url": job_url, "_enrichment": enrichment})
        by_company[key] = c
        companies.append(c)
        if len(companies) >= limit:
            break
    return companies


if __name__ == "__main__":
    import sys
    role = sys.argv[1] if len(sys.argv) > 1 else "marketing"
    city = sys.argv[2] if len(sys.argv) > 2 else ""
    res = discover_dou(role, city, limit=20)
    print(f"Found {len(res)} hiring companies on DOU")
    for c in res:
        print("•", c.name[:30], "| hiring:", c.raw_tags["signals"]["hiring_for"][:2], "|", c.city)
