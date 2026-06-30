"""Buying-intent signals from Brave News Search."""
from __future__ import annotations

import re

from ..brave import news_search
from ..identity import normalize_text

SIGNALS = {
    "funding": re.compile(r"\b(funding|fundraise|raised|investment|invests?|seed round|series [a-f]|фінансув|інвестиц|инвестиц)\b", re.I),
    "expansion": re.compile(r"\b(expand|expansion|new office|launches?|enters? market|відкрива|розшир|открыва|расшир)\b", re.I),
    "leadership_change": re.compile(r"\b(appoints?|named|joins? as|new ceo|new director|признач|назнач)\b", re.I),
    "partnership": re.compile(r"\b(partnership|partners? with|collaboration|партнерств|співпрац|сотруднич)\b", re.I),
    "acquisition": re.compile(r"\b(acquires?|acquisition|merger|придба|поглин|приобрета|слияни)\b", re.I),
}


def enrich_news_signals(enrichment: dict, company_name: str, country: str = "ALL",
                        search_lang: str = "en") -> dict:
    try:
        results = news_search(f'"{company_name}"', count=10, country=country,
                              search_lang=search_lang, freshness="py")
    except Exception:
        return enrichment
    relevant, detected = [], set()
    company_norm = normalize_text(company_name)
    for item in results:
        text = " ".join(str(x) for x in (
            item.get("title"), item.get("description"), *(item.get("extra_snippets") or [])
        ) if x)
        if company_norm and company_norm not in normalize_text(text):
            continue
        hits = [name for name, pattern in SIGNALS.items() if pattern.search(text)]
        if not hits:
            continue
        detected.update(hits)
        relevant.append({"title": item.get("title"), "url": item.get("url"),
                         "age": item.get("age"), "signals": hits})
    signals = dict(enrichment.get("signals") or {})
    for signal in detected:
        signals[signal] = True
    if relevant:
        signals["news"] = relevant[:5]
        signals["news_active"] = True
    enrichment["signals"] = signals
    return enrichment
