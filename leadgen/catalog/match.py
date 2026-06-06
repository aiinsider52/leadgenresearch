"""Match a company's analysis/signals against the n8n automation catalog.

Stage 1 (this file): cheap keyword/signal scoring — runs free, no LLM.
Stage 2 (optional, analyze/company.py): Claude re-ranks the shortlist and
writes the personalized pitch angle. Keeping a free deterministic prefilter
keeps token cost down and gives a sane fallback when no API key is set.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

CATALOG_PATH = Path(__file__).with_name("automations.yaml")


@dataclass
class Match:
    id: str
    name: str
    pitch: str
    solves: str
    score: float
    matched_on: list[str]
    effort: str


def load_catalog(path: Path | str = CATALOG_PATH) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["automations"]


def _signal_text(company: dict) -> str:
    """Flatten the company record into one lowercased haystack."""
    parts: list[str] = []
    for key in ("industry", "description", "name", "summary"):
        v = company.get(key)
        if v:
            parts.append(str(v))
    parts.extend(str(s) for s in company.get("signals", []))
    parts.extend(str(s) for s in company.get("pains", []))
    # Absence-of-X signals derived from enrichment.
    socials = company.get("socials", {})
    if not socials.get("linkedin") and not socials.get("instagram"):
        parts.append("inactive socials no social media")
    return " ".join(parts).lower()


def _pitch(auto: dict, lang: str) -> str:
    p = auto.get("pitch", "")
    if isinstance(p, dict):
        return p.get(lang) or p.get("en") or next(iter(p.values()), "")
    return p


def match_company(
    company: dict, top_n: int = 3, lang: str = "uk", catalog: list[dict] | None = None
) -> list[Match]:
    catalog = catalog or load_catalog()
    hay = _signal_text(company)
    industry = str(company.get("industry", "")).lower()

    results: list[Match] = []
    for auto in catalog:
        matched: list[str] = []
        score = 0.0
        for trig in auto.get("triggers", []):
            if trig.lower() in hay:
                matched.append(trig)
                score += 1.0
        inds = [i.lower() for i in auto.get("industries", [])]
        if industry and any(industry in i or i in industry for i in inds):
            score += 1.5
            matched.append(f"industry:{industry}")
        # Prefer low-effort wins on ties (easier to sell + deliver fast).
        score += {"low": 0.3, "medium": 0.15, "high": 0.0}.get(auto.get("effort", ""), 0.0)

        if score > 0:
            results.append(
                Match(
                    id=auto["id"],
                    name=auto["name"],
                    pitch=_pitch(auto, lang),
                    solves=auto["solves"],
                    score=round(score, 2),
                    matched_on=matched,
                    effort=auto.get("effort", "?"),
                )
            )

    results.sort(key=lambda m: m.score, reverse=True)
    return results[:top_n]


if __name__ == "__main__":
    demo = {
        "name": "Bella Vista",
        "industry": "restaurant",
        "description": "Італійський ресторан у Львові з онлайн-бронюванням столиків.",
        "signals": ["відгуки", "бронювання"],
        "socials": {},
    }
    for m in match_company(demo, lang="uk"):
        print(f"[{m.score}] {m.name}  ←  {m.matched_on}")
        print(f"        {m.pitch}\n")
