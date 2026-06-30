"""Shared search response packaging for sync + async paths."""
from __future__ import annotations

from .service import SearchResult, _lead_id, passes_filters, saved_ids


def package_search_result(result: SearchResult, filters: dict | None = None) -> dict:
    filters = filters or {}
    saved = set(saved_ids())
    decorated: list[dict] = []
    for lead in result.leads:
        row = lead.to_dict()
        lid = _lead_id(row)
        decorated.append({**row, "_id": lid, "_saved": lid in saved})
    if any(filters.values()):
        decorated = [row for row in decorated if passes_filters(row, **filters)]
    meta = {**result.meta, "after_filters": len(decorated)}
    return {"leads": decorated, "meta": meta}
