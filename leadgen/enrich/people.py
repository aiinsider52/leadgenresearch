"""Promote executive-looking staff into addressable decision-makers."""
from __future__ import annotations

import re

from .linkedin import enrich_people

EXEC_RE = re.compile(
    r"\b(founder|co-?founder|owner|ceo|chief executive|managing director|director|"
    r"president|partner|vp|vice president|head of|cmo|cto|coo|cro|cfo|"
    r"geschäftsführer|inhaber|засновник|власник|директор|керівник|партнер|"
    r"основатель|владелец|руководитель)\b", re.I,
)


def enrich_decision_makers(enrichment: dict, company_name: str) -> dict:
    dms = list(enrichment.get("decision_makers") or [])
    seen = {(p.get("name") or "").strip().lower() for p in dms}
    for person in enrichment.get("staff") or []:
        name, role = person.get("name", ""), person.get("role", "")
        if name and EXEC_RE.search(role) and name.strip().lower() not in seen:
            promoted = dict(person)
            promoted["confidence"] = "medium"
            dms.append(promoted)
            seen.add(name.strip().lower())
    enrich_people(dms, company_name, enrichment.get("linkedin_profiles") or [])
    enrichment["decision_makers"] = dms
    return enrichment
