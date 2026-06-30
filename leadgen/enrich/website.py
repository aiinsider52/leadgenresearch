"""Find and verify official company websites for leads missing a domain."""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, unquote, urlparse

import requests

from ..identity import NON_COMPANY_DOMAINS, domain, normalize_text

SEARCH_URL = "https://html.duckduckgo.com/html/"
UA = "Mozilla/5.0 (compatible; LeadGen/0.2; +https://example.com)"
BLOCKED = NON_COMPANY_DOMAINS | {
    "google.com", "maps.google.com", "yelp.com", "tripadvisor.com",
    "yellowpages.com", "wikipedia.org", "work.ua", "dou.ua",
}
LINK_RE = re.compile(r'class="result__a"[^>]+href="([^"]+)"', re.I)


def _result_url(raw: str) -> str:
    raw = html.unescape(raw)
    parsed = urlparse(raw)
    if "duckduckgo.com" in parsed.netloc:
        raw = parse_qs(parsed.query).get("uddg", [raw])[0]
    return unquote(raw)


def verify_website(url: str, company_name: str, timeout: int = 10) -> bool:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, allow_redirects=True)
    except requests.RequestException:
        return False
    if r.status_code >= 400 or "html" not in r.headers.get("content-type", ""):
        return False
    tokens = [x for x in normalize_text(company_name).split() if len(x) > 2]
    hay = normalize_text(r.text[:250000])
    return not tokens or any(token in hay for token in tokens)


def find_official_website(company_name: str, city: str = "", country: str = "",
                          timeout: int = 15) -> str | None:
    query = " ".join(x for x in (company_name, city, country, "official website") if x)
    try:
        from ..brave import available, web_search
        if available():
            for item in web_search(f'"{company_name}" {city} official website', count=8):
                url = item.get("url")
                d = domain(url)
                if not d or d in BLOCKED or any(d.endswith("." + x) for x in BLOCKED):
                    continue
                base = f"{urlparse(url).scheme or 'https'}://{d}"
                if verify_website(base, company_name):
                    return base
    except Exception:
        pass
    try:
        r = requests.get(SEARCH_URL, params={"q": query}, headers={"User-Agent": UA}, timeout=timeout)
    except requests.RequestException:
        return None
    for raw in LINK_RE.findall(r.text)[:8]:
        url = _result_url(raw)
        d = domain(url)
        if not d or d in BLOCKED or any(d.endswith("." + x) for x in BLOCKED):
            continue
        base = f"{urlparse(url).scheme or 'https'}://{d}"
        if verify_website(base, company_name):
            return base
    return None
