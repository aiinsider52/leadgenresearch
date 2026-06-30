"""Signal listeners — RSS/news monitoring for buying triggers."""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import quote

import requests

from ..config import data_dir, get
from .. import brave
from ..sources.osm import Company
from .. import service

SIGNALS_FILE = data_dir() / "signals.jsonl"
TRIGGERS = re.compile(
    r"\b(funding|invest|raise|CEO|змін|новий офіс|тендер|RFP|procurement|"
    r"series [abc]|acquisition|hiring spree|expansion|інвест|фінансуван)\b",
    re.I,
)

DEFAULT_FEEDS = [
    "https://ain.ua/feed/",
    "https://dou.ua/lenta/feed/",
]

ProgressFn = Optional[Callable[[str], None]]


def _fetch_rss(url: str, timeout: int = 15) -> list[dict]:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "leadgen-signals/0.1"})
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        items = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "")[:500]
            if title:
                items.append({"title": title, "url": link, "description": desc, "feed": url})
        return items
    except Exception:
        return []


def _company_from_signal(item: dict, country: str = "Ukraine") -> Company | None:
    title = item.get("title", "")
    if not TRIGGERS.search(title + " " + item.get("description", "")):
        return None
    # Extract quoted company name or first capitalized phrase
    m = re.search(r"['\"]([^'\"]{3,40})['\"]", title)
    name = m.group(1) if m else title.split("—")[0].split("-")[0].strip()[:60]
    if len(name) < 3:
        return None
    signals = {"news_active": True, "trigger": title[:120], "source_url": item.get("url")}
    enrichment = {
        "emails": [], "phones": [], "socials": {}, "signals": signals,
        "decision_makers": [], "staff": [], "source": "signal",
    }
    return Company(
        name=name, category="signal", city="", country=country,
        website=None, source="signal",
        raw_tags={"signals": signals, "_enrichment": enrichment},
    )


def poll_signals(progress: ProgressFn = None, *, limit: int = 15) -> dict:
    """Poll RSS feeds + optional Brave news for triggers → auto-leads."""
    if progress:
        progress("signals:poll_start")
    hits: list[dict] = []
    companies: list[Company] = []

    feeds = DEFAULT_FEEDS
    extra = get("SIGNAL_RSS_FEEDS", "")
    if extra:
        feeds = feeds + [u.strip() for u in extra.split(",") if u.strip()]

    for feed in feeds:
        for item in _fetch_rss(feed)[:20]:
            if TRIGGERS.search(item.get("title", "") + item.get("description", "")):
                hits.append(item)
                c = _company_from_signal(item)
                if c:
                    companies.append(c)

    if brave.available():
        try:
            from ..enrich.brave_signals import news_search
            for q in ("Ukraine startup funding", "Ukraine company expansion"):
                for item in (news_search(q, count=5) or [])[:5]:
                    hits.append(item)
                    c = _company_from_signal(item)
                    if c:
                        companies.append(c)
        except Exception:
            pass

    leads_created = 0
    if companies:
        from ..service import Lead, _process
        unique = {}
        for c in companies:
            unique[c.name.lower()] = c
        processed = _process(list(unique.values())[:limit], "uk", enrich=False, progress=progress)
        leads_created = len(processed)

    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hits": len(hits),
        "leads_created": leads_created,
        "samples": [h.get("title", "")[:80] for h in hits[:5]],
    }
    with SIGNALS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if progress:
        progress(f"signals:done:{leads_created}_leads")

    return row


def list_recent_signals(limit: int = 20) -> list[dict]:
    if not SIGNALS_FILE.exists():
        return []
    rows = []
    for line in SIGNALS_FILE.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows[::-1]
