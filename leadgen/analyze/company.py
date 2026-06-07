"""Company analysis: pains + ICP summary + outreach angle.

Uses Claude when a key is set, otherwise derives a solid summary from the
signals we already have (matched automations, growth, size).
"""
from __future__ import annotations

from .. import llm

_LANG_NAME = {"uk": "Ukrainian", "ru": "Russian", "en": "English"}


def analyze(lead: dict, lang: str = "uk") -> dict:
    company = lead.get("company", {})
    en = lead.get("enrichment", {})
    autos = lead.get("automations", [])
    name = company.get("name", "")

    facts = {
        "name": name,
        "category": company.get("gmaps_category") or company.get("category"),
        "city": company.get("city"),
        "rating": company.get("rating"),
        "reviews": company.get("reviews"),
        "size": (en.get("profile", {}) or {}).get("size_band") or company.get("size_band"),
        "hiring": (en.get("signals", {}) or {}).get("hiring"),
        "has_email": bool(en.get("emails")),
        "decision_makers": [p.get("name") for p in en.get("decision_makers", [])][:3],
        "top_automations": [a.get("name") for a in autos[:3]],
        "pitches": [a.get("pitch") for a in autos[:3]],
    }

    text = llm.complete(
        system=(
            f"You are a B2B sales analyst. Reply in {_LANG_NAME.get(lang,'Ukrainian')}. "
            "Be concrete and concise. Output 3 short sections: PAINS (2-3 bullets), "
            "WHY-NOW (1 line), ANGLE (1 line on how to open the pitch)."
        ),
        user=f"Analyze this company for an automation-agency outreach:\n{facts}",
        max_tokens=400,
    )
    if text:
        return {"summary": text, "ai": True}

    # --- Template fallback (no key) ---
    pains = []
    if not facts["has_email"]:
        pains.append("важко знайти прямий контакт — втрата вхідних звернень")
    if facts["hiring"]:
        pains.append("компанія росте/наймає — навантаження на процеси")
    if autos:
        pains.append(f"можлива автоматизація: {autos[0].get('solves','')}")
    why = "компанія активна" + (" і наймає" if facts["hiring"] else "")
    angle = autos[0].get("pitch") if autos else "запропонувати аудит процесів"
    summary = (
        "БОЛІ:\n- " + "\n- ".join(pains or ["потрібен ручний розбір"]) +
        f"\n\nЧОМУ ЗАРАЗ: {why}\n\nКУТ ЗАХОДУ: {angle}"
    )
    return {"summary": summary, "ai": False}
