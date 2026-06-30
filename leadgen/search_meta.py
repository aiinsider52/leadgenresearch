"""Honest limit metadata for search responses (ISS-003)."""
from __future__ import annotations


def cap_reason(
    requested_limit: int,
    returned: int,
    discovered_raw: int,
    deduped_before_enrichment: int,
) -> str | None:
    if returned >= requested_limit:
        return None
    if discovered_raw < requested_limit:
        return "source_exhausted"
    if deduped_before_enrichment < discovered_raw:
        return "dedupe_filter"
    return "pipeline_cap"


def build_limit_meta(
    *,
    requested_limit: int,
    returned: int,
    discovered_raw: int,
    deduped_before_enrichment: int,
    after_filters: int | None = None,
    source: str | None = None,
    cities: list[str] | None = None,
) -> dict:
    capped = returned < requested_limit
    reason = cap_reason(requested_limit, returned, discovered_raw, deduped_before_enrichment)
    meta = {
        "requested_limit": requested_limit,
        "returned": returned,
        "discovered_raw": discovered_raw,
        "deduped_before_enrichment": deduped_before_enrichment,
        "capped": capped,
        "cap_reason": reason,
    }
    if after_filters is not None:
        meta["after_filters"] = after_filters
    if source:
        meta["source"] = source
    if cities:
        meta["cities"] = cities
    return meta


def merge_multi_meta(parts: list[dict], requested_limit: int) -> dict:
    if not parts:
        return build_limit_meta(
            requested_limit=requested_limit,
            returned=0,
            discovered_raw=0,
            deduped_before_enrichment=0,
        )
    discovered = sum(p.get("discovered_raw", 0) for p in parts)
    deduped = sum(p.get("deduped_before_enrichment", 0) for p in parts)
    returned = parts[-1].get("returned", 0)
    return build_limit_meta(
        requested_limit=requested_limit,
        returned=returned,
        discovered_raw=discovered,
        deduped_before_enrichment=deduped,
        source=parts[0].get("source"),
        cities=parts[0].get("cities"),
    )
