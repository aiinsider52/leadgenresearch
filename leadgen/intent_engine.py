"""Intent signal helpers — surface leads showing buying signals."""
from __future__ import annotations

INTENT_KEYS = frozenset({"hiring", "funding", "expansion", "tender", "automation_need"})


def lead_has_intent(lead: dict) -> bool:
    signals = (lead.get("enrichment", {}) or {}).get("signals") or {}
    if isinstance(signals, dict) and INTENT_KEYS & set(signals.keys()):
        return True
    intent = (lead.get("enrichment", {}) or {}).get("intent") or {}
    if isinstance(intent, dict) and intent.get("score", 0) > 0:
        return True
    return False


def intent_labels(lead: dict) -> list[str]:
    signals = (lead.get("enrichment", {}) or {}).get("signals") or {}
    if not isinstance(signals, dict):
        return []
    return sorted(k for k in signals if k in INTENT_KEYS)


def filter_intent_leads(leads: list[dict], limit: int = 50) -> list[dict]:
    out = [l for l in leads if lead_has_intent(l)]
    out.sort(key=lambda l: ((l.get("score", {}) or {}).get("score") or 0), reverse=True)
    return out[:limit]
