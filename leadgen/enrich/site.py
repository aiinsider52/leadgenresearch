"""Site enrichment: extract emails, phones, socials, Telegram and Impressum
decision-makers from a company's website. Pure Python, no API keys.

This is the free, GDPR-friendly core of the lead-gen system. For DE/AT/CH
sites the Impressum page legally must contain the managing director
(Geschäftsführer = a C-level decision-maker) and a business contact, so we
mine it directly instead of paying Apollo.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
# Phone numbers: must start with +, 00 or 0 AND be grouped with a separator,
# so we don't capture bare ID/date runs like "19982026".
PHONE_RE = re.compile(
    r"(?:\+|00)\d{1,3}[\s.\-/()]+\d[\d\s.\-/()]{5,}\d"
    r"|0\d{1,4}[\s.\-/()]+\d[\d\s.\-/()]{4,}\d"
)
# Words that wrongly get glued onto a captured name on Impressum pages.
NAME_STOPWORDS = {
    "Kontakt", "Telefon", "Tel", "Fax", "E-Mail", "Email", "Registergericht",
    "Registernummer", "Umsatzsteuer", "USt", "Handelsregister", "Vertreten",
    "Sitz", "Adresse", "Postanschrift", "Verantwortlich", "Inhaltlich",
}
TELEGRAM_RE = re.compile(r"(?:https?://)?(?:t\.me|telegram\.me)/([A-Za-z0-9_]{4,})", re.I)
_LINKEDIN_PROFILE_RE = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/[A-Za-z0-9\-_%]+/?", re.I)
# Geschäftsführer / managing director / CEO line on Impressum pages.
CLEVEL_RE = re.compile(
    r"(?:Gesch[äa]ftsf[üu]hrer(?:in)?|Vertretungsberechtigt(?:er)?|"
    r"Inhaber(?:in)?|Managing Director|CEO|Owner|Founder)\s*[:\-]?\s*"
    r"([A-ZÄÖÜ][\wäöüß.\-]+(?:\s+[A-ZÄÖÜ][\wäöüß.\-]+){1,3})",
)

SOCIAL_HOSTS = {
    "linkedin": ("linkedin.com",),
    "instagram": ("instagram.com",),
    "facebook": ("facebook.com", "fb.com"),
    "twitter": ("twitter.com", "x.com"),
    "youtube": ("youtube.com", "youtu.be"),
    "tiktok": ("tiktok.com",),
    "xing": ("xing.com",),
}

JUNK_EMAIL_HINTS = ("example.com", "sentry.io", "wixpress.com", "@2x", ".png", ".jpg")
CONTACT_HINTS = ("impressum", "kontakt", "contact", "about", "team", "ueber-uns", "über-uns", "legal")


@dataclass
class Person:
    name: str
    role: str
    source_url: str


@dataclass
class CompanyProfile:
    """Firmographics mined from the site (best-effort, free sources)."""
    legal_name: Optional[str] = None
    employees: Optional[str] = None          # e.g. "11-50" or "20"
    size_band: Optional[str] = None          # micro | small | medium | large
    founders: list[str] = field(default_factory=list)
    founded: Optional[str] = None
    revenue: Optional[str] = None            # only if explicitly published
    industry: Optional[str] = None


@dataclass
class SiteEnrichment:
    url: str
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    socials: dict[str, str] = field(default_factory=dict)
    telegram: list[str] = field(default_factory=list)
    decision_makers: list[Person] = field(default_factory=list)
    staff: list[Person] = field(default_factory=list)
    profile: CompanyProfile = field(default_factory=CompanyProfile)
    signals: dict = field(default_factory=dict)   # growth signals (hiring, blog, etc.)
    linkedin_profiles: list[str] = field(default_factory=list)  # personal /in/ links found on-site
    pages_crawled: list[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "emails": self.emails,
            "phones": self.phones,
            "socials": self.socials,
            "telegram": self.telegram,
            "decision_makers": [p.__dict__ for p in self.decision_makers],
            "staff": [p.__dict__ for p in self.staff],
            "profile": self.profile.__dict__,
            "signals": self.signals,
            "linkedin_profiles": self.linkedin_profiles,
            "pages_crawled": self.pages_crawled,
            "error": self.error,
        }


def _fetch(session: requests.Session, url: str, timeout: int = 15) -> Optional[str]:
    try:
        r = session.get(url, timeout=timeout, allow_redirects=True)
        ctype = r.headers.get("content-type", "")
        if r.status_code == 200 and "html" in ctype:
            return r.text
    except requests.RequestException:
        return None
    return None


def _clean_phone(raw: str) -> Optional[str]:
    digits = re.sub(r"[^\d+]", "", raw)
    core = digits.lstrip("+")
    if 7 <= len(core) <= 15:
        return digits
    return None


def _size_band(n: Optional[int]) -> Optional[str]:
    if n is None:
        return None
    if n <= 10:
        return "micro"
    if n <= 50:
        return "small"
    if n <= 250:
        return "medium"
    return "large"


# Strict: only fires on real obfuscation — bracketed [at]/(dot) or the literal
# word "dot"/"punkt". Avoids matching "at"/"." inside ordinary prose.
_BRACKET_AT = re.compile(r"\s*[\[(]\s*(?:at|@|ät)\s*[\])]\s*", re.I)
_BRACKET_DOT = re.compile(r"\s*[\[(]\s*(?:dot|punkt)\s*[\])]\s*", re.I)
_WORD_EMAIL = re.compile(
    r"([a-zA-Z0-9._%+\-]+)\s+(?:at|ät)\s+([a-zA-Z0-9.\-]+)\s+(?:dot|punkt)\s+([a-zA-Z]{2,})",
    re.I,
)


def _deobfuscate_emails(text: str) -> list[str]:
    """Catch anti-bot emails like 'name [at] domain [dot] com' or
    'name at domain dot com' — without false-firing on normal text."""
    out: list[str] = []
    t = _BRACKET_DOT.sub(".", _BRACKET_AT.sub("@", text))
    out.extend(EMAIL_RE.findall(t))
    for local, domain, tld in _WORD_EMAIL.findall(text):
        out.append(f"{local}@{domain}.{tld}")
    return out


def _parse_jsonld(soup: BeautifulSoup, e: "SiteEnrichment") -> None:
    """Extract schema.org Organization/LocalBusiness structured data —
    the most reliable free source for firmographics and contacts."""
    import json as _json

    def walk(obj):
        if isinstance(obj, list):
            for x in obj:
                walk(x)
            return
        if not isinstance(obj, dict):
            return
        t = obj.get("@type", "")
        types = t if isinstance(t, list) else [t]
        if any("Organization" in str(x) or "LocalBusiness" in str(x) for x in types):
            p = e.profile
            p.legal_name = p.legal_name or obj.get("legalName") or obj.get("name")
            if obj.get("email"):
                em = obj["email"].replace("mailto:", "").strip()
                if em and em not in e.emails:
                    e.emails.append(em)
            if obj.get("telephone"):
                ph = _clean_phone(str(obj["telephone"]))
                if ph and ph not in e.phones:
                    e.phones.append(ph)
            ne = obj.get("numberOfEmployees")
            if isinstance(ne, dict):
                ne = ne.get("value") or ne.get("minValue")
            if ne and not p.employees:
                p.employees = str(ne)
                try:
                    p.size_band = _size_band(int(re.sub(r"\D", "", str(ne)) or 0))
                except ValueError:
                    pass
            for f in (obj.get("founder") or obj.get("founders") or []):
                name = f.get("name") if isinstance(f, dict) else f
                if name and name not in p.founders:
                    p.founders.append(name)
                    if not any(d.name == name for d in e.decision_makers):
                        e.decision_makers.append(Person(name=name, role="Founder", source_url=e.url))
            p.founded = p.founded or obj.get("foundingDate")
            for sa in (obj.get("sameAs") or []):
                hit = _classify_social(sa)
                if hit:
                    e.socials.setdefault(*hit)
        # recurse into @graph / nested
        for v in obj.values():
            if isinstance(v, (dict, list)):
                walk(v)

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            walk(_json.loads(tag.string or "{}"))
        except (ValueError, TypeError):
            continue


def _parse_team(soup: BeautifulSoup, page_url: str, e: "SiteEnrichment") -> None:
    """Estimate headcount and pull staff names+roles from a team page."""
    if not any(h in page_url.lower() for h in ("team", "about", "ueber", "über", "staff", "mitarbeiter", "people")):
        return
    count = 0
    for card in soup.select("[class*=team], [class*=member], [class*=staff], [class*=person]"):
        name_el = card.find(["h2", "h3", "h4", "strong"])
        if not name_el:
            continue
        name = name_el.get_text(" ", strip=True)
        if not (2 <= len(name.split()) <= 4) or not name[:1].isupper():
            continue
        role_el = name_el.find_next(["p", "span", "div"])
        role = role_el.get_text(" ", strip=True)[:60] if role_el else "team"
        if not any(s.name == name for s in e.staff):
            e.staff.append(Person(name=name, role=role, source_url=page_url))
            count += 1
    if count and not e.profile.employees:
        e.profile.employees = f"{count}+"
        e.profile.size_band = _size_band(count)


def _trim_name(name: str) -> str:
    """Drop trailing non-name tokens the greedy regex may glue on."""
    tokens = name.split()
    kept: list[str] = []
    for tok in tokens:
        if tok.strip(".,") in NAME_STOPWORDS:
            break
        kept.append(tok)
        if len(kept) >= 3:  # Dr. Max Mustermann is the realistic ceiling
            break
    return " ".join(kept)


def _classify_social(href: str) -> Optional[tuple[str, str]]:
    host = urlparse(href).netloc.lower().lstrip("www.")
    for name, hosts in SOCIAL_HOSTS.items():
        if any(h in host for h in hosts):
            return name, href
    return None


def _find_contact_links(base_url: str, soup: BeautifulSoup) -> list[str]:
    found: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(h in href.lower() for h in CONTACT_HINTS):
            absolute = urljoin(base_url, href)
            if absolute not in found:
                found.append(absolute)
    return found


# Page category -> URL/anchor keywords. Drives the multi-page crawl.
PAGE_CATEGORIES = {
    "contact": ("impressum", "kontakt", "contact", "legal", "imprint"),
    "team": ("team", "about", "ueber-uns", "über-uns", "people", "staff", "mitarbeiter", "komanda", "команда", "о-нас", "про-нас"),
    "careers": ("career", "careers", "jobs", "vacanc", "karriere", "hiring", "join-us", "робота", "вакансі", "вакансии"),
    "blog": ("blog", "news", "press", "insights", "articles", "новини", "новости", "статт"),
}
GROWTH_HIRE_RE = re.compile(
    r"\b(we[’']?re hiring|now hiring|join our team|open positions?|"
    r"job openings?|wir stellen ein|ми наймаємо|шукаємо|вакансі|ваканси)\b", re.I)
JOB_ITEM_HINT = re.compile(r"(apply|bewerben|відгукнут|откликнут|view (job|role)|details)", re.I)


def _norm_host(host: str) -> str:
    return host.lower().removeprefix("www.")


def _categorize_links(base_url: str, soup: BeautifulSoup) -> dict[str, list[str]]:
    base_host = _norm_host(urlparse(base_url).netloc)
    out: dict[str, list[str]] = {k: [] for k in PAGE_CATEGORIES}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True).lower()
        absolute = urljoin(base_url, href)
        if _norm_host(urlparse(absolute).netloc) not in ("", base_host):
            continue  # stay on-site
        low = (href + " " + text).lower()
        for cat, hints in PAGE_CATEGORIES.items():
            if any(h in low for h in hints) and absolute not in out[cat]:
                out[cat].append(absolute)
                break
    return out


def _extract_growth(html: str, soup: BeautifulSoup, page_cat: str, e: SiteEnrichment) -> None:
    text = soup.get_text(" ", strip=True)
    if page_cat == "careers":
        e.signals["hiring"] = True
        # Rough open-position count: job-ish links / apply buttons.
        jobs = sum(1 for a in soup.find_all(["a", "button"]) if JOB_ITEM_HINT.search(a.get_text(" ", strip=True)))
        if jobs:
            e.signals["open_positions"] = max(e.signals.get("open_positions", 0), jobs)
    if page_cat == "blog":
        # Activity signal: recent year present on the blog/news page.
        years = re.findall(r"\b(20\d{2})\b", text)
        if years:
            e.signals["blog_latest_year"] = max(years)
            e.signals["blog_active"] = max(years) >= "2024"
    if GROWTH_HIRE_RE.search(text):
        e.signals["hiring"] = True


def _harvest(html: str, page_url: str, e: SiteEnrichment) -> None:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # Structured data first — highest quality.
    _parse_jsonld(soup, e)
    _parse_team(soup, page_url, e)

    # mailto: / tel: links are the most reliable contact source.
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            em = href[7:].split("?")[0].strip()
            if em and em not in e.emails and "@" in em:
                e.emails.append(em)
        elif href.lower().startswith("tel:"):
            ph = _clean_phone(href[4:])
            if ph and ph not in e.phones:
                e.phones.append(ph)

    candidates = set(EMAIL_RE.findall(html)) | set(_deobfuscate_emails(text))
    for m in candidates:
        m = m.strip().rstrip(".")
        low = m.lower()
        if low in (x.lower() for x in e.emails):
            continue
        if any(h in low for h in JUNK_EMAIL_HINTS):
            continue
        e.emails.append(m)

    for raw in PHONE_RE.findall(text):
        cleaned = _clean_phone(raw)
        if cleaned and cleaned not in e.phones:
            e.phones.append(cleaned)

    for a in soup.find_all("a", href=True):
        hit = _classify_social(a["href"])
        if hit:
            name, href = hit
            e.socials.setdefault(name, href)

    for handle in TELEGRAM_RE.findall(html):
        if handle.lower() in ("share", "iv", "joinchat") or handle in e.telegram:
            continue
        e.telegram.append(handle)

    for prof in _LINKEDIN_PROFILE_RE.findall(html):
        prof = prof.rstrip("/")
        if prof not in e.linkedin_profiles:
            e.linkedin_profiles.append(prof)

    # Decision makers only from Impressum/contact-ish pages to avoid noise.
    if any(h in page_url.lower() for h in ("impressum", "kontakt", "contact", "team", "about")):
        for role_match in CLEVEL_RE.finditer(text):
            name = _trim_name(role_match.group(1).strip())
            role = role_match.group(0).split(role_match.group(1))[0].strip(" :-")
            if name and not any(p.name == name for p in e.decision_makers):
                e.decision_makers.append(Person(name=name, role=role or "decision-maker", source_url=page_url))


# How many pages to crawl per category (budget keeps it polite & fast).
PAGE_BUDGET = {"contact": 2, "team": 2, "careers": 1, "blog": 1}


def enrich_site(url: str, max_pages: int = 8, delay: float = 0.5, deep: bool = True) -> SiteEnrichment:
    """Multi-page crawl: homepage + contact/team/careers/blog pages.

    `deep=False` restores the old shallow behaviour (homepage + contacts only),
    used when speed matters more than growth signals.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    e = SiteEnrichment(url=url)
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "uk,en;q=0.8,de;q=0.6"})

    home = _fetch(session, url)
    if home is None:
        e.error = "homepage unreachable"
        return e

    e.pages_crawled.append(url)
    soup = BeautifulSoup(home, "html.parser")
    _harvest(home, url, e)

    if not deep:
        for link in _find_contact_links(url, soup)[: max_pages - 1]:
            time.sleep(delay)
            html = _fetch(session, link)
            if html:
                e.pages_crawled.append(link)
                _harvest(html, link, e)
        return e

    # Categorized crawl with a per-category budget.
    buckets = _categorize_links(url, soup)
    crawled = 1
    for cat, budget in PAGE_BUDGET.items():
        for link in buckets.get(cat, [])[:budget]:
            if crawled >= max_pages:
                break
            if link in e.pages_crawled:
                continue
            time.sleep(delay)
            html = _fetch(session, link)
            if not html:
                continue
            crawled += 1
            e.pages_crawled.append(link)
            psoup = BeautifulSoup(html, "html.parser")
            _harvest(html, link, e)
            _extract_growth(html, psoup, cat, e)

    # Derive a coarse company size if only staff headcount is known.
    if e.staff and not e.profile.size_band:
        e.profile.size_band = _size_band(len(e.staff))
    return e


def enrich_many(urls: Iterable[str], **kwargs) -> list[SiteEnrichment]:
    return [enrich_site(u, **kwargs) for u in urls]


if __name__ == "__main__":
    import json
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "https://www.anthropic.com"
    print(json.dumps(enrich_site(target).to_dict(), indent=2, ensure_ascii=False))
