"""Shared Playwright route mocks for async search (ISS-004)."""
from __future__ import annotations

import json
import re
from typing import Any

SEARCH_POST = re.compile(r".*/api/search$")
JOBS_GET = re.compile(r".*/api/jobs/[^/]+$")
JOBS_CANCEL = re.compile(r".*/api/jobs/[^/]+/cancel$")

MOCK_META = {
    "requested_limit": 100,
    "returned": 1,
    "discovered_raw": 3,
    "deduped_before_enrichment": 2,
    "capped": True,
    "cap_reason": "source_exhausted",
    "after_filters": 1,
}


def mock_lead(lead_id: str, name: str) -> dict:
    return {
        "_id": lead_id,
        "company": {"name": name, "city": "Київ", "source": "osm"},
        "enrichment": {},
        "score": {"score": 55, "tier": "warm"},
    }


def install_instant_search_mock(page, leads: list[dict], meta: dict | None = None,
                                counters: dict | None = None) -> None:
    """Fulfill POST /api/search + GET job poll without hitting the worker."""
    meta = meta or {"requested_limit": 5, "returned": len(leads), "capped": False,
                    "cap_reason": None, "discovered_raw": len(leads),
                    "deduped_before_enrichment": len(leads), "after_filters": len(leads)}
    job_id = "mock-search-job"

    def handler(route):
        url = route.request.url
        if SEARCH_POST.match(url) and route.request.method == "POST":
            if counters is not None:
                counters["search_posts"] = counters.get("search_posts", 0) + 1
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"job_id": job_id, "status": "pending", "search_seq": 1}),
            )
        elif JOBS_CANCEL.match(url):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"cancelled": True, "job_id": job_id}))
        elif JOBS_GET.match(url) and route.request.method == "GET":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "id": job_id,
                    "status": "done",
                    "result": {"leads": leads, "meta": meta},
                }),
            )
        else:
            route.continue_()

    page.route(SEARCH_POST, handler)
    page.route(JOBS_GET, handler)
    page.route(JOBS_CANCEL, handler)


def install_hanging_search_post(page, pending: list, counters: dict) -> None:
    def hang(route):
        counters["search_posts"] = counters.get("search_posts", 0) + 1
        pending.append(route)

    page.route(SEARCH_POST, hang)
