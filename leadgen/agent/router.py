"""Fast-path intent router — skip slow LLM loops for common agent requests."""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

from .. import service
from .format_reply import format_leads_reply
from .tools import execute_tool, _filter_leads, _lead_summary

ProgressFn = Optional[Callable[[str], None]]

_CITY_MAP = [
    (r"київ|kyiv|kiev", "Київ"),
    (r"львів|lviv|lviv", "Львів"),
    (r"одес|odesa|odessa", "Одеса"),
    (r"дніпр|dnipro|dnepro", "Дніпро"),
    (r"харків|kharkiv", "Харків"),
    (r"запоріж|zaporizh", "Запоріжжя"),
    (r"вінниц|vinnyts", "Вінниця"),
    (r"киев", "Київ"),
    (r"львов", "Львів"),
    (r"одесс", "Одеса"),
]


def _parse_cities(text: str) -> list[str]:
    low = text.lower()
    found: list[str] = []
    for pat, city in _CITY_MAP:
        if re.search(pat, low) and city not in found:
            found.append(city)
    return found or ["Київ"]


def _parse_limit(text: str, default: int = 20) -> int:
    m = re.search(r"\b(\d{1,3})\b", text)
    if not m:
        return default
    return min(max(int(m.group(1)), 5), 40)


def _wants_deep(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in (
        "all_sources", "all sources", "всі джерел", "все источник",
        "з email", "с email", "with email", "верифік", "enrich",
        "глибок", "глубок", "deep", "80", "100",
    ))


def _wants_expanded(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in ("веер", "expand", "expanded", "розшир", "расшир", "fan"))


def _pick_source(text: str, category: str) -> str:
    low = f"{text} {category}".lower()
    if _wants_deep(text):
        return "all_sources"
    if any(k in low for k in ("найм", "hiring", "ваканс", "jobs", "dou", "djinni", "work.ua", "robota")):
        return "jobs"
    if any(k in low for k in ("founder", "ceo", "c-level", "керівник", "директор", "linkedin people")):
        return "linkedin_people"
    if any(k in low for k in ("instagram", "інстаграм", "инстаграм", " ig ")):
        return "instagram"
    if any(k in low for k in ("facebook", "фейсбук", " fb ")):
        return "facebook"
    if any(k in low for k in ("карта", "maps", "gmaps", "google")):
        return "gmaps"
    return "brave_places"


def _parse_category(text: str) -> str:
    low = text.lower()
    # Strip command words
    cleaned = re.sub(
        r"(?i)\b(знайди|найди|find|search|шукай|покажи|show|get|ліди|лиды|leads)\b",
        " ", text,
    )
    cleaned = re.sub(
        r"(?i)\b(у|в|in|з|с|with|email|all_sources|all sources|top|міст|город|city|cities)\b[^,]*",
        " ", cleaned,
    )
    for pat, _ in _CITY_MAP:
        cleaned = re.sub(pat, " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\b\d{1,3}\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.")
    if len(cleaned) >= 3:
        return cleaned
    if "saas" in low:
        return "saas"
    if "ресторан" in low or "restaurant" in low:
        return "restaurant"
    if "агент" in low or "agency" in low or "marketing" in low:
        return "marketing agency"
    return "marketing agency"


def _is_search_intent(text: str) -> bool:
    low = text.lower()
    return bool(re.search(
        r"(знайди|найди|find|search|шукай|покажи лід|покажи лид|show leads|hot leads|гаряч)",
        low,
    )) or ("лід" in low or "лид" in low) and any(
        k in low for k in ("знайди", "найди", "find", "покажи", "show", "top")
    )


def _is_stats_intent(text: str) -> bool:
    return bool(re.search(r"(статистик|stats|скільки лід|сколько лид|dashboard|воронк)", text.lower()))


def _is_hot_intent(text: str) -> bool:
    low = text.lower()
    return "hot" in low or "гаряч" in low or "горяч" in low


def try_fast_path(
    user_message: str,
    *,
    lang: str = "uk",
    progress: ProgressFn = None,
) -> str | None:
    """Run instant handlers for common intents. Returns reply text or None."""
    msg = user_message.strip()
    if not msg:
        return None

    low = msg.lower()
    if any(k in low for k in (
        "outreach", "чернет", "draft", "analyze", "qualify", "кампан", "campaign",
        "лист для", "message for", "напиши лист", "write email",
    )):
        return None
    if _is_stats_intent(msg):
        data = json.loads(execute_tool("get_stats", {}, lang=lang, progress=progress))
        labels = {
            "uk": f"**База:** {data.get('total_leads', 0)} лідів · email: {data.get('with_email', 0)} · hot: {(data.get('by_tier') or {}).get('hot', 0)} · збережено: {data.get('saved', 0)}",
            "ru": f"**База:** {data.get('total_leads', 0)} лидов · email: {data.get('with_email', 0)} · hot: {(data.get('by_tier') or {}).get('hot', 0)} · сохранено: {data.get('saved', 0)}",
            "en": f"**Database:** {data.get('total_leads', 0)} leads · email: {data.get('with_email', 0)} · hot: {(data.get('by_tier') or {}).get('hot', 0)} · saved: {data.get('saved', 0)}",
        }
        return labels.get(lang, labels["uk"])

    if _is_hot_intent(msg) and not _is_search_intent(msg):
        data = json.loads(execute_tool("list_leads", {"tier": "hot", "limit": 15}, lang=lang, progress=progress))
        return format_leads_reply(count=data.get("count", 0), leads=data.get("leads", []), lang=lang, source="database")

    if not _is_search_intent(msg):
        return None

    cities = _parse_cities(msg)
    category = _parse_category(msg)
    limit = _parse_limit(msg, 20)
    deep = _wants_deep(msg)
    source = _pick_source(msg, category)
    fast = not deep
    require_email = any(k in msg.lower() for k in ("email", "пошт", "почт"))

    tool_args: dict[str, Any] = {
        "category": category,
        "country": "Ukraine",
        "limit": limit,
        "source": source,
        "require_email": require_email,
        "fast": fast,
    }

    if _wants_expanded(msg):
        tool_args["city"] = cities[0] if len(cities) == 1 else ""
        tool_args["cities"] = cities if len(cities) > 1 else None
        raw = execute_tool("search_expanded_niche", tool_args, lang=lang, progress=progress)
    elif len(cities) > 1:
        tool_args["cities"] = cities
        raw = execute_tool("search_multi_city", tool_args, lang=lang, progress=progress)
    else:
        tool_args["city"] = cities[0]
        raw = execute_tool("search_leads", tool_args, lang=lang, progress=progress)

    data = json.loads(raw)
    if data.get("error"):
        return f"⚠️ {data['error']}"

    return format_leads_reply(
        count=data.get("count", 0),
        leads=data.get("leads", []),
        lang=lang,
        source=source,
        cities=cities,
        fast=fast,
    )
