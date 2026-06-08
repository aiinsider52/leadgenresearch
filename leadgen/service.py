"""Orchestration layer: discover → enrich → match. Both the web dashboard
and the Telegram bot call these functions so there is one code path.

Persists results to data/leads.jsonl. Analysis/outreach (Claude) plug in
here later; right now matching uses the free deterministic scorer.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .analyze.scoring import score_lead
from .catalog.match import Match, match_company
from .catalog.n8n_templates import recommend_templates
from .enrich.linkedin import enrich_people
from .enrich.site import enrich_site
from .i18n import resolve_category

# Office-based niches where OSM is sparse → auto-route to Google Maps.
OFFICE_NICHES = {"agency", "law", "real_estate", "education"}
from .sources.osm import Company, discover, discover_around

from .config import data_dir

DATA_DIR = data_dir()  # writable; falls back to /tmp on read-only hosts (Vercel)
LEADS_FILE = DATA_DIR / "leads.jsonl"
SAVED_FILE = DATA_DIR / "saved.json"


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
    for k in ("telegram", "decision_makers", "staff", "linkedin_profiles", "pages_crawled"):
        if extra.get(k):
            out[k] = extra[k]
    if extra.get("signals"):
        out["signals"] = extra["signals"]
    # Keep apify size_band but adopt crawled profile fields where richer.
    prof = dict(base.get("profile") or {})
    for k, v in (extra.get("profile") or {}).items():
        if v and not prof.get(k):
            prof[k] = v
    out["profile"] = prof
    return out


def _process(companies, lang: str, enrich: bool, progress, category: str = "",
             with_templates: bool = True) -> list[Lead]:
    # Live n8n templates depend on category only → fetch once, reuse (cached).
    templates: list[dict] = []
    if with_templates and category:
        try:
            templates = [t.to_dict() for t in recommend_templates(category)]
        except Exception:
            templates = []

    leads: list[Lead] = []
    for c in companies:
        enrichment: dict = {}
        # Apify already returns email/socials/reviews → use them as the base.
        prebuilt = getattr(c, "raw_tags", {}).get("_enrichment")
        if prebuilt:
            enrichment = dict(prebuilt)
        if enrich and c.website:
            if progress:
                progress(f"enrich:{c.name}")
            try:
                crawled = enrich_site(c.website, max_pages=4).to_dict()
                enrichment = _merge_enrichment(enrichment, crawled) if prebuilt else crawled
            except Exception as exc:  # network/parse issues shouldn't kill the batch
                if not prebuilt:
                    enrichment = {"error": str(exc)}
        if c.phone and not enrichment.get("phones"):
            enrichment.setdefault("phones", []).append(c.phone)
        # Attach LinkedIn profile + ready search links to each decision-maker.
        if enrichment.get("decision_makers"):
            enrich_people(enrichment["decision_makers"], c.name,
                          enrichment.get("linkedin_profiles", []))
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
    save_leads(leads)
    return leads


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
    progress: Optional[Callable[[str], None]] = None,
) -> list[Lead]:
    """Full free pipeline by city. `source` = 'osm' (default, reliable) or
    'gmaps' (richer: ratings/reviews/size, but experimental). gmaps falls
    back to OSM if Google blocks the request."""
    category = resolve_category(category_label) or category_label
    if source == "auto":  # office niches → Google Maps, physical places → OSM
        source = "gmaps" if category in OFFICE_NICHES else "osm"
    if progress:
        progress(f"discover:{source}:{category}:{city}")
    companies = []
    if source == "instagram":
        # IG-native niches: founders/personal brands + emails via Apify actor.
        from .sources.instagram import discover_instagram
        companies = discover_instagram(category_label, city, country=country, limit=limit, mode=ig_mode)
        for c in companies:
            c.category = category
    elif source == "gmaps":
        # Live Google Maps via headless browser — works worldwide incl. Ukraine.
        # Search with the user's RAW phrase ("marketing agency"), not the slug.
        # Deep-clicking is slow (~2s/result), so cap when also enriching to
        # avoid multi-minute requests that time out the browser.
        gmaps_limit = min(limit, 20) if enrich else min(limit, 30)
        try:
            from .sources.gmaps_playwright import discover_gmaps_pw
            companies = discover_gmaps_pw(category_label, city, country=country, limit=gmaps_limit)
            for c in companies:        # keep slug for matching/templates
                c.category = category
        except Exception as exc:
            if progress:
                progress(f"gmaps_failed:{exc}")
    if not companies and source != "instagram":  # default / fallback
        companies = discover(category, city, country=country, limit=limit,
                             require_website=require_website)
    return _process(companies, lang, enrich, progress, category=category)


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
) -> list[Lead]:
    """Full free pipeline around a map point (mini-map selection)."""
    category = resolve_category(category_label) or category_label
    if progress:
        progress(f"discover_around:{category}:{lat},{lon}")
    companies = discover_around(
        category, lat, lon, radius_m=radius_m, limit=limit, require_website=require_website
    )
    return _process(companies, lang, enrich, progress, category=category)


def save_leads(leads: list[Lead]) -> None:
    with open(LEADS_FILE, "a", encoding="utf-8") as f:
        for lead in leads:
            f.write(json.dumps(lead.to_dict(), ensure_ascii=False) + "\n")


def load_leads(limit: int = 200) -> list[dict]:
    if not LEADS_FILE.exists():
        return []
    by_id: dict[str, dict] = {}
    with open(LEADS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lead = json.loads(line)
                by_id[_lead_id(lead)] = lead   # dedupe: keep latest per company
    return list(by_id.values())[-limit:]


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

def _lead_id(lead: dict) -> str:
    """Stable id for dedupe: OSM id, else website, else name+city."""
    c = lead.get("company", {})
    return c.get("osm_id") or c.get("website") or f"{c.get('name')}|{c.get('city')}"


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
    return lid


def update_favorite(lead_id: str, **fields) -> bool:
    """Set tags / notes / status on a saved lead."""
    d = _read_saved()
    if lead_id not in d:
        return False
    for k in ("tags", "notes", "status"):
        if k in fields and fields[k] is not None:
            d[lead_id][k] = fields[k]
    _write_saved(d)
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


def find_leads_multi(category_label: str, cities: list[str], country: str = "Ukraine",
                     limit: int = 30, lang: str = "uk", enrich: bool = True,
                     source: str = "osm", ig_mode: str = "business",
                     progress: Optional[Callable[[str], None]] = None) -> list[Lead]:
    """Run the pipeline across several cities and merge, deduped by company.
    Splits the limit across cities so the total stays close to `limit`."""
    cities = [c.strip() for c in cities if c.strip()]
    per = max(limit // max(len(cities), 1), 3)
    seen: set[str] = set()
    out: list[Lead] = []
    for city in cities:
        if progress:
            progress(f"city:{city}")
        try:
            leads = find_leads(category_label, city, country=country, limit=per, lang=lang,
                               enrich=enrich, source=source, ig_mode=ig_mode, progress=progress)
        except Exception:
            continue
        for l in leads:
            lid = _lead_id(l.to_dict())
            if lid in seen:
                continue
            seen.add(lid)
            out.append(l)
    out.sort(key=lambda l: l.score.get("score", 0), reverse=True)
    return out


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

    return {
        "total_leads": len(allleads),
        "saved": len(saved),
        "with_email": with_email,
        "funnel": {s: funnel.get(s, 0) for s in PIPELINE_STATUSES},
        "by_tier": dict(by_tier),
        "by_source": dict(by_source),
        "by_city": dict(by_city.most_common(8)),
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
                                         "limit", "lang", "enrich", "source", "ig_mode")}
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
    """Run every saved search; new leads are appended (and deduped on read).
    Returns a summary. Intended to be called from cron."""
    total = 0
    for i, sc in enumerate(list_schedules()):
        cat = sc.get("category") or ""
        try:
            if sc.get("cities"):
                leads = find_leads_multi(cat, sc["cities"], country=sc.get("country", "Ukraine"),
                                         limit=sc.get("limit", 20), lang=sc.get("lang", "uk"),
                                         enrich=sc.get("enrich", True), source=sc.get("source", "osm"),
                                         ig_mode=sc.get("ig_mode", "business"), progress=progress)
            else:
                leads = find_leads(cat, sc.get("city", ""), country=sc.get("country", "Ukraine"),
                                   limit=sc.get("limit", 20), lang=sc.get("lang", "uk"),
                                   enrich=sc.get("enrich", True), source=sc.get("source", "osm"),
                                   ig_mode=sc.get("ig_mode", "business"), progress=progress)
            total += len(leads)
            if progress:
                progress(f"schedule {i}: {len(leads)} leads")
        except Exception as exc:
            if progress:
                progress(f"schedule {i} failed: {exc}")
    return {"schedules": len(list_schedules()), "new_leads": total}


if __name__ == "__main__":
    import sys

    cat = sys.argv[1] if len(sys.argv) > 1 else "ресторан"
    town = sys.argv[2] if len(sys.argv) > 2 else "Львів"
    res = find_leads(cat, town, limit=5, progress=lambda s: print("…", s))
    for lead in res:
        autos = ", ".join(a["name"] for a in lead.automations) or "—"
        print(f"\n• {lead.company['name']}  [{lead.company.get('website') or 'no site'}]")
        print(f"   → {autos}")
