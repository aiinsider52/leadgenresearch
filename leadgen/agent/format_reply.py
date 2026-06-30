"""Deterministic agent replies for search results — no hallucinated leads."""
from __future__ import annotations

_TIER = {
    "hot": {"uk": "🔥 hot", "ru": "🔥 hot", "en": "🔥 hot"},
    "warm": {"uk": "🟡 warm", "ru": "🟡 warm", "en": "🟡 warm"},
    "cold": {"uk": "⚪ cold", "ru": "⚪ cold", "en": "⚪ cold"},
}


def format_leads_reply(
    *,
    count: int,
    leads: list[dict],
    lang: str = "uk",
    source: str = "",
    cities: list[str] | None = None,
    fast: bool = False,
) -> str:
    lng = lang if lang in ("uk", "ru", "en") else "uk"
    intros = {
        "uk": f"Знайшов **{count}** лідів",
        "ru": f"Нашёл **{count}** лидов",
        "en": f"Found **{count}** leads",
    }
    parts = [intros[lng]]
    if cities:
        parts[0] += f" ({', '.join(cities[:4])})"
    if source:
        parts[0] += f" · `{source}`"
    if fast:
        fast_note = {
            "uk": " · швидкий режим (без повного enrich — скажіть «з email» для глибшого пошуку)",
            "ru": " · быстрый режим (без полного enrich — скажите «с email» для глубокого поиска)",
            "en": " · fast mode (light enrich — say «with email» for deep search)",
        }
        parts[0] += fast_note[lng]
    parts[0] += ":\n"

    if not leads:
        empty = {
            "uk": "\nНічого не знайшов. Спробуйте інше місто, нішу або `all_sources`.",
            "ru": "\nНичего не найдено. Попробуйте другой город, нишу или `all_sources`.",
            "en": "\nNo results. Try another city, niche, or `all_sources`.",
        }
        return parts[0] + empty[lng]

    show = leads[:8]
    for i, l in enumerate(show, 1):
        tier = (l.get("tier") or "cold")
        tier_lbl = _TIER.get(tier, _TIER["cold"]).get(lng, tier)
        name = l.get("name") or "—"
        city = l.get("city") or ""
        score = l.get("score")
        sc = f" **{score}**" if score is not None else ""
        emails = l.get("emails") or []
        phones = l.get("phones") or []
        dms = l.get("decision_makers") or []
        contact_bits = []
        if emails:
            contact_bits.append(emails[0])
        elif phones:
            contact_bits.append(phones[0])
        elif dms:
            contact_bits.append(f"{dms[0].get('name', '')} ({dms[0].get('role', '')})".strip())
        site = l.get("website") or ""
        line = f"\n{i}. **{name}**{sc} · {tier_lbl}"
        if city:
            line += f" · {city}"
        if contact_bits:
            line += f"\n   📧 {contact_bits[0]}"
        if site:
            line += f"\n   🔗 {site}"
        hiring = l.get("hiring_for") or []
        if hiring:
            line += f"\n   💼 {hiring[0]}"
        parts.append(line)

    if count > len(show):
        more = {
            "uk": f"\n\n_+ ще {count - len(show)} у базі. Відкрийте вкладку «Всі ліди»._",
            "ru": f"\n\n_+ ещё {count - len(show)} в базе. Откройте вкладку «Все лиды»._",
            "en": f"\n\n_+ {count - len(show)} more in database. Open «All leads» tab._",
        }
        parts.append(more[lng])
    return "".join(parts)
