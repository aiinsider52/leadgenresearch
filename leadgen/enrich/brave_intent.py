"""High-intent company signals from targeted Brave web-search footprints."""
from __future__ import annotations

import re

from ..brave import web_search
from ..identity import normalize_text

INTENT_PATTERNS = {
    "hiring": re.compile(r"\b(hiring|vacancy|join our team|career|ваканс|найма|шукаємо)\b", re.I),
    "tender": re.compile(r"\b(tender|procurement|rfp|request for proposal|тендер|закупів|закупк)\b", re.I),
    "automation_need": re.compile(r"\b(automation|automate|manual process|spreadsheet|excel|crm migration|автоматизац|ручн\w+ процес)\b", re.I),
    "expansion": re.compile(r"\b(expand|new office|new location|enters? market|розшир|відкрива|открыва)\b", re.I),
}


def enrich_intent_signals(enrichment: dict, company_name: str, website: str | None = None,
                          country: str = "ALL", search_lang: str = "en",
                          max_queries: int = 2) -> dict:
    queries = [
        f'"{company_name}" (hiring OR vacancy OR tender OR procurement OR RFP)',
        f'"{company_name}" (automation OR "manual process" OR spreadsheet OR expansion)',
    ]
    results = []
    for query in queries[:max_queries]:
        try:
            results.extend(web_search(query, count=10, country=country, search_lang=search_lang,
                                      freshness="py"))
        except Exception:
            continue

    company_norm, evidence, detected = normalize_text(company_name), [], set()
    for item in results:
        text = " ".join(str(x) for x in (
            item.get("title"), item.get("description"), *(item.get("extra_snippets") or [])
        ) if x)
        if company_norm and company_norm not in normalize_text(text):
            continue
        hits = [name for name, pattern in INTENT_PATTERNS.items() if pattern.search(text)]
        if hits:
            detected.update(hits)
            evidence.append({"title": item.get("title"), "url": item.get("url"), "signals": hits})

    signals = dict((enrichment or {}).get("signals") or {})
    for signal in detected:
        signals[signal] = True
    if evidence:
        signals["intent_evidence"] = evidence[:8]
    enrichment["signals"] = signals
    return enrichment
