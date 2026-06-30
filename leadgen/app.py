"""FastAPI dashboard: redesigned UI (uk/ru/en) with a Leaflet mini-map for
geo selection and like/save for prospects. Backed by the shared service layer.

Run:  uvicorn leadgen.app:app --reload --host 127.0.0.1 --port 8091
"""
from __future__ import annotations

import os
from pathlib import Path

import csv
import io
from typing import List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import llm, service, usage, storage, auth, search_guard, worker
from .search_response import package_search_result
from . import brave
from .enrich.brave_people import enrich_people_brave
from .enrich.brave_signals import enrich_news_signals
from .enrich.brave_intent import enrich_intent_signals
from .enrich.contact_quality import assess_contacts
from .analyze.company import analyze
from .analyze.qualify import qualify
from .analyze.scoring import score_lead
from .catalog.ai_recommender import ai_recommend
from .i18n import LANGS
from .outreach.writer import write_message
from .service import (
    UA_MAJOR_CITIES,
    add_schedule,
    find_leads,
    find_leads_around,
    find_leads_expanded,
    find_leads_multi,
    get_icp,
    list_favorites,
    list_schedules,
    load_leads,
    passes_filters,
    remove_favorite,
    remove_schedule,
    run_schedules,
    save_favorite,
    saved_ids,
    set_icp,
    stats,
    update_favorite,
)
from .pipeline_metrics import recent as recent_pipeline_metrics
from .history import recent as recent_history
from .sources.osm import CATEGORY_TAGS
from .agent import session as chat_session
from .agent.brain import run_agent, run_agent_stream
from . import campaigns
from .outreach import queue as outreach_queue
from .outreach.sender import process_queue, send_one
from .outreach.sequences import start_sequence, list_sequences
from .outreach.reply_handler import handle_reply, recent_replies
from .signals.listeners import poll_signals, list_recent_signals
from . import worker
from .db import init_schema, backend as db_backend

app = FastAPI(title="LeadGen Autopilot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.url.path not in (
        "/api/ai_status", "/api/categories",
    ):
        auth.check_request(request)
    return await call_next(request)
INDEX_PATH = Path(__file__).with_name("static") / "index.html"
STATIC_DIR = Path(__file__).with_name("static")


@app.on_event("startup")
def sync_structured_storage() -> None:
    try:
        init_schema()
        rows = load_leads(5000)
        storage.sync_leads([(service._lead_id(row), row) for row in rows])
    except Exception as exc:
        import logging
        logging.getLogger("leadgen").warning("startup sync skipped: %s", exc)


def _decorate(leads: list[dict]) -> list[dict]:
    """Attach stable id + saved flag so the UI can render hearts correctly."""
    saved = set(saved_ids())
    out = []
    for lead in leads:
        lid = service._lead_id(lead)
        out.append({**lead, "_id": lid, "_saved": lid in saved})
    return out


class Filters(BaseModel):
    email: bool = False
    phone: bool = False
    social: bool = False
    linkedin: bool = False
    telegram: bool = False
    dm: bool = False


class FindRequest(BaseModel):
    category: str
    city: str
    country: str = "Ukraine"
    limit: int = 20
    lang: str = "uk"
    enrich: bool = True
    require_website: bool = False
    source: str = "osm"
    ig_mode: str = "business"
    discover_websites: bool = True
    brave_people: bool = True
    brave_news: bool = True
    brave_intent: bool = True
    filters: Filters = Filters()
    search_seq: Optional[int] = None


class FindAroundRequest(BaseModel):
    category: str
    lat: float
    lon: float
    radius_m: int = 2000
    limit: int = 20
    lang: str = "uk"
    enrich: bool = True
    require_website: bool = False
    filters: Filters = Filters()
    search_seq: Optional[int] = None


def _apply_filters(leads: list[dict], f: Filters) -> list[dict]:
    if not any(f.model_dump().values()):
        return leads
    return [l for l in leads if passes_filters(l, **f.model_dump())]


class SaveRequest(BaseModel):
    lead: dict


class UnsaveRequest(BaseModel):
    id: str


@app.get("/api/categories")
def categories():
    return JSONResponse(sorted(CATEGORY_TAGS.keys()))


@app.get("/api/leads")
def leads(limit: int = 100):
    return JSONResponse(_decorate(load_leads(limit)))


@app.post("/api/find")
def api_find(req: FindRequest):
    lang = req.lang if req.lang in LANGS else "uk"
    search_guard.register_search(req.search_seq)
    try:
        res = find_leads(req.category, req.city, country=req.country, limit=req.limit,
                         lang=lang, enrich=req.enrich, require_website=req.require_website,
                         source=req.source, ig_mode=req.ig_mode,
                         discover_websites=req.discover_websites,
                         brave_people=req.brave_people, brave_news=req.brave_news,
                         brave_intent=req.brave_intent, search_seq=req.search_seq)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    body = package_search_result(res, req.filters.model_dump())
    return JSONResponse(body)


@app.post("/api/find_around")
def api_find_around(req: FindAroundRequest):
    lang = req.lang if req.lang in LANGS else "uk"
    search_guard.register_search(req.search_seq)
    res = find_leads_around(req.category, req.lat, req.lon, radius_m=req.radius_m,
                            limit=req.limit, lang=lang, enrich=req.enrich,
                            require_website=req.require_website, search_seq=req.search_seq)
    body = package_search_result(res, req.filters.model_dump())
    return JSONResponse(body)


@app.get("/api/saved")
def api_saved():
    return JSONResponse(_decorate(list_favorites()))


@app.post("/api/save")
def api_save(req: SaveRequest):
    return JSONResponse({"id": save_favorite(req.lead)})


@app.post("/api/unsave")
def api_unsave(req: UnsaveRequest):
    return JSONResponse({"removed": remove_favorite(req.id)})


class UpdateSavedRequest(BaseModel):
    id: str
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    status: Optional[str] = None


@app.post("/api/update_saved")
def api_update_saved(req: UpdateSavedRequest):
    ok = update_favorite(req.id, tags=req.tags, notes=req.notes, status=req.status)
    return JSONResponse({"updated": ok})


class OutreachRequest(BaseModel):
    lead: dict
    person_index: int = 0
    channel: str = "email"
    lang: str = "uk"


@app.post("/api/outreach")
def api_outreach(req: OutreachRequest):
    lang = req.lang if req.lang in LANGS else "uk"
    return JSONResponse(write_message(req.lead, req.person_index, req.channel, lang))


class AnalyzeRequest(BaseModel):
    lead: dict
    lang: str = "uk"


@app.post("/api/analyze")
def api_analyze(req: AnalyzeRequest):
    lang = req.lang if req.lang in LANGS else "uk"
    return JSONResponse(analyze(req.lead, lang))


class RecommendRequest(BaseModel):
    lead: dict
    lang: str = "uk"


@app.post("/api/recommend")
def api_recommend(req: RecommendRequest):
    lang = req.lang if req.lang in LANGS else "uk"
    recs = ai_recommend(req.lead, lang)
    if recs is None:  # no key/failure → fall back to the lead's deterministic ones
        recs = [{"name": a["name"], "pitch": a["pitch"], "template": None, "ai": False}
                for a in (req.lead.get("automations") or [])[:3]]
    return JSONResponse({"recommendations": recs, "ai": bool(recs and recs[0].get("ai"))})


class FindMultiRequest(BaseModel):
    category: str
    cities: List[str] = []
    country: str = "Ukraine"
    limit: int = 30
    lang: str = "uk"
    enrich: bool = True
    source: str = "osm"
    ig_mode: str = "business"
    discover_websites: bool = True
    brave_people: bool = True
    brave_news: bool = True
    brave_intent: bool = True
    filters: Filters = Filters()
    search_seq: Optional[int] = None


@app.post("/api/find_multi")
def api_find_multi(req: FindMultiRequest):
    lang = req.lang if req.lang in LANGS else "uk"
    cities = req.cities or UA_MAJOR_CITIES
    search_guard.register_search(req.search_seq)
    try:
        res = find_leads_multi(req.category, cities, country=req.country, limit=req.limit,
                               lang=lang, enrich=req.enrich, source=req.source, ig_mode=req.ig_mode,
                               discover_websites=req.discover_websites,
                               brave_people=req.brave_people, brave_news=req.brave_news,
                               brave_intent=req.brave_intent, search_seq=req.search_seq)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    body = package_search_result(res, req.filters.model_dump())
    return JSONResponse(body)


class FindExpandedRequest(BaseModel):
    category: str
    city: str = ""
    cities: List[str] = []
    country: str = "Ukraine"
    limit: int = 40
    lang: str = "uk"
    enrich: bool = True
    source: str = "osm"
    ig_mode: str = "business"
    discover_websites: bool = True
    brave_people: bool = True
    brave_news: bool = True
    brave_intent: bool = True
    filters: Filters = Filters()
    search_seq: Optional[int] = None


@app.post("/api/find_expanded")
def api_find_expanded(req: FindExpandedRequest):
    lang = req.lang if req.lang in LANGS else "uk"
    search_guard.register_search(req.search_seq)
    try:
        res = find_leads_expanded(req.category, req.city, country=req.country, limit=req.limit,
                                  lang=lang, enrich=req.enrich, source=req.source,
                                  ig_mode=req.ig_mode, cities=(req.cities or None),
                                  discover_websites=req.discover_websites,
                                  brave_people=req.brave_people, brave_news=req.brave_news,
                                  brave_intent=req.brave_intent, search_seq=req.search_seq)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    body = package_search_result(res, req.filters.model_dump())
    return JSONResponse(body)


class SearchSubmitRequest(BaseModel):
    endpoint: str
    params: dict = {}
    filters: Filters = Filters()
    search_seq: Optional[int] = None


@app.post("/api/search")
def api_search_async(req: SearchSubmitRequest):
    """Start async search; poll GET /api/jobs/{job_id} for {status, result}."""
    search_guard.register_search(req.search_seq)
    jid = worker.submit_search(
        req.endpoint,
        req.params,
        req.filters.model_dump(),
        search_seq=req.search_seq,
    )
    return JSONResponse({"job_id": jid, "search_seq": req.search_seq, "status": "pending"})


@app.post("/api/jobs/{job_id}/cancel")
def api_cancel_job(job_id: str):
    ok = worker.cancel_job(job_id)
    if not ok:
        return JSONResponse({"error": "not cancellable"}, status_code=409)
    return JSONResponse({"cancelled": True, "job_id": job_id})


@app.get("/api/stats")
def api_stats():
    return JSONResponse(stats())


@app.get("/api/pipeline_metrics")
def api_pipeline_metrics(limit: int = 50):
    return JSONResponse(recent_pipeline_metrics(limit))


@app.get("/api/history")
def api_history(lead_id: Optional[str] = None, limit: int = 100):
    return JSONResponse(recent_history(lead_id, limit))


@app.get("/api/storage/status")
def api_storage_status():
    return JSONResponse(storage.status())


@app.get("/api/usage")
def api_usage():
    return JSONResponse(usage.summary())


@app.get("/api/brave/status")
def api_brave_status():
    return JSONResponse(brave.status())


class BraveEnrichRequest(BaseModel):
    lead: dict
    people: bool = True
    news: bool = True
    intent: bool = True


@app.post("/api/brave/enrich")
def api_brave_enrich(req: BraveEnrichRequest):
    if not brave.available():
        return JSONResponse({"error": "BRAVE_SEARCH_API_KEY not set"}, status_code=400)
    lead = req.lead
    company = lead.get("company", {}) or {}
    enrichment = dict(lead.get("enrichment", {}) or {})
    if req.people:
        enrichment = enrich_people_brave(
            enrichment, company.get("name", ""), company.get("website"), max_queries=4
        )
    if req.news:
        enrichment = enrich_news_signals(enrichment, company.get("name", ""))
    if req.intent:
        enrichment = enrich_intent_signals(enrichment, company.get("name", ""), company.get("website"))
    enrichment = assess_contacts(enrichment, company.get("website"))
    company["sources"] = sorted(set(company.get("sources") or []) | {"brave_web"})
    enriched = {**lead, "company": company, "enrichment": enrichment,
                "score": score_lead(company, enrichment)}
    service.save_leads([service.Lead(
        company=company, enrichment=enrichment,
        automations=enriched.get("automations") or [],
        templates=enriched.get("templates") or [],
        score=enriched["score"], lang=enriched.get("lang", "uk"),
    )])
    return JSONResponse(_decorate([enriched])[0])


@app.get("/api/icp")
def api_get_icp():
    return JSONResponse({"icp": get_icp()})


class IcpRequest(BaseModel):
    icp: str


@app.post("/api/icp")
def api_set_icp(req: IcpRequest):
    set_icp(req.icp)
    return JSONResponse({"saved": True})


class QualifyRequest(BaseModel):
    lead: dict
    lang: str = "uk"


@app.post("/api/qualify")
def api_qualify(req: QualifyRequest):
    lang = req.lang if req.lang in LANGS else "uk"
    res = qualify(req.lead, lang)
    return JSONResponse(res or {"fit": None, "ai": False})


class SaveBulkRequest(BaseModel):
    leads: List[dict]


@app.post("/api/save_bulk")
def api_save_bulk(req: SaveBulkRequest):
    ids = [save_favorite(l) for l in req.leads]
    return JSONResponse({"saved": len(ids), "ids": ids})


@app.get("/api/schedules")
def api_list_schedules():
    return JSONResponse(list_schedules())


class ScheduleRequest(BaseModel):
    search: dict


@app.post("/api/schedules")
def api_add_schedule(req: ScheduleRequest):
    return JSONResponse(add_schedule(req.search))


@app.delete("/api/schedules/{index}")
def api_remove_schedule(index: int):
    return JSONResponse(remove_schedule(index))


@app.post("/api/run_schedules")
def api_run_schedules():
    return JSONResponse(run_schedules())


@app.get("/api/ai_status")
def api_ai_status():
    from .config import get
    st = llm.status()
    st["waterfall"] = get("USE_WATERFALL", "").lower() in ("1", "true", "yes")
    return JSONResponse(st)


@app.get("/api/export.csv")
def api_export(scope: str = "saved"):
    leads = list_favorites() if scope == "saved" else load_leads(500)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name", "category", "city", "address", "website", "rating", "reviews",
                "size", "score", "tier", "emails", "phones", "linkedin", "telegram",
                "decision_makers", "tags", "status", "notes"])
    for ld in leads:
        c, en = ld.get("company", {}), ld.get("enrichment", {})
        sc = ld.get("score", {})
        w.writerow([
            c.get("name"), c.get("gmaps_category") or c.get("category"), c.get("city"),
            c.get("address"), c.get("website"), c.get("rating"), c.get("reviews"),
            (en.get("profile", {}) or {}).get("size_band") or c.get("size_band"),
            sc.get("score"), sc.get("tier"),
            "; ".join(en.get("emails", [])), "; ".join(en.get("phones", [])),
            (en.get("socials", {}) or {}).get("linkedin", ""),
            "; ".join("@" + h for h in en.get("telegram", [])),
            "; ".join(p.get("name", "") for p in en.get("decision_makers", [])),
            "; ".join(ld.get("tags", [])), ld.get("status", ""), ld.get("notes", ""),
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=leadgen_{scope}.csv"},
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return HTMLResponse(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="24" height="24" rx="6" fill="#0A0A0F"/><path d="M4 14h4l2-5 4 10 2-5h4" fill="none" stroke="#E8B84B" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        media_type="image/svg+xml",
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        INDEX_PATH.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
    )


# ---- Agent chat ----

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    lang: str = "uk"


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    lang = req.lang if req.lang in LANGS else "uk"
    sid = req.session_id or chat_session.create_session(lang)
    reply = run_agent(sid, req.message, lang=lang)
    return JSONResponse({"session_id": sid, "reply": reply})


@app.post("/api/chat/stream")
def api_chat_stream(req: ChatRequest):
    lang = req.lang if req.lang in LANGS else "uk"
    sid = req.session_id or chat_session.create_session(lang)
    return StreamingResponse(
        run_agent_stream(sid, req.message, lang=lang),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Session-Id": sid},
    )


@app.get("/api/chat/sessions")
def api_chat_sessions(limit: int = 20):
    return JSONResponse(chat_session.list_sessions(limit))


@app.get("/api/chat/{session_id}")
def api_chat_history(session_id: str):
    sess = chat_session.get_session(session_id)
    if not sess:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(sess)


# ---- Campaigns ----

class CampaignCreateRequest(BaseModel):
    name: str
    category: str
    cities: List[str]
    source: str = "all_sources"
    limit_per_run: int = 50
    cron: str = "0 7 * * *"
    auto_outreach: bool = False
    expand_niche: bool = True
    lang: str = "uk"
    discover_websites: bool = True
    brave_people: bool = True
    brave_news: bool = True
    brave_intent: bool = True


@app.get("/api/campaigns")
def api_list_campaigns():
    from .campaigns import CRON_PRESETS
    return JSONResponse({"campaigns": campaigns.list_campaigns(), "cron_presets": CRON_PRESETS})


@app.post("/api/campaigns")
def api_create_campaign(req: CampaignCreateRequest):
    cid = campaigns.create_campaign(
        req.name, req.category, req.cities,
        source=req.source, limit_per_run=req.limit_per_run,
        cron=req.cron, auto_outreach=req.auto_outreach,
        expand_niche=req.expand_niche, lang=req.lang,
        discover_websites=req.discover_websites,
        brave_people=req.brave_people, brave_news=req.brave_news,
        brave_intent=req.brave_intent,
    )
    return JSONResponse({"campaign_id": cid})


@app.post("/api/campaigns/{campaign_id}/run")
def api_run_campaign(campaign_id: str):
    return JSONResponse(campaigns.run_campaign(campaign_id))


@app.post("/api/campaigns/{campaign_id}/pause")
def api_pause_campaign(campaign_id: str):
    return JSONResponse({"paused": campaigns.pause_campaign(campaign_id)})


@app.post("/api/campaigns/{campaign_id}/resume")
def api_resume_campaign(campaign_id: str):
    return JSONResponse({"resumed": campaigns.resume_campaign(campaign_id)})


@app.delete("/api/campaigns/{campaign_id}")
def api_delete_campaign(campaign_id: str):
    return JSONResponse({"deleted": campaigns.delete_campaign(campaign_id)})


@app.post("/api/campaigns/run_due")
def api_run_due_campaigns():
    return JSONResponse({"results": campaigns.run_due_campaigns()})


@app.get("/api/campaigns/runs")
def api_campaign_runs(limit: int = 20):
    return JSONResponse(campaigns.recent_runs(limit))


# ---- Outreach queue ----

@app.get("/api/outreach/queue")
def api_outreach_queue(status: Optional[str] = None, limit: int = 50):
    return JSONResponse(outreach_queue.list_queue(status, limit))


@app.post("/api/outreach/send/{queue_id}")
def api_outreach_send_one(queue_id: str):
    return JSONResponse(send_one(queue_id))


@app.post("/api/outreach/process")
def api_outreach_process(limit: int = 10):
    return JSONResponse(process_queue(limit=limit))


class SequenceRequest(BaseModel):
    lead_id: str
    channel: str = "email"
    lang: str = "uk"


@app.post("/api/outreach/sequence")
def api_outreach_sequence(req: SequenceRequest):
    lang = req.lang if req.lang in LANGS else "uk"
    sid = start_sequence(req.lead_id, channel=req.channel, lang=lang)
    return JSONResponse({"sequence_id": sid})


@app.get("/api/outreach/sequences")
def api_outreach_sequences():
    return JSONResponse(list_sequences())


class ReplyRequest(BaseModel):
    lead_id: str
    reply_text: str
    lang: str = "uk"


@app.post("/api/outreach/reply")
def api_outreach_reply(req: ReplyRequest):
    lang = req.lang if req.lang in LANGS else "uk"
    return JSONResponse(handle_reply(req.lead_id, req.reply_text, lang=lang))


@app.get("/api/outreach/replies")
def api_outreach_replies(limit: int = 50):
    return JSONResponse(recent_replies(limit))


# ---- Signals ----

@app.post("/api/signals/poll")
def api_signals_poll():
    return JSONResponse(poll_signals())


@app.get("/api/signals/recent")
def api_signals_recent(limit: int = 20):
    return JSONResponse(list_recent_signals(limit))


# ---- Background jobs ----

class JobRequest(BaseModel):
    kind: str
    payload: dict = {}


@app.post("/api/jobs")
def api_submit_job(req: JobRequest):
    jid = worker.submit(req.kind, req.payload)
    return JSONResponse({"job_id": jid})


@app.get("/api/jobs/{job_id}")
def api_get_job(job_id: str):
    job = worker.get_job(job_id)
    if not job:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(job)


@app.get("/api/jobs")
def api_list_jobs(limit: int = 20):
    return JSONResponse(worker.list_jobs(limit))


@app.get("/api/db/status")
def api_db_status():
    return JSONResponse({"backend": db_backend()})


@app.get("/api/health")
def api_health():
    return JSONResponse({"ok": True, "vercel": bool(os.environ.get("VERCEL"))})


# Static assets live in leadgen/static/ next to this module — serve on Vercel too
# (CDN via public/static/ is optional; the package bundle is the reliable source).
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
