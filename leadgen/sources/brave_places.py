"""Business discovery through Brave Place Search."""
from __future__ import annotations

from typing import Any, Optional

from ..brave import available, place_search
from ..identity import domain
from .apify_gmaps import resolve_country
from .osm import Company


def _first(item: dict, *keys):
    for key in keys:
        if item.get(key) not in (None, "", []):
            return item[key]
    return None


def _address(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return ", ".join(str(x) for x in value.values() if x) or None
    return None


def _coords(item: dict) -> tuple[float | None, float | None]:
    coords = item.get("coordinates") or item.get("location") or {}
    if isinstance(coords, dict):
        return _first(coords, "latitude", "lat"), _first(coords, "longitude", "lng", "lon")
    return None, None


def _category(item: dict) -> Optional[str]:
    cats = item.get("categories") or item.get("types") or item.get("category")
    if isinstance(cats, list):
        first = cats[0] if cats else None
        return first.get("name") if isinstance(first, dict) else first
    return str(cats) if cats else None


def discover_brave_places(category: str, city: str = "", country: str = "Ukraine",
                          limit: int = 50) -> list[Company]:
    if not available():
        raise RuntimeError("BRAVE_SEARCH_API_KEY not set (env or data/secrets.env).")
    code = resolve_country(country)
    items = place_search(category, location=f"{city} {country}".strip(), count=limit,
                         country=code if len(code) == 2 else "US")
    companies: list[Company] = []
    for item in items:
        name = _first(item, "name", "title")
        if not name:
            continue
        lat, lon = _coords(item)
        website = _first(item, "website", "url")
        phone = _first(item, "phone", "telephone")
        address = _address(_first(item, "address", "postal_address"))
        rating = _first(item, "rating", "stars")
        reviews = _first(item, "review_count", "reviews", "rating_count")
        place_id = _first(item, "id", "place_id", "provider_id")
        companies.append(Company(
            name=name, category=category, city=city, country=country,
            website=website if domain(website) else None, phone=phone,
            address=address, lat=lat, lon=lon, source="brave_places",
            raw_tags={"rating": rating, "reviews": reviews, "gmaps_category": _category(item),
                      "place_id": f"brave:{place_id}" if place_id else None,
                      "brave_place": item},
        ))
    return companies[:limit]
