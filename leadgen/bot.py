"""Telegram bot to run the lead pipeline from chat. aiogram v3.

Set BOT_TOKEN env var, then:  python3 -m leadgen.bot

Commands:
  /find <category> <city>   run discover→enrich→match
  /lang uk|ru|en            set language
  /cats                     list categories
  /help
"""
from __future__ import annotations

import asyncio
import html
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from .i18n import LANGS, resolve_category, t
from .service import find_leads
from .sources.osm import CATEGORY_TAGS

# Per-user language (swap for a DB if you need persistence).
USER_LANG: dict[int, str] = {}


def lang_of(msg: Message) -> str:
    return USER_LANG.get(msg.from_user.id, "uk")


def format_lead(lead: dict, lang: str) -> str:
    c = lead["company"]
    en = lead.get("enrichment", {})
    lines = [f"<b>{html.escape(c['name'])}</b>"]
    if c.get("website"):
        lines.append(html.escape(c["website"]))
    if c.get("address"):
        lines.append(f"📍 {html.escape(c['address'])}")
    emails = ", ".join(en.get("emails", [])[:2])
    phones = ", ".join(en.get("phones", [])[:2])
    if emails:
        lines.append(f"✉️ {html.escape(emails)}")
    if phones:
        lines.append(f"📞 {html.escape(phones)}")
    tg = " ".join(f"@{h}" for h in en.get("telegram", []))
    if tg:
        lines.append(f"📨 {html.escape(tg)}")
    dms = en.get("decision_makers", [])
    if dms:
        lines.append("👤 " + "; ".join(f"{html.escape(p['name'])} ({html.escape(p['role'])})" for p in dms[:3]))
    autos = lead.get("automations", [])
    if autos:
        lines.append("\n💡 " + "\n💡 ".join(f"<b>{html.escape(a['name'])}</b> — {html.escape(a['pitch'])}" for a in autos))
    return "\n".join(lines)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def start(msg: Message):
        await msg.answer(t("bot_start", lang_of(msg)))

    @dp.message(Command("help"))
    async def help_(msg: Message):
        await msg.answer(t("bot_help", lang_of(msg)))

    @dp.message(Command("cats"))
    async def cats(msg: Message):
        await msg.answer("📂 " + ", ".join(sorted(CATEGORY_TAGS.keys())))

    @dp.message(Command("lang"))
    async def setlang(msg: Message, command: CommandObject):
        arg = (command.args or "").strip().lower()
        if arg in LANGS:
            USER_LANG[msg.from_user.id] = arg
            await msg.answer(t("bot_lang_set", arg))
        else:
            await msg.answer("Usage: /lang uk|ru|en")

    @dp.message(Command("find"))
    async def find(msg: Message, command: CommandObject):
        lang = lang_of(msg)
        args = (command.args or "").split()
        if len(args) < 2:
            await msg.answer(t("bot_help", lang))
            return
        category_label = args[0]
        city = " ".join(args[1:])
        category = resolve_category(category_label) or category_label
        await msg.answer(t("bot_searching", lang, cat=category, city=city))
        try:
            leads = await asyncio.to_thread(
                find_leads, category, city, "Ukraine", 10, lang, True, False
            )
        except Exception as exc:
            await msg.answer(f"⚠️ {html.escape(str(exc))}")
            return
        if not leads:
            await msg.answer(t("no_results", lang))
            return
        await msg.answer(t("found_n", lang, n=len(leads)))
        for lead in leads[:10]:
            await msg.answer(format_lead(lead.to_dict(), lang), disable_web_page_preview=True)

    return dp


async def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Set BOT_TOKEN env var (from @BotFather)")
    bot = Bot(token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = build_dispatcher()
    print("LeadGen bot running…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
