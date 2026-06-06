"""FastAPI dashboard: redesigned UI (uk/ru/en) with a Leaflet mini-map for
geo selection and like/save for prospects. Backed by the shared service layer.

Run:  uvicorn leadgen.app:app --reload --host 127.0.0.1 --port 8091
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from . import service
from .i18n import LANGS
from .service import (
    find_leads,
    find_leads_around,
    list_favorites,
    load_leads,
    passes_filters,
    remove_favorite,
    save_favorite,
    saved_ids,
)
from .sources.osm import CATEGORY_TAGS

app = FastAPI(title="LeadGen")
INDEX_PATH = Path(__file__).with_name("static") / "index.html"


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
    filters: Filters = Filters()


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
    try:
        res = find_leads(req.category, req.city, country=req.country, limit=req.limit,
                         lang=lang, enrich=req.enrich, require_website=req.require_website,
                         source=req.source)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(_apply_filters(_decorate([l.to_dict() for l in res]), req.filters))


@app.post("/api/find_around")
def api_find_around(req: FindAroundRequest):
    lang = req.lang if req.lang in LANGS else "uk"
    res = find_leads_around(req.category, req.lat, req.lon, radius_m=req.radius_m,
                            limit=req.limit, lang=lang, enrich=req.enrich,
                            require_website=req.require_website)
    return JSONResponse(_apply_filters(_decorate([l.to_dict() for l in res]), req.filters))


@app.get("/api/saved")
def api_saved():
    return JSONResponse(_decorate(list_favorites()))


@app.post("/api/save")
def api_save(req: SaveRequest):
    return JSONResponse({"id": save_favorite(req.lead)})


@app.post("/api/unsave")
def api_unsave(req: UnsaveRequest):
    return JSONResponse({"removed": remove_favorite(req.id)})


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_PATH.read_text(encoding="utf-8")
