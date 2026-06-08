"""Personalized outreach message generation per decision-maker + channel.

Claude when a key is set; otherwise a solid localized template using the
company's name, the contact's role and the top matched automation.
"""
from __future__ import annotations

from .. import llm

_LANG_NAME = {"uk": "Ukrainian", "ru": "Russian", "en": "English"}

# Channel constraints baked into the prompt + template.
CHANNEL = {
    "email": {"uk": "лист", "ru": "письмо", "en": "email", "limit": "120-160 words, with a subject line"},
    "linkedin": {"uk": "повідомлення LinkedIn", "ru": "сообщение LinkedIn", "en": "LinkedIn DM", "limit": "under 80 words, no subject"},
    "telegram": {"uk": "повідомлення Telegram", "ru": "сообщение Telegram", "en": "Telegram message", "limit": "under 60 words, casual"},
}

_T = {
    "uk": {"hi": "Вітаю", "we": "Ми допомагаємо бізнесам як ваш автоматизувати рутину з n8n",
           "cta": "Відкриті до короткого дзвінка на 15 хв цього тижня?", "sub": "Тема"},
    "ru": {"hi": "Здравствуйте", "we": "Мы помогаем бизнесам как ваш автоматизировать рутину на n8n",
           "cta": "Открыты к короткому 15-мин звонку на этой неделе?", "sub": "Тема"},
    "en": {"hi": "Hi", "we": "We help businesses like yours automate routine work with n8n",
           "cta": "Open to a quick 15-min call this week?", "sub": "Subject"},
}


def write_message(lead: dict, person_index: int = 0, channel: str = "email", lang: str = "uk") -> dict:
    company = lead.get("company", {})
    en = lead.get("enrichment", {})
    autos = lead.get("automations", [])
    dms = en.get("decision_makers", [])
    person = dms[person_index] if 0 <= person_index < len(dms) else {}
    name = person.get("name", "")
    role = person.get("role", "")
    comp = company.get("name", "")
    pitch = autos[0]["pitch"] if autos else ""
    ch = channel if channel in CHANNEL else "email"
    lng = lang if lang in _T else "uk"

    sig = en.get("signals", {}) or {}
    hiring_for = sig.get("hiring_for") or []
    hiring_line = ""
    extra_sys = ""
    if hiring_for:
        roles = ", ".join(hiring_for[:2])
        hiring_line = f"\nHIRING SIGNAL: they posted a job for '{roles}'. "
        extra_sys = (" The prospect is actively HIRING for a role. Open by referencing that job and "
                     "pitch automating ~80% of that work instead of (or alongside) hiring — this is the hook.")

    text = llm.complete(
        system=(
            f"You write concise, non-salesy B2B cold outreach. "
            f"Write the ENTIRE message in {_LANG_NAME.get(lng,'Ukrainian')} (even if the company "
            f"name, role or website are in English — body, subject and CTA must be {_LANG_NAME.get(lng,'Ukrainian')}). "
            f"Channel: {CHANNEL[ch]['en']} ({CHANNEL[ch]['limit']}). "
            "One clear value prop, one soft CTA. No fluff, no emoji overload. "
            "We are an automation agency selling ready-made n8n AI automations." + extra_sys
        ),
        user=(
            f"Recipient: {name or 'decision maker'} ({role}) at {comp}.\n"
            f"Most relevant automation to offer: {autos[0]['name'] if autos else 'process automation'} "
            f"— {pitch}\n"
            f"Company facts: rating {company.get('rating')}, size {company.get('size_band')}, "
            f"hiring={sig.get('hiring')}.{hiring_line}\n"
            "Write the message."
        ),
        max_tokens=500,
    )
    if text:
        return {"message": text, "channel": ch, "person": name, "ai": True}

    # --- Template fallback ---
    t = _T[lng]
    greet = f"{t['hi']}, {name}!" if name else f"{t['hi']}!"
    body = f"{t['we']}."
    if pitch:
        body += f" {pitch}"
    msg = f"{greet}\n\n{body}\n\n{t['cta']}"
    if ch == "email":
        subj = f"{t['sub']}: {autos[0]['name'] if autos else 'Автоматизація'} для {comp}"
        msg = f"{subj}\n\n{msg}"
    return {"message": msg, "channel": ch, "person": name, "ai": False}
