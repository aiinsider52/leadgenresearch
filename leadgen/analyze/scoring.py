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
    quality = en.get("contact_quality", {}) or {}
    contactability = 0
    intent = 0
    fit = 0

    def add(n, label):
        nonlocal pts
        pts += n
        reasons.append(label)

    # Reachability — can we actually contact them?
    if en.get("emails"):
        add(22, "email")
        contactability += 22
    if en.get("phones"):
        add(8, "phone")
        contactability += 8
    if en.get("decision_makers"):
        add(20, "decision-maker")
        contactability += 20
    if socials.get("linkedin"):
        add(8, "LinkedIn")
        contactability += 8
    if en.get("telegram"):
        add(6, "Telegram")
        contactability += 6
    if quality.get("high_confidence_dm_count"):
        add(5, "verified decision-maker")
        contactability += 5

    # Quality / maturity.
    band = prof.get("size_band") or company.get("size_band")
    if band in SIZE_POINTS:
        add(SIZE_POINTS[band], f"size:{band}")
        fit += SIZE_POINTS[band]
    rating = company.get("rating")
    reviews = company.get("reviews")
    if isinstance(rating, (int, float)) and rating >= 4.3:
        add(6, f"rating {rating}")
        fit += 6
    if isinstance(reviews, int) and reviews >= 100:
        add(6, "established (100+ reviews)")
        fit += 6

    # Buying intent — growth signals.
    if sig.get("hiring"):
        add(15, "hiring (growing)")
        intent += 15
    if sig.get("blog_active"):
        add(4, "active content")
    if sig.get("funding"):
        add(15, "recent funding")
        intent += 15
    if sig.get("expansion"):
        add(12, "expanding")
        intent += 12
    if sig.get("leadership_change"):
        add(8, "leadership change")
    if sig.get("partnership") or sig.get("acquisition"):
        add(8, "strategic activity")
        intent += 8
    if sig.get("tender"):
        add(15, "active tender/procurement")
        intent += 15
    if sig.get("automation_need"):
        add(18, "automation need")
        intent += 18

    # Basic presence.
    if company.get("website"):
        add(6, "has website")
        fit += 6

    score = max(0, min(100, pts))
    tier = "hot" if score >= 65 else "warm" if score >= 40 else "cold"
    evidence = quality.get("verified_email_count", 0) + quality.get("high_confidence_dm_count", 0)
    return {
        "score": score, "tier": tier, "reasons": reasons,
        "dimensions": {
            "fit": min(100, fit * 3),
            "intent": min(100, intent * 3),
            "contactability": min(100, contactability * 2),
            "data_confidence": min(100, evidence * 25 + (20 if company.get("website") else 0)),
        },
    }
