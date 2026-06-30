"""Orchestration layer: discover → enrich → match. Both the web dashboard
and the Telegram bot call these functions so there is one code path.

Persists results to data/leads.jsonl. Analysis/outreach (Claude) plug in
here later; right now matching uses the free deterministic scorer.
"""
from __future__ import annotations

import json
import hashlib
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .analyze.niche import expand_niche
from .analyze.scoring import score_lead
from .analyze.prescore import pre_score
from .catalog.match import Match, match_company
from .catalog.n8n_templates import recommend_templates
from .enrich.people import enrich_decision_makers
from .enrich.brave_people import enrich_people_brave
from .enrich.brave_signals import enrich_news_signals
from .enrich.brave_intent import enrich_intent_signals
from .enrich.contact_quality import assess_contacts
from .enrich.site import enrich_site
from .enrich.website import find_official_website
from .identity import NON_COMPANY_DOMAINS, dedupe_companies, domain as identity_domain, normalize_phone, normalize_text
from .i18n import resolve_category
from .pipeline_metrics import record as record_pipeline_metrics
from .pipeline_metrics import summarize as summarize_pipeline
from . import history
from . import storage
from . import search_guard
from .search_meta import build_limit_meta, cap_reason, merge_multi_meta

# Office-based niches where OSM is sparse → auto-route to Google Maps.
OFFICE_NICHES = {"agency", "law", "real_estate", "education"}
from .sources.osm import Company, discover, discover_around

from .config import data_dir, get

DATA_DIR = data_dir()  # writable; falls back to /tmp on read-only hosts (Vercel)
LEADS_FILE = DATA_DIR / "leads.jsonl"
SAVED_FILE = DATA_DIR / "saved.json"
ENRICH_CACHE_DIR = data_dir("enrich_cache")
ENRICH_CACHE_TTL = 30 * 86400
ALL_SOURCES = (
    "brave_places", "brave_intent", "gmaps", "osm", "instagram", "facebook", "jobs", "dou",
    "djinni", "workua", "robota", "linkedin_people", "linkedin_company",
    "web_discovery", "apify_gmaps",
)
_LEADS_LOCK = threading.Lock()


@dataclass
class Lead:
    company: dict
    enrichment: dict
    automations: list[dict] = field(default_factory=list)   # our sellable offers
    templates: list[dict] = field(default_factory=list)     # live n8n library matches
    score: dict = field(default_factory=dict)               # {score, tier, reasons}
    lang: str = "uk"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchResult:
    leads: list[Lead]
    meta: dict


def _company_signals(c: Company, enrichment: dict) -> dict:
    """Build the dict the matcher consumes from a company + its enrichment."""
    return {
        "name": c.name,
        "industry": c.category,
        "description": " ".join(filter(None, [c.name, c.address or ""])),
        "signals": list(enrichment.get("socials", {}).keys()),
        "socials": enrichment.get("socials", {}),
    }


def _merge_enrichment(base: dict, extra: dict) -> dict:
    """Merge Apify base (emails/socials/reviews) with crawled extras
    (decision-makers, staff, growth signals, profile)."""
    out = dict(base)
    out["emails"] = list(dict.fromkeys((base.get("emails") or []) + (extra.get("emails") or [])))
    out["phones"] = list(dict.fromkeys((base.get("phones") or []) + (extra.get("phones") or [])))
    out["socials"] = {**(extra.get("socials") or {}), **(base.get("socials") or {})}
    for k in ("telegram", "linkedin_profiles", "pages_crawled"):
        out[k] = list(dict.fromkeys((base.get(k) or []) + (extra.get(k) or [])))
    for key in ("decision_makers", "staff"):
        people, seen = [], set()
        for person in (base.get(key) or []) + (extra.get(key) or []):
            pid = normalize_text(person.get("name"))
            if pid and pid not in seen:
                seen.add(pid)
                people.append(person)
        out[key] = people
    out["signals"] = {**(base.get("signals") or {}), **(extra.get("signals") or {})}
    # Keep apify size_band but adopt crawled profile fields where richer.
    prof = dict(base.get("profile") or {})
    for k, v in (extra.get("profile") or {}).items():
        if v and not prof.get(k):
            prof[k] = v
    out["profile"] = prof
    return out


def _cache_path(url: str) -> Path:
    key = hashlib.sha256((identity_domain(url) or url).encode("utf-8")).hexdigest()
    return ENRICH_CACHE_DIR / f"{key}.json"


def _cached_enrich(url: str) -> dict:
    path = _cache_path(url)
    if path.exists() and time.time() - path.stat().st_mtime < ENRICH_CACHE_TTL:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    result = enrich_site(url, max_pages=6).to_dict()
    try:
        path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return result


def _prepare_company(c: Company, discover_websites: bool) -> Company:
    current_domain = identity_domain(c.website)
    if discover_websites and (not current_domain or current_domain in NON_COMPANY_DOMAINS):
        c.website = find_official_website(c.name, c.city, c.country)
        if c.website:
            c.raw_tags["website_discovered"] = True
    return c


def _enrich_company(c: Company, enrich: bool, brave_people: bool, brave_news: bool,
                    brave_intent: bool = True) -> tuple[Company, dict]:
    prebuilt = getattr(c, "raw_tags", {}).get("_enrichment") or {}
    enrichment = dict(prebuilt)
    if enrich and c.website and identity_domain(c.website) not in NON_COMPANY_DOMAINS:
        try:
            crawled = _cached_enrich(c.website)
            enrichment = _merge_enrichment(enrichment, crawled) if prebuilt else crawled
        except Exception as exc:
            if not prebuilt:
                enrichment = {"error": str(exc)}
    if c.phone and not enrichment.get("phones"):
        enrichment.setdefault("phones", []).append(c.phone)
    enrichment = enrich_decision_makers(enrichment, c.name)
    if brave_people:
        enrichment = enrich_people_brave(enrichment, c.name, c.website, search_lang="en")
    if brave_news:
        enrichment = enrich_news_signals(enrichment, c.name, search_lang="en")
    if brave_intent:
        enrichment = enrich_intent_signals(enrichment, c.name, c.website, search_lang="en")
    if enrich and get("USE_WATERFALL", "").lower() in ("1", "true", "yes"):
        from .enrich.waterfall import waterfall_enrich
        enrichment = waterfall_enrich(c.name, c.website, enrichment, brave_people=brave_people)
    else:
        enrichment = assess_contacts(enrichment, c.website)
    return c, enrichment


def _process(companies, lang: str, enrich: bool, progress, category: str = "",
             with_templates: bool = True, limit: int | None = None,
             discover_websites: bool = True, brave_people: bool = True,
             brave_news: bool = True, brave_intent: bool = True,
             search_seq: int | None = None) -> list[Lead]:
    # Live n8n templates depend on category only → fetch once, reuse (cached).
    templates: list[dict] = []
    if with_templates and category:
        try:
            templates = [t.to_dict() for t in recommend_templates(category)]
        except Exception:
            templates = []

    companies = dedupe_companies(companies)
    pool_limit = max((limit or len(companies)) * 4, limit or 0)
    companies = companies[:pool_limit]
    if discover_websites:
        prepared: list[Company] = []
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(companies)))) as executor:
            futures = {executor.submit(_prepare_company, c, True): c for c in companies}
            for future in as_completed(futures):
                try:
                    prepared.append(future.result())
                except Exception:
                    prepared.append(futures[future])
        companies = dedupe_companies(prepared)

    # Cheap ranking first. Spend crawl + Brave calls on strongest candidates,
    # rather than whichever source happened to finish first.
    companies.sort(key=lambda c: pre_score(c.to_dict())["score"], reverse=True)
    for c in companies:
        c.raw_tags["_pre_score"] = pre_score(c.to_dict())

    enriched: list[tuple[Company, dict]] = []
    workers = min(8, max(1, len(companies)))
    requested = limit or len(companies)
    try:
        brave_limit = min(len(companies), int(get("BRAVE_DEEP_LIMIT", str(requested)) or requested))
        deep_multiplier = max(1, int(get("DEEP_ENRICH_MULTIPLIER", "2") or "2"))
    except ValueError:
        brave_limit, deep_multiplier = requested, 2
    deep_limit = min(len(companies), max(requested * deep_multiplier, 10))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_enrich_company, c, enrich and i < deep_limit,
                            brave_people and i < brave_limit, brave_news and i < brave_limit,
                            brave_intent and i < brave_limit): c
            for i, c in enumerate(companies)
        }
        for future in as_completed(futures):
            c = futures[future]
            if progress:
                progress(f"enrich:{c.name}")
            try:
                enriched.append(future.result())
            except Exception as exc:
                enriched.append((c, {"error": str(exc)}))

    leads: list[Lead] = []
    for c, enrichment in enriched:
        signals = _company_signals(c, enrichment)
        matches: list[Match] = match_company(signals, lang=lang)
        company_dict = c.to_dict()
        leads.append(
            Lead(
                company=company_dict,
                enrichment=enrichment,
                automations=[m.__dict__ for m in matches],
                templates=templates,
                score=score_lead(company_dict, enrichment),
                lang=lang,
            )
        )
    leads.sort(key=lambda l: l.score.get("score", 0), reverse=True)  # hottest first
    if limit:
        leads = leads[:limit]
    if search_guard.should_persist(search_seq):
        save_leads(leads)
    return leads


def _discover_source(source: str, category_label: str, category: str, city: str,
                     country: str, limit: int, require_website: bool,
                     ig_mode: str, progress) -> list[Company]:
    if progress:
        progress(f"discover:{source}:{category}:{city}")
    companies: list[Company] = []
    if source == "jobs":
        from .sources.jobs import discover_jobs
        companies = discover_jobs(category_label, city, country=country, limit=limit)
    elif source == "dou":
        from .sources.dou import discover_dou
        companies = discover_dou(category_label, city, country=country, limit=max(limit, 25))
    elif source == "instagram":
        from .sources.instagram import discover_instagram
        companies = discover_instagram(category_label, city, country=country, limit=limit, mode=ig_mode)
    elif source == "facebook":
        from .sources.facebook import discover_facebook
        companies = discover_facebook(category_label, city, country=country, limit=limit)
    elif source == "apify_gmaps":
        from .sources.apify_gmaps import discover_apify, is_supported
        if is_supported(country):
            companies = discover_apify(category_label, city=city, country=country, limit=limit)
    elif source == "brave_places":
        from .sources.brave_places import discover_brave_places
        companies = discover_brave_places(category_label, city=city, country=country, limit=limit)
    elif source == "brave_intent":
        from .sources.brave_intent import discover_brave_intent
        companies = discover_brave_intent(category_label, city=city, country=country, limit=limit)
    elif source == "gmaps":
        if limit >= 20:
            from .sources.gmaps_playwright import discover_gmaps_grid
            companies = discover_gmaps_grid(category_label, city, country=country, limit=limit, grid=3)
        else:
            from .sources.gmaps_playwright import discover_gmaps_pw
            companies = discover_gmaps_pw(category_label, city, country=country, limit=min(limit, 30))
    elif source == "djinni":
        from .sources.djinni import discover_djinni
        companies = discover_djinni(category_label, city, country=country, limit=limit)
    elif source == "workua":
        from .sources.workua import discover_workua
        companies = discover_workua(category_label, city, country=country, limit=limit)
    elif source == "robota":
        from .sources.robota import discover_robota
        companies = discover_robota(category_label, city, country=country, limit=limit)
    elif source == "linkedin_people":
        from .sources.linkedin_people import discover_linkedin_people
        companies = discover_linkedin_people(category_label, city, country=country, limit=limit)
    elif source == "linkedin_company":
        from .sources.linkedin_company import discover_linkedin_company
        companies = discover_linkedin_company(category_label, city, country=country, limit=limit)
    elif source == "web_discovery":
        from .sources.web_discovery import discover_web
        companies = discover_web(category_label, city, country=country, limit=limit)
    elif source == "osm":
        osm_category = resolve_category(category_label) or category
        companies = discover(osm_category, city, country=country, limit=max(limit, 60),
                             require_website=require_website)
    for company in companies:
        company.category = category
    return companies


def find_leads(
    category_label: str,
    city: str,
    country: str = "Ukraine",
    limit: int = 20,
    lang: str = "uk",
    enrich: bool = True,
    require_website: bool = False,
    source: str = "osm",
    ig_mode: str = "business",
    discover_websites: bool = True,
    brave_people: bool = True,
    brave_news: bool = True,
    brave_intent: bool = True,
    progress: Optional[Callable[[str], None]] = None,
    search_seq: int | None = None,
) -> SearchResult:
    """Full free pipeline by city. `source` = 'osm' (default, reliable) or
    'gmaps' (richer: ratings/reviews/size, but experimental). gmaps falls
    back to OSM if Google blocks the request."""
    category = resolve_category(category_label) or category_label
    if source == "auto":  # office niches → Google Maps, physical places → OSM
        source = "gmaps" if category in OFFICE_NICHES else "osm"
    companies: list[Company] = []
    sources = ALL_SOURCES if source in ("all", "all_sources") else (source,)
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=min(6, len(sources))) as executor:
        futures = {
            executor.submit(_discover_source, src, category_label, category, city, country,
                            limit, require_website, ig_mode, progress): src
            for src in sources
        }
        for future in as_completed(futures):
            src = futures[future]
            try:
                companies.extend(future.result())
            except Exception as exc:
                errors.append(f"{src}: {exc}")
                if progress:
                    progress(f"{src}_failed:{exc}")
    if not companies and len(sources) == 1 and errors:
        raise RuntimeError(errors[0])
    if not companies and source not in ("instagram", "jobs", "dou", "brave_places", "brave_intent", "apify_gmaps"):
        companies = _discover_source("osm", category_label, category, city, country, limit,
                                     require_website, ig_mode, progress)
    raw_count = len(companies)
    companies = dedupe_companies(companies)
    leads = _process(companies, lang, enrich, progress, category=category, limit=limit,
                     discover_websites=discover_websites, brave_people=brave_people,
                     brave_news=brave_news, brave_intent=brave_intent,
                     search_seq=search_seq)
    metrics = summarize_pipeline([x.to_dict() for x in leads], category=category_label, city=city,
                                 country=country, source=source, discovered=raw_count,
                                 deduped_before_enrichment=len(companies))
    record_pipeline_metrics(metrics)
    meta = build_limit_meta(
        requested_limit=limit,
        returned=len(leads),
        discovered_raw=raw_count,
        deduped_before_enrichment=len(companies),
        source=source,
    )
    return SearchResult(leads=leads, meta=meta)


def find_leads_around(
    category_label: str,
    lat: float,
    lon: float,
    radius_m: int = 2000,
    limit: int = 20,
    lang: str = "uk",
    enrich: bool = True,
    require_website: bool = False,
    progress: Optional[Callable[[str], None]] = None,
    search_seq: int | None = None,
) -> SearchResult:
    """Full free pipeline around a map point (mini-map selection)."""
    category = resolve_category(category_label) or category_label
    if progress:
        progress(f"discover_around:{category}:{lat},{lon}")
    companies = discover_around(
        category, lat, lon, radius_m=radius_m, limit=limit, require_website=require_website
    )
    raw_count = len(companies)
    leads = _process(companies, lang, enrich, progress, category=category, limit=limit,
                     search_seq=search_seq)
    meta = build_limit_meta(
        requested_limit=limit,
        returned=len(leads),
        discovered_raw=raw_count,
        deduped_before_enrichment=raw_count,
        source="osm_around",
    )
    return SearchResult(leads=leads, meta=meta)


def save_leads(leads: list[Lead]) -> None:
    """Upsert leads atomically so repeated searches enrich instead of bloating JSONL."""
    with _LEADS_LOCK:
        items = _load_raw_leads()
        known_ids = {_lead_id(item) for item in items}
        items.extend(lead.to_dict() for lead in leads)
        merged = _dedupe_lead_dicts(items)
        tmp = LEADS_FILE.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for lead in merged:
                f.write(json.dumps(lead, ensure_ascii=False) + "\n")
        tmp.replace(LEADS_FILE)
        storage.sync_leads([(_lead_id(row), row) for row in merged])
        for lead in leads:
            row = lead.to_dict()
            lid = _lead_id(row)
            history.record(lid, "refreshed" if lid in known_ids else "discovered", lead=row)


def load_leads(limit: int = 200) -> list[dict]:
    return _dedupe_lead_dicts(_load_raw_leads())[-limit:]


# ---- Quality filters ---------------------------------------------------------

def passes_filters(
    lead: dict,
    *,
    email: bool = False,
    phone: bool = False,
    social: bool = False,
    linkedin: bool = False,
    telegram: bool = False,
    dm: bool = False,
) -> bool:
    """True if the lead has the requested contact signals. Used to hide
    empty/low-quality cards in the dashboard and bot."""
    en = lead.get("enrichment", {}) or {}
    socials = en.get("socials", {}) or {}
    if email and not en.get("emails"):
        return False
    if phone and not en.get("phones"):
        return False
    if social and not socials:
        return False
    if linkedin and not socials.get("linkedin"):
        return False
    if telegram and not en.get("telegram"):
        return False
    if dm and not en.get("decision_makers"):
        return False
    return True


# ---- Saved / liked prospects -------------------------------------------------

# Social/link-shortener hosts that aren't a company's own domain — don't dedupe on these.
_NON_DOMAINS = {"instagram.com", "t.me", "telegram.me", "facebook.com", "fb.com",
                "linktr.ee", "linkedin.com", "youtube.com", "tiktok.com", "expz.link"}


def _domain(url) -> Optional[str]:
    return identity_domain(url)


def _lead_id(lead: dict) -> str:
    """Cross-source dedupe key: company domain (so OSM/IG/Jobs/Maps merge),
    else OSM id, else normalized name+city."""
    c = lead.get("company", {})
    d = _domain(c.get("website"))
    if d and d not in _NON_DOMAINS:
        return "d:" + d
    en = lead.get("enrichment", {}) or {}
    phones = (en.get("phones") or []) + ([c.get("phone")] if c.get("phone") else [])
    phone = next((normalize_phone(x) for x in phones if normalize_phone(x)), None)
    if phone:
        return "p:" + phone
    return f"n:{normalize_text(c.get('name'))}|{normalize_text(c.get('city'))}"


def _lead_aliases(lead: dict) -> set[str]:
    c, en = lead.get("company", {}) or {}, lead.get("enrichment", {}) or {}
    aliases = {_lead_id(lead)}
    d = _domain(c.get("website"))
    if d and d not in _NON_DOMAINS:
        aliases.add("d:" + d)
    for value in (en.get("phones") or []) + ([c.get("phone")] if c.get("phone") else []):
        phone = normalize_phone(value)
        if phone:
            aliases.add("p:" + phone)
    name = normalize_text(c.get("name"))
    if name:
        aliases.add(f"n:{name}|{normalize_text(c.get('city'))}")
    return aliases


def _load_raw_leads() -> list[dict]:
    if not LEADS_FILE.exists():
        return []
    rows = []
    with LEADS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def _dedupe_lead_dicts(leads: list[dict]) -> list[dict]:
    out: list[dict] = []
    alias_sets: list[set[str]] = []
    for lead in leads:
        aliases = _lead_aliases(lead)
        indexes = [i for i, known in enumerate(alias_sets) if aliases & known]
        if indexes:
            idx = indexes[0]
            merged = _merge_leads(out[idx], lead)
            for other in reversed(indexes[1:]):
                merged = _merge_leads(merged, out.pop(other))
                alias_sets.pop(other)
            out[idx] = merged
            alias_sets[idx] |= aliases | _lead_aliases(merged)
        else:
            out.append(lead)
            alias_sets.append(aliases)
    return out


def _merge_leads(a: dict, b: dict) -> dict:
    """Merge two records of the same company (from different sources) into one
    richer lead: union contacts/socials/decision-makers, combine sources, keep
    the best of everything, recompute the score."""
    ca, cb = a.get("company", {}) or {}, b.get("company", {}) or {}
    comp = dict(ca)
    for k, v in cb.items():
        if v and not comp.get(k):
            comp[k] = v
    srcs = set(ca.get("sources", []) or []) | set(cb.get("sources", []) or [])
    for x in (ca.get("source"), cb.get("source")):
        if x:
            srcs.add(x)
    comp["sources"] = sorted(srcs)

    ea, eb = a.get("enrichment", {}) or {}, b.get("enrichment", {}) or {}
    en = dict(ea)
    for k in ("emails", "phones", "telegram", "linkedin_profiles", "pages_crawled"):
        en[k] = list(dict.fromkeys((ea.get(k) or []) + (eb.get(k) or [])))
    en["socials"] = {**(eb.get("socials") or {}), **(ea.get("socials") or {})}
    for key in ("decision_makers", "staff"):  # lists of {name,...} → dedupe by name
        seen, merged = set(), []
        for p in (ea.get(key) or []) + (eb.get(key) or []):
            n = (p.get("name") or "").lower()
            if n and n not in seen:
                seen.add(n)
                merged.append(p)
        en[key] = merged
    en["signals"] = {**(ea.get("signals") or {}), **(eb.get("signals") or {})}
    prof = dict(ea.get("profile") or {})
    for k, v in (eb.get("profile") or {}).items():
        if v and not prof.get(k):
            prof[k] = v
    en["profile"] = prof

    out = dict(a)
    out["company"] = comp
    out["enrichment"] = en
    out["automations"] = a.get("automations") or b.get("automations") or []
    out["templates"] = a.get("templates") or b.get("templates") or []
    out["score"] = score_lead(comp, en)  # richer data → fresher score
    return out


def _read_saved() -> dict[str, dict]:
    if not SAVED_FILE.exists():
        return {}
    try:
        return json.loads(SAVED_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_saved(d: dict[str, dict]) -> None:
    SAVED_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


PIPELINE_STATUSES = ["new", "contacted", "replied", "client", "rejected"]


def save_favorite(lead: dict) -> str:
    """Like/save a prospect. Returns its id. Idempotent — keeps existing
    pipeline fields (status/tags/notes) if the lead was already saved."""
    d = _read_saved()
    lid = _lead_id(lead)
    existing = d.get(lid, {})
    lead = {**lead, "saved_id": lid,
            "status": existing.get("status", "new"),
            "tags": existing.get("tags", []),
            "notes": existing.get("notes", "")}
    d[lid] = lead
    _write_saved(d)
    storage.upsert_lead(lid, lead)
    if not existing:
        history.record(lid, "saved", lead=lead)
    return lid


def update_favorite(lead_id: str, **fields) -> bool:
    """Set tags / notes / status on a saved lead."""
    d = _read_saved()
    if lead_id not in d:
        return False
    changes = {}
    for k in ("tags", "notes", "status"):
        if k in fields and fields[k] is not None:
            if d[lead_id].get(k) != fields[k]:
                changes[k] = {"from": d[lead_id].get(k), "to": fields[k]}
            d[lead_id][k] = fields[k]
    _write_saved(d)
    storage.upsert_lead(lead_id, d[lead_id])
    if changes:
        history.record(lead_id, "pipeline_updated", lead=d[lead_id], changes=changes)
    return True


def remove_favorite(lead_id: str) -> bool:
    d = _read_saved()
    if lead_id in d:
        del d[lead_id]
        _write_saved(d)
        return True
    return False


def list_favorites() -> list[dict]:
    return list(_read_saved().values())


def saved_ids() -> list[str]:
    return list(_read_saved().keys())


# ---- Multi-city search ------------------------------------------------------

UA_MAJOR_CITIES = ["Київ", "Львів", "Одеса", "Дніпро", "Харків", "Запоріжжя"]


def _expand_search_terms(category_label: str, lang: str, source: str) -> list[str]:
    """Fan-out terms for expanded search. OSM maps synonyms to tag slugs."""
    if source == "osm":
        terms: list[str] = []
        seen: set[str] = set()
        for term in expand_niche(category_label, lang):
            slug = resolve_category(term)
            key = (slug or term.strip()).lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append(term)
        return terms or [category_label]
    return expand_niche(category_label, lang)


def find_leads_multi(category_label: str, cities: list[str], country: str = "Ukraine",
                     limit: int = 30, lang: str = "uk", enrich: bool = True,
                     source: str = "osm", ig_mode: str = "business",
                     discover_websites: bool = True,
                     brave_people: bool = True, brave_news: bool = True,
                     brave_intent: bool = True,
                     progress: Optional[Callable[[str], None]] = None,
                     search_seq: int | None = None) -> SearchResult:
    """Run the pipeline across several cities, merge + dedupe, then top-N by score."""
    cities = [c.strip() for c in cities if c.strip()]
    if not cities:
        return SearchResult(leads=[], meta=build_limit_meta(
            requested_limit=limit, returned=0, discovered_raw=0, deduped_before_enrichment=0,
            source=source, cities=cities))
    per_city = max(limit, 20) if len(cities) > 1 else limit
    seen: set[str] = set()
    out: list[Lead] = []
    part_meta: list[dict] = []
    for city in cities:
        if progress:
            progress(f"city:{city}")
        try:
            result = find_leads(category_label, city, country=country, limit=per_city, lang=lang,
                                enrich=enrich, source=source, ig_mode=ig_mode,
                                discover_websites=discover_websites, brave_people=brave_people,
                                brave_news=brave_news, brave_intent=brave_intent, progress=progress,
                                search_seq=search_seq)
        except Exception:
            continue
        part_meta.append(result.meta)
        for l in result.leads:
            lid = _lead_id(l.to_dict())
            if lid in seen:
                continue
            seen.add(lid)
            out.append(l)
    out.sort(key=lambda l: l.score.get("score", 0), reverse=True)
    sliced = out[:limit] if limit else out
    meta = merge_multi_meta(part_meta, limit)
    meta["returned"] = len(sliced)
    meta["capped"] = len(sliced) < limit
    meta["cap_reason"] = cap_reason(limit, len(sliced), meta["discovered_raw"],
                                    meta["deduped_before_enrichment"]) if meta["capped"] else None
    meta["cities"] = cities
    meta["source"] = source
    return SearchResult(leads=sliced, meta=meta)


# ---- AI niche fan-out -------------------------------------------------------

def find_leads_expanded(category_label: str, city: str = "", country: str = "Ukraine",
                        limit: int = 40, lang: str = "uk", enrich: bool = True,
                        source: str = "osm", ig_mode: str = "business",
                        cities: Optional[list[str]] = None,
                        discover_websites: bool = True,
                        brave_people: bool = True, brave_news: bool = True,
                        brave_intent: bool = True,
                        progress: Optional[Callable[[str], None]] = None,
                        search_seq: int | None = None) -> SearchResult:
    """Expand the niche into related terms and search each, merged + deduped —
    one query sweeps the whole niche for many more leads."""
    terms = _expand_search_terms(category_label, lang, source)
    per = max(limit // max(len(terms), 1), 8)
    seen: set[str] = set()
    out: list[Lead] = []
    part_meta: list[dict] = []
    for term in terms:
        if progress:
            progress(f"niche:{term}")
        try:
            if cities and len(cities) > 1:
                result = find_leads_multi(term, cities, country=country, limit=per, lang=lang,
                                          enrich=enrich, source=source, ig_mode=ig_mode,
                                          discover_websites=discover_websites, brave_people=brave_people,
                                          brave_news=brave_news, brave_intent=brave_intent,
                                          search_seq=search_seq)
            else:
                result = find_leads(term, city, country=country, limit=per, lang=lang,
                                    enrich=enrich, source=source, ig_mode=ig_mode,
                                    discover_websites=discover_websites, brave_people=brave_people,
                                    brave_news=brave_news, brave_intent=brave_intent,
                                    search_seq=search_seq)
        except Exception:
            continue
        part_meta.append(result.meta)
        for l in result.leads:
            lid = _lead_id(l.to_dict())
            if lid in seen:
                continue
            seen.add(lid)
            out.append(l)
    out.sort(key=lambda l: l.score.get("score", 0), reverse=True)
    sliced = out[:limit]
    meta = merge_multi_meta(part_meta, limit)
    meta["returned"] = len(sliced)
    meta["capped"] = len(sliced) < limit
    meta["cap_reason"] = cap_reason(limit, len(sliced), meta["discovered_raw"],
                                    meta["deduped_before_enrichment"]) if meta["capped"] else None
    meta["source"] = source
    if cities:
        meta["cities"] = cities
    return SearchResult(leads=sliced, meta=meta)


# ---- Analytics --------------------------------------------------------------

def stats() -> dict:
    """Counters for the analytics view: pipeline funnel (saved) + breakdowns
    (all leads) by tier / source / city."""
    from collections import Counter
    saved = list_favorites()
    allleads = load_leads(1000)

    funnel = Counter(s.get("status", "new") for s in saved)
    by_tier = Counter((l.get("score", {}) or {}).get("tier", "cold") for l in allleads)
    by_source = Counter((l.get("company", {}) or {}).get("source", "?") for l in allleads)
    by_city = Counter((l.get("company", {}) or {}).get("city", "?") for l in allleads)
    with_email = sum(1 for l in allleads if (l.get("enrichment", {}) or {}).get("emails"))
    with_dm = sum(1 for l in allleads if (l.get("enrichment", {}) or {}).get("decision_makers"))
    with_website = sum(1 for l in allleads if (l.get("company", {}) or {}).get("website"))
    verified_email = sum(
        bool(((l.get("enrichment", {}) or {}).get("contact_quality") or {}).get("verified_email_count"))
        for l in allleads
    )
    with_intent = sum(
        bool(set(((l.get("enrichment", {}) or {}).get("signals") or {})) &
             {"hiring", "funding", "expansion", "tender", "automation_need"})
        for l in allleads
    )
    source_funnel: dict[str, dict[str, int]] = {}
    for lead in saved:
        company = lead.get("company", {}) or {}
        sources = company.get("sources") or [company.get("source") or "?"]
        status = lead.get("status", "new")
        for source in sources:
            row = source_funnel.setdefault(source, {s: 0 for s in PIPELINE_STATUSES})
            row[status] = row.get(status, 0) + 1
    source_conversion = {}
    for source, row in source_funnel.items():
        contacted = sum(row.get(s, 0) for s in ("contacted", "replied", "client", "rejected"))
        source_conversion[source] = {
            **row,
            "reply_rate": round((row.get("replied", 0) + row.get("client", 0)) / contacted * 100, 1)
            if contacted else 0,
            "client_rate": round(row.get("client", 0) / contacted * 100, 1) if contacted else 0,
        }

    return {
        "total_leads": len(allleads),
        "saved": len(saved),
        "with_email": with_email,
        "with_dm": with_dm,
        "with_website": with_website,
        "verified_email": verified_email,
        "with_intent": with_intent,
        "funnel": {s: funnel.get(s, 0) for s in PIPELINE_STATUSES},
        "by_tier": dict(by_tier),
        "by_source": dict(by_source),
        "by_city": dict(by_city.most_common(8)),
        "source_conversion": source_conversion,
    }


# ---- ICP (ideal customer profile) -------------------------------------------

ICP_FILE = DATA_DIR / "icp.txt"


def get_icp() -> str:
    return ICP_FILE.read_text(encoding="utf-8").strip() if ICP_FILE.exists() else ""


def set_icp(text: str) -> None:
    ICP_FILE.write_text(text.strip(), encoding="utf-8")


# ---- Scheduled searches (run via run_scheduled.py / cron) --------------------

SCHEDULES_FILE = DATA_DIR / "schedules.json"


def list_schedules() -> list[dict]:
    if SCHEDULES_FILE.exists():
        try:
            return json.loads(SCHEDULES_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_schedules(s: list[dict]) -> None:
    SCHEDULES_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def add_schedule(search: dict) -> list[dict]:
    s = list_schedules()
    search = {k: search.get(k) for k in ("category", "city", "cities", "country",
                                         "limit", "lang", "enrich", "source", "ig_mode",
                                         "discover_websites", "brave_people", "brave_news",
                                         "brave_intent")}
    search["brave_intent"] = True if search["brave_intent"] is None else search["brave_intent"]
    s.append(search)
    _save_schedules(s)
    return s


def remove_schedule(index: int) -> list[dict]:
    s = list_schedules()
    if 0 <= index < len(s):
        s.pop(index)
        _save_schedules(s)
    return s


def run_schedules(progress: Optional[Callable[[str], None]] = None) -> dict:
    """Run every saved search with full fan-out (niche expansion + multi-city)
    for maximum nightly volume. New leads are appended (deduped + merged on read).
    Intended for cron (run_scheduled.py)."""
    total = 0
    for i, sc in enumerate(list_schedules()):
        cat = sc.get("category") or ""
        try:
            result = find_leads_expanded(
                cat, sc.get("city", ""), country=sc.get("country", "Ukraine"),
                limit=sc.get("limit", 40), lang=sc.get("lang", "uk"),
                enrich=sc.get("enrich", True), source=sc.get("source", "osm"),
                ig_mode=sc.get("ig_mode", "business"),
                discover_websites=sc.get("discover_websites", True),
                brave_people=sc.get("brave_people", True), brave_news=sc.get("brave_news", True),
                brave_intent=sc.get("brave_intent", True),
                cities=sc.get("cities") or None, progress=progress)
            total += len(result.leads)
            if progress:
                progress(f"schedule {i}: {len(result.leads)} leads")
        except Exception as exc:
            if progress:
                progress(f"schedule {i} failed: {exc}")
    return {"schedules": len(list_schedules()), "new_leads": total}


if __name__ == "__main__":
    import sys

    cat = sys.argv[1] if len(sys.argv) > 1 else "ресторан"
    town = sys.argv[2] if len(sys.argv) > 2 else "Львів"
    res = find_leads(cat, town, limit=5, progress=lambda s: print("…", s))
    for lead in res.leads:
        autos = ", ".join(a["name"] for a in lead.automations) or "—"
        print(f"\n• {lead.company['name']}  [{lead.company.get('website') or 'no site'}]")
        print(f"   → {autos}")
