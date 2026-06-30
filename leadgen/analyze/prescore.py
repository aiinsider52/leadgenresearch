"""Cheap pre-enrichment ranking used to spend deep-enrichment budget wisely."""
from __future__ import annotations


def pre_score(company: dict) -> dict:
    pts, reasons = 0, []

    def add(value: int, reason: str) -> None:
        nonlocal pts
        pts += value
        reasons.append(reason)

    if company.get("website"):
        add(25, "website")
    if company.get("phone"):
        add(12, "phone")
    if company.get("company_linkedin"):
        add(10, "company-linkedin")
    if company.get("instagram"):
        add(5, "instagram")
    rating, reviews = company.get("rating"), company.get("reviews")
    if isinstance(rating, (int, float)) and rating >= 4.0:
        add(8, "rating")
    if isinstance(reviews, int) and reviews >= 25:
        add(8, "reviews")
    if company.get("size_band") in ("small", "medium", "large"):
        add(12, "size")
    sources = company.get("sources") or [company.get("source")]
    if len([x for x in sources if x]) > 1:
        add(10, "multi-source")
    return {"score": min(100, pts), "reasons": reasons}
