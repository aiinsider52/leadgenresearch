"""UI strings (uk/ru/en) for the dashboard and Telegram bot, plus localized
category labels so users can type a niche in their own language."""
from __future__ import annotations

LANGS = ("uk", "ru", "en")
DEFAULT_LANG = "uk"

STRINGS: dict[str, dict[str, str]] = {
    "app_title": {
        "uk": "LeadGen — пошук лідів та AI-автоматизації",
        "ru": "LeadGen — поиск лидов и AI-автоматизации",
        "en": "LeadGen — lead finder & AI automations",
    },
    "search": {"uk": "Пошук", "ru": "Поиск", "en": "Search"},
    "category": {"uk": "Категорія", "ru": "Категория", "en": "Category"},
    "city": {"uk": "Місто", "ru": "Город", "en": "City"},
    "country": {"uk": "Країна", "ru": "Страна", "en": "Country"},
    "limit": {"uk": "Кількість", "ru": "Количество", "en": "Limit"},
    "run": {"uk": "Знайти лідів", "ru": "Найти лидов", "en": "Find leads"},
    "company": {"uk": "Компанія", "ru": "Компания", "en": "Company"},
    "contacts": {"uk": "Контакти", "ru": "Контакты", "en": "Contacts"},
    "decision_makers": {"uk": "Керівники", "ru": "Руководители", "en": "Decision makers"},
    "automations": {"uk": "Автоматизації", "ru": "Автоматизации", "en": "Automations"},
    "score": {"uk": "Скор", "ru": "Скор", "en": "Score"},
    "no_results": {"uk": "Нічого не знайдено", "ru": "Ничего не найдено", "en": "No results"},
    "found_n": {"uk": "Знайдено: {n}", "ru": "Найдено: {n}", "en": "Found: {n}"},
    "enriching": {"uk": "Збагачую дані…", "ru": "Обогащаю данные…", "en": "Enriching…"},
    "bot_start": {
        "uk": "👋 Вітаю! Я LeadGen-бот. Команда: /find <категорія> <місто>\nНапр.: /find restaurant Львів",
        "ru": "👋 Привет! Я LeadGen-бот. Команда: /find <категория> <город>\nНапр.: /find restaurant Киев",
        "en": "👋 Hi! I'm the LeadGen bot. Use: /find <category> <city>\nE.g.: /find restaurant Kyiv",
    },
    "bot_searching": {
        "uk": "🔎 Шукаю «{cat}» у «{city}»…",
        "ru": "🔎 Ищу «{cat}» в «{city}»…",
        "en": "🔎 Searching '{cat}' in '{city}'…",
    },
    "bot_lang_set": {"uk": "Мову змінено 🇺🇦", "ru": "Язык изменён 🇷🇺", "en": "Language set 🇬🇧"},
    "bot_help": {
        "uk": "/find <категорія> <місто> — знайти лідів\n/lang uk|ru|en — мова\n/cats — категорії",
        "ru": "/find <категория> <город> — найти лидов\n/lang uk|ru|en — язык\n/cats — категории",
        "en": "/find <category> <city> — find leads\n/lang uk|ru|en — language\n/cats — categories",
    },
}

# Localized niche labels -> category slug (used by osm.CATEGORY_TAGS).
CATEGORY_LABELS: dict[str, str] = {
    # restaurant
    "ресторан": "restaurant", "кафе": "restaurant", "restaurant": "restaurant", "cafe": "restaurant",
    # dental
    "стоматологія": "dental", "стоматология": "dental", "dental": "dental", "dentist": "dental",
    # clinic
    "клініка": "clinic", "клиника": "clinic", "медцентр": "clinic", "clinic": "clinic",
    # beauty
    "салон": "beauty", "краса": "beauty", "красота": "beauty", "beauty": "beauty", "перукарня": "beauty",
    # fitness
    "фітнес": "fitness", "фитнес": "fitness", "спортзал": "fitness", "fitness": "fitness", "gym": "fitness",
    # law
    "юрист": "law", "адвокат": "law", "юридична": "law", "юридическая": "law", "law": "law",
    # real estate
    "нерухомість": "real_estate", "недвижимость": "real_estate", "real estate": "real_estate", "realtor": "real_estate",
    # auto
    "авто": "auto", "автосервіс": "auto", "автосервис": "auto", "сто": "auto", "auto": "auto",
    # hotel
    "готель": "hotel", "отель": "hotel", "hotel": "hotel",
    # retail
    "магазин": "retail", "ритейл": "retail", "retail": "retail", "shop": "retail",
    # agency
    "агенція": "agency", "агентство": "agency", "agency": "agency", "маркетинг": "agency",
    # construction
    "будівництво": "construction", "строительство": "construction", "ремонт": "construction", "construction": "construction",
    # education
    "школа": "education", "курси": "education", "курсы": "education", "education": "education", "школа мов": "education",
}


def t(key: str, lang: str = DEFAULT_LANG, **fmt) -> str:
    lang = lang if lang in LANGS else DEFAULT_LANG
    val = STRINGS.get(key, {}).get(lang) or STRINGS.get(key, {}).get(DEFAULT_LANG) or key
    return val.format(**fmt) if fmt else val


def resolve_category(label: str) -> str | None:
    """Map a user-typed niche (any language) to a category slug."""
    key = label.strip().lower()
    if key in CATEGORY_LABELS:
        return CATEGORY_LABELS[key]
    for label_key, slug in CATEGORY_LABELS.items():
        if key in label_key or label_key in key:
            return slug
    return None
