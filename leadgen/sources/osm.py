"""Geo company discovery via OpenStreetMap Overpass API.

Free, no API key, works worldwide incl. Ukraine. You pass a business
category + city, and get back companies with website/phone/address, which
then flow into enrich/ and catalog/.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import requests

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Overpass returns 406 without a real User-Agent.
HEADERS = {"User-Agent": "leadgen/0.1 (+https://github.com/leadgen)"}

# Business category -> OSM tag filters. Keys are language-neutral slugs;
# the i18n layer maps localized labels to these.
CATEGORY_TAGS: dict[str, list[str]] = {
    "restaurant": ['amenity~"restaurant|cafe|fast_food|bar"'],
    "dental": ['amenity="dentist"', 'healthcare="dentist"'],
    "clinic": ['amenity~"clinic|doctors|hospital"', 'healthcare~"clinic|doctor"'],
    "beauty": ['shop~"beauty|hairdresser|massage"', 'leisure="spa"'],
    "fitness": ['leisure~"fitness_centre|sports_centre"'],
    "law": ['office="lawyer"'],
    "real_estate": ['office="estate_agent"'],
    "auto": ['shop~"car|car_repair|tyres"'],
    "hotel": ['tourism~"hotel|guest_house|hostel"'],
    "retail": ['shop~"clothes|shoes|jewelry|gift|furniture"'],
    "agency": ['office~"advertising_agency|company|it|consulting"'],
    "construction": ['craft~"builder|carpenter|electrician|plumber"', 'office="construction_company"'],
    "education": ['amenity~"school|language_school|college"', 'office="educational_institution"'],
}


@dataclass
class Company:
    name: str
    category: str
    city: str
    country: str
    website: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    osm_id: Optional[str] = None
    source: str = "osm"
    raw_tags: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "raw_tags"}
        # Surface useful gmaps metadata (rating/reviews/size) for the UI.
        for key in ("rating", "reviews", "size_band", "gmaps_category"):
            if key in self.raw_tags and self.raw_tags[key] is not None:
                d[key] = self.raw_tags[key]
        return d


def _build_query(category: str, city: str, country: Optional[str], limit: int) -> str:
    filters = CATEGORY_TAGS.get(category)
    if not filters:
        raise ValueError(f"Unknown category '{category}'. Known: {', '.join(CATEGORY_TAGS)}")

    area = f'area["name"="{city}"]["boundary"="administrative"]->.searchArea;'
    blocks = []
    for f in filters:
        for kind in ("node", "way"):
            blocks.append(f'{kind}[{f}](area.searchArea);')
    body = "\n".join(blocks)
    return f"""[out:json][timeout:60];
{area}
(
{body}
);
out tags center {limit};"""


def _address(tags: dict) -> Optional[str]:
    street = tags.get("addr:street")
    num = tags.get("addr:housenumber")
    city = tags.get("addr:city")
    parts = [p for p in [f"{street} {num}".strip() if street else None, city] if p]
    return ", ".join(parts) or None


def _category_filters(category: str) -> list[str]:
    filters = CATEGORY_TAGS.get(category)
    if not filters:
        raise ValueError(f"Unknown category '{category}'. Known: {', '.join(CATEGORY_TAGS)}")
    return filters


def _overpass(query: str) -> dict:
    """POST a query to Overpass with retries across mirrors. Returns JSON."""
    last_err = None
    attempts = [(ep, wait) for wait in (0, 3, 8) for ep in OVERPASS_ENDPOINTS]
    for endpoint, wait in attempts:
        if wait:
            time.sleep(wait)
        try:
            r = requests.post(endpoint, data={"data": query}, headers=HEADERS, timeout=60)
            if r.status_code == 200:
                return r.json()
            last_err = f"HTTP {r.status_code} ({endpoint})"
        except requests.RequestException as exc:
            last_err = f"{type(exc).__name__} ({endpoint})"
    raise RuntimeError(f"Overpass unreachable after {len(attempts)} attempts: {last_err}")


def _parse(data: dict, category: str, city: str, country: str, require_website: bool) -> list[Company]:
    companies: list[Company] = []
    seen: set[str] = set()
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:uk") or tags.get("name:en")
        if not name or name in seen:
            continue
        website = tags.get("website") or tags.get("contact:website") or tags.get("url")
        if require_website and not website:
            continue
        seen.add(name)
        center = el.get("center", {})
        companies.append(
            Company(
                name=name,
                category=category,
                city=city,
                country=country or "",
                website=website,
                phone=tags.get("phone") or tags.get("contact:phone"),
                address=_address(tags),
                lat=el.get("lat") or center.get("lat"),
                lon=el.get("lon") or center.get("lon"),
                osm_id=f"{el.get('type')}/{el.get('id')}",
                raw_tags=tags,
            )
        )
    return companies


def discover(
    category: str,
    city: str,
    country: Optional[str] = "Ukraine",
    limit: int = 50,
    require_website: bool = False,
) -> list[Company]:
    """Discover companies of `category` in `city`. Free, no key."""
    data = _overpass(_build_query(category, city, country, limit))
    return _parse(data, category, city, country or "", require_website)


def discover_around(
    category: str,
    lat: float,
    lon: float,
    radius_m: int = 2000,
    limit: int = 50,
    require_website: bool = False,
) -> list[Company]:
    """Discover companies of `category` within `radius_m` of a map point.

    Powers the dashboard mini-map: the user clicks a location and we search
    a radius around it. Faster/more reliable than area-name lookup.
    """
    blocks = []
    for f in _category_filters(category):
        for kind in ("node", "way"):
            blocks.append(f"{kind}[{f}](around:{radius_m},{lat},{lon});")
    query = "[out:json][timeout:60];\n(\n" + "\n".join(blocks) + f"\n);\nout tags center {limit};"
    data = _overpass(query)
    label = f"{lat:.4f},{lon:.4f}"
    return _parse(data, category, label, "", require_website)


if __name__ == "__main__":
    import json
    import sys

    cat = sys.argv[1] if len(sys.argv) > 1 else "restaurant"
    town = sys.argv[2] if len(sys.argv) > 2 else "Львів"
    res = discover(cat, town, limit=15)
    print(f"Found {len(res)} '{cat}' in {town}")
    print(json.dumps([c.to_dict() for c in res[:10]], indent=2, ensure_ascii=False))
