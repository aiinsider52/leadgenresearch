"""Deterministic lead scoring 0-100 — no API key needed.

Turns the signals we already collect (contacts, size, rating, hiring) into a
single priority number + tier so the dashboard can sort "who to contact first".
Claude can refine this later, but this works offline and is the sane default.
"""
from __future__ import annotations

SIZE_POINTS = {"large": 18, "medium": 14, "small": 9, "micro": 4}


def score_lead(company: dict, enrichment: dict) -> dict:
    """Return {'score': int 0-100, 'tier': hot|warm|cold, 'reasons': [...]}."""
    pts = 0
    reasons: list[str] = []
    en = enrichment or {}
    socials = en.get("socials", {}) or {}
    prof = en.get("profile", {}) or {}
    sig = en.get("signals", {}) or {}

    def add(n, label):
        nonlocal pts
        pts += n
        reasons.append(label)

    # Reachability — can we actually contact them?
    if en.get("emails"):
        add(22, "email")
    if en.get("phones"):
        add(8, "phone")
    if en.get("decision_makers"):
        add(20, "decision-maker")
    if socials.get("linkedin"):
        add(8, "LinkedIn")
    if en.get("telegram"):
        add(6, "Telegram")

    # Quality / maturity.
    band = prof.get("size_band") or company.get("size_band")
    if band in SIZE_POINTS:
        add(SIZE_POINTS[band], f"size:{band}")
    rating = company.get("rating")
    reviews = company.get("reviews")
    if isinstance(rating, (int, float)) and rating >= 4.3:
        add(6, f"rating {rating}")
    if isinstance(reviews, int) and reviews >= 100:
        add(6, "established (100+ reviews)")

    # Buying intent — growth signals.
    if sig.get("hiring"):
        add(15, "hiring (growing)")
    if sig.get("blog_active"):
        add(4, "active content")

    # Basic presence.
    if company.get("website"):
        add(6, "has website")

    score = max(0, min(100, pts))
    tier = "hot" if score >= 65 else "warm" if score >= 40 else "cold"
    return {"score": score, "tier": tier, "reasons": reasons}
