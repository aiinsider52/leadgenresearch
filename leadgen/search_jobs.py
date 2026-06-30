"""Async search job execution (ISS-004) — params mirror sync app routes."""
from __future__ import annotations

from typing import Any

from . import search_guard
from .i18n import LANGS
from .service import (
    SearchResult,
    UA_MAJOR_CITIES,
    find_leads,
    find_leads_around,
    find_leads_expanded,
    find_leads_multi,
)


def _category(params: dict) -> str:
    if "category" in params:
        return params["category"]
    return params.get("category_label", "")


def _lang(params: dict) -> str:
    lang = params.get("lang", "uk")
    return lang if lang in LANGS else "uk"


def run_search(endpoint: str, params: dict) -> SearchResult:
    """Run a search endpoint inside a worker — same args as sync /api/find* handlers."""
    p = dict(params)
    search_seq = p.pop("search_seq", None)
    if search_seq is not None:
        search_guard.register_search(search_seq)
    p.pop("filters", None)
    category = _category(p)
    lang = _lang(p)

    if endpoint == "find":
        return find_leads(
            category,
            p.get("city", ""),
            country=p.get("country", "Ukraine"),
            limit=p.get("limit", 20),
            lang=lang,
            enrich=p.get("enrich", True),
            require_website=p.get("require_website", False),
            source=p.get("source", "osm"),
            ig_mode=p.get("ig_mode", "business"),
            discover_websites=p.get("discover_websites", True),
            brave_people=p.get("brave_people", True),
            brave_news=p.get("brave_news", True),
            brave_intent=p.get("brave_intent", True),
            search_seq=search_seq,
        )
    if endpoint == "find_around":
        return find_leads_around(
            category,
            p["lat"],
            p["lon"],
            radius_m=p.get("radius_m", 2000),
            limit=p.get("limit", 20),
            lang=lang,
            enrich=p.get("enrich", True),
            require_website=p.get("require_website", False),
            search_seq=search_seq,
        )
    if endpoint == "find_multi":
        cities = p.get("cities") or UA_MAJOR_CITIES
        return find_leads_multi(
            category,
            cities,
            country=p.get("country", "Ukraine"),
            limit=p.get("limit", 30),
            lang=lang,
            enrich=p.get("enrich", True),
            source=p.get("source", "osm"),
            ig_mode=p.get("ig_mode", "business"),
            discover_websites=p.get("discover_websites", True),
            brave_people=p.get("brave_people", True),
            brave_news=p.get("brave_news", True),
            brave_intent=p.get("brave_intent", True),
            search_seq=search_seq,
        )
    if endpoint == "find_expanded":
        return find_leads_expanded(
            category,
            p.get("city", ""),
            country=p.get("country", "Ukraine"),
            limit=p.get("limit", 40),
            lang=lang,
            enrich=p.get("enrich", True),
            source=p.get("source", "osm"),
            ig_mode=p.get("ig_mode", "business"),
            cities=p.get("cities") or None,
            discover_websites=p.get("discover_websites", True),
            brave_people=p.get("brave_people", True),
            brave_news=p.get("brave_news", True),
            brave_intent=p.get("brave_intent", True),
            search_seq=search_seq,
        )
    raise ValueError(f"unknown search endpoint: {endpoint}")


def package_result(result: SearchResult, decorated_leads: list[dict], meta: dict) -> dict[str, Any]:
    return {"leads": decorated_leads, "meta": meta}
