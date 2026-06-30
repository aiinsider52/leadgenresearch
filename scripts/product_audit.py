#!/usr/bin/env python3
"""Real product audit — running app only. Playwright + HTTP + stress + adversarial."""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import sync_playwright, Route, Request, Response

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent.parent / "data" / "product_audit"
OUT.mkdir(parents=True, exist_ok=True)
SHOTS = OUT / "screenshots"
VIDEOS = OUT / "videos"
SHOTS.mkdir(exist_ok=True)
VIDEOS.mkdir(exist_ok=True)

RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT: dict[str, Any] = {
    "run_id": RUN_ID,
    "started": datetime.now(timezone.utc).isoformat(),
    "base_url": BASE,
    "sitemap": {},
    "features": [],
    "issues": [],
    "stress": [],
    "adversarial": [],
    "network_log": [],
    "console_log": [],
}


@dataclass
class FeatureResult:
    name: str
    ok: bool
    duration_ms: float
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    api_calls: list[dict] = field(default_factory=list)
    screenshot: str = ""
    notes: str = ""


@dataclass
class Issue:
    id: str
    severity: str
    title: str
    reproduction: list[str]
    expected: str
    actual: str
    evidence: str
    screenshot: str
    affected_api: str
    possible_root_cause: str
    business_impact: str
    suggested_solution: str


def add_issue(**kw) -> None:
    REPORT["issues"].append(asdict(Issue(id=f"ISS-{len(REPORT['issues'])+1:03d}", **kw)))


def http(method: str, path: str, **kw) -> dict:
    t0 = time.perf_counter()
    try:
        r = requests.request(method, BASE + path, timeout=kw.pop("timeout", 180), **kw)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        body = None
        try:
            body = r.json()
        except Exception:
            body = (r.text or "")[:500]
        return {"method": method, "path": path, "status": r.status_code, "ms": ms,
                "ok": 200 <= r.status_code < 300, "body_preview": str(body)[:300]}
    except Exception as exc:
        return {"method": method, "path": path, "status": 0, "ms": round((time.perf_counter() - t0) * 1000, 1),
                "ok": False, "error": str(exc)}


def discover_sitemap_via_http() -> None:
    """Map API surface from OpenAPI-less discovery: known paths + HTML link scan."""
    apis = [
        "GET /", "GET /api/categories", "GET /api/leads", "GET /api/saved", "GET /api/stats",
        "GET /api/pipeline_metrics", "GET /api/history", "GET /api/storage/status",
        "GET /api/usage", "GET /api/brave/status", "GET /api/icp", "GET /api/schedules",
        "GET /api/ai_status", "GET /api/export.csv", "GET /api/chat/sessions",
        "GET /api/campaigns", "GET /api/campaigns/runs", "GET /api/outreach/queue",
        "GET /api/outreach/sequences", "GET /api/outreach/replies", "GET /api/signals/recent",
        "GET /api/jobs", "GET /api/db/status",
    ]
    api_results = []
    for item in apis:
        m, p = item.split(" ", 1)
        api_results.append(http(m, p, timeout=60))
    REPORT["sitemap"]["api_endpoints"] = api_results

    r = requests.get(BASE + "/", timeout=30)
    ids = sorted(set(re.findall(r'id="([^"]+)"', r.text)))
    classes = sorted(set(re.findall(r'class="([^"]*modal[^"]*)"', r.text, re.I)))
    REPORT["sitemap"]["html_element_ids"] = ids
    REPORT["sitemap"]["ui_surfaces"] = {
        "pages_tabs": ["search", "agent", "all", "saved"],
        "modals": [i for i in ids if "modal" in i.lower() or i in ("stats", "cmdPalette", "leadModal")],
        "drawers": [i for i in ids if "drawer" in i.lower()],
        "panels": [i for i in ids if "Panel" in i],
        "forms": [i for i in ids if "Form" in i or i in ("searchForm", "agentForm")],
    }


def _parse_find_response(data):
    if isinstance(data, dict) and "leads" in data:
        return len(data["leads"]), data.get("meta")
    if isinstance(data, list):
        return len(data), None
    return 0, None


def stress_search_limits() -> None:
    limits = [10, 50, 100, 250, 500]
    for limit in limits:
        t0 = time.perf_counter()
        res = http("POST", "/api/find", json={
            "category": "agency", "city": "Київ", "limit": limit,
            "source": "osm", "enrich": False,
        }, timeout=300)
        wall = round((time.perf_counter() - t0) * 1000, 1)
        count = 0
        meta = None
        if res.get("ok") and isinstance(res.get("body_preview"), str):
            try:
                import ast
                data = ast.literal_eval(res["body_preview"].split("...")[0] + "]") if "[" in res["body_preview"] else []
                count = len(data) if isinstance(data, list) else 0
            except Exception:
                pass
        # re-fetch properly
        try:
            r = requests.post(BASE + "/api/find", json={
                "category": "agency", "city": "Київ", "limit": limit,
                "source": "osm", "enrich": False,
            }, timeout=300)
            if r.ok:
                count, meta = _parse_find_response(r.json())
        except Exception as exc:
            res["error"] = str(exc)
        REPORT["stress"].append({
            "test": f"osm_search_limit_{limit}",
            "limit": limit,
            "wall_ms": wall,
            "api_ms": res.get("ms"),
            "status": res.get("status"),
            "leads_returned": count,
            "meta": meta,
            "ok": res.get("ok", False),
        })


def adversarial_http() -> None:
    tests = [
        ("double_find_concurrent", lambda: _concurrent_finds(3)),
        ("empty_find", lambda: http("POST", "/api/find", json={})),
        ("huge_chat", lambda: http("POST", "/api/chat", json={"message": "x" * 100_000, "lang": "uk"}, timeout=60)),
        ("invalid_json_lead", lambda: http("POST", "/api/save", json={"lead": None})),
        ("campaign_fake_id", lambda: http("POST", "/api/campaigns/fake99/run")),
    ]
    for name, fn in tests:
        try:
            result = fn()
            REPORT["adversarial"].append({"name": name, "result": result})
        except Exception as exc:
            REPORT["adversarial"].append({"name": name, "error": str(exc)})


def _concurrent_finds(n: int) -> list:
    import concurrent.futures
    payload = {"category": "agency", "city": "Київ", "limit": 5, "source": "osm", "enrich": False}
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
        futs = [ex.submit(requests.post, BASE + "/api/find", json=payload, timeout=120) for _ in range(n)]
        for f in concurrent.futures.as_completed(futs):
            try:
                r = f.result()
                body = r.json() if r.ok else {}
                cnt, _ = _parse_find_response(body)
                results.append({"status": r.status_code, "len": cnt})
            except Exception as exc:
                results.append({"error": str(exc)})
    return results


def run_playwright_audit() -> None:
    net_log: list[dict] = []
    console_log: list[dict] = []
    features: list[dict] = []

    def on_request(req: Request) -> None:
        if "/api/" in req.url or req.url.rstrip("/") == BASE:
            net_log.append({"t": time.time(), "method": req.method, "url": req.url})

    def on_response(res: Response) -> None:
        if "/api/" in res.url:
            net_log.append({"t": time.time(), "status": res.status, "url": res.url})

    def on_console(msg) -> None:
        console_log.append({"type": msg.type, "text": msg.text})

    video_path = str(VIDEOS / f"journey_{RUN_ID}.webm")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            color_scheme="dark",
            record_video_dir=str(VIDEOS),
            record_video_size={"width": 1440, "height": 900},
        )
        page = ctx.new_page()
        page.on("request", on_request)
        page.on("response", on_response)
        page.on("console", on_console)

        def feat(name: str, fn) -> None:
            t0 = time.perf_counter()
            errs: list[str] = []
            try:
                fn()
                ok = True
            except Exception as exc:
                ok = False
                errs.append(str(exc))
            ms = round((time.perf_counter() - t0) * 1000, 1)
            shot = SHOTS / f"{len(features)+1:02d}_{name}.png"
            try:
                page.screenshot(path=str(shot), full_page=True)
            except Exception:
                shot = ""
            features.append(FeatureResult(name=name, ok=ok, duration_ms=ms, errors=errs,
                                          screenshot=str(shot)).__dict__)

        # Load
        page.goto(BASE, wait_until="networkidle", timeout=90000)
        feat("dashboard_load", lambda: None)

        # Tabs sitemap
        for tab in ["search", "all", "saved", "agent"]:
            feat(f"tab_{tab}", lambda t=tab: page.click(f'.tabbtn[data-tab="{t}"]', timeout=10000))

        # Search OSM small
        page.click('.tabbtn[data-tab="search"]')
        page.fill("#category", "agency")
        page.fill("#city", "Київ")
        page.evaluate("localStorage.setItem('lg_src','osm')")

        def do_search():
            page.locator("#runCity").click()
            page.wait_for_selector('.lead-card[data-hydrated="true"], .lead-card, #empty', timeout=180000)

        feat("search_osm_10", do_search)

        # Wait for cards not skeleton
        page.wait_for_timeout(3000)
        cards = page.locator(".lead-card").count()

        # Lead detail
        def open_lead():
            if page.locator(".lead-card").count() == 0:
                raise RuntimeError("no cards")
            page.locator(".lead-card").first.click()
            page.wait_for_timeout(800)
            hidden = page.locator("#leadModal").evaluate("el => el.classList.contains('hidden')")
            if hidden:
                raise RuntimeError("modal did not open")

        feat("lead_detail_modal", open_lead)

        # Analyze in modal if button exists
        def analyze_btn():
            btn = page.locator("#leadAnalyze, [data-action='analyze'], button:has-text('Аналіз')")
            if btn.count():
                btn.first.click()
                page.wait_for_timeout(5000)
        feat("lead_analyze", analyze_btn)
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)

        # Save
        def save_lead():
            if page.locator(".lead-card .heart").count():
                page.locator(".lead-card .heart").first.click()
                page.wait_for_timeout(500)
        feat("save_lead", save_lead)

        # Bulk select if checkboxes
        def bulk():
            cbs = page.locator(".lead-card input[type=checkbox]")
            if cbs.count() >= 2:
                cbs.nth(0).click()
                cbs.nth(1).click()
        feat("bulk_select", bulk)

        # Analytics
        def stats():
            page.click("#statsBtnSide", timeout=5000)
            page.wait_for_timeout(1000)
            if page.locator("#stats").evaluate("el => el.classList.contains('hidden')"):
                raise RuntimeError("stats modal not open")
        feat("analytics_modal", stats)
        feat("analytics_campaigns_section", lambda: page.locator("#campCreate").is_visible())
        page.keyboard.press("Escape")

        # Agent
        def agent():
            page.click('.tabbtn[data-tab="agent"]')
            page.fill("#agentInput", "статистика")
            page.locator("#agentForm").evaluate("f => f.requestSubmit()")
            page.wait_for_timeout(6000)
        feat("agent_chat", agent)

        # Cmd palette
        def cmdk():
            page.keyboard.press("Meta+k")
            page.wait_for_timeout(400)
            if not page.locator("#cmdPalette").is_visible():
                raise RuntimeError("palette not visible")
            page.keyboard.press("Escape")
        feat("cmd_palette", cmdk)

        # Map search here button
        def map_btn():
            page.click('.tabbtn[data-tab="search"]')
            if page.locator("#searchHere").count():
                page.locator("#searchHere").click()
                page.wait_for_timeout(8000)
        feat("map_search_here", map_btn)

        # Theme toggle
        feat("light_theme", lambda: (page.click("#theme"), page.wait_for_timeout(500)))

        # Mobile
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(BASE, wait_until="networkidle", timeout=60000)
        feat("mobile_375", lambda: None)

        # Adversarial UI: spam search button
        def spam_search():
            page.set_viewport_size({"width": 1440, "height": 900})
            page.goto(BASE, wait_until="domcontentloaded")
            page.click('.tabbtn[data-tab="search"]')
            for _ in range(5):
                page.locator("#runCity").click(force=True)
                page.wait_for_timeout(200)
        feat("adversarial_spam_search", spam_search)

        ctx.close()
        browser.close()

    REPORT["features"] = features
    REPORT["network_log"] = net_log[-200:]
    REPORT["console_log"] = console_log

    # Issue detection from features
    for f in features:
        if not f["ok"]:
            add_issue(
                severity="medium" if "modal" in f["name"] else "high",
                title=f"Feature failed: {f['name']}",
                reproduction=[f"Run Playwright step: {f['name']}"],
                expected="Step completes without error",
                actual=f["errors"][0] if f["errors"] else "unknown",
                evidence=f"duration_ms={f['duration_ms']}",
                screenshot=f.get("screenshot", ""),
                affected_api="UI",
                possible_root_cause="Timing/race or missing element",
                business_impact="User cannot complete workflow step",
                suggested_solution="Add wait for data load before interaction",
            )

    for c in console_log:
        if c["type"] == "error":
            add_issue(
                severity="low",
                title=f"Console error: {c['text'][:80]}",
                reproduction=["Open dashboard", "Check browser console"],
                expected="No console errors",
                actual=c["text"][:200],
                evidence="console_log",
                screenshot="",
                affected_api="frontend",
                possible_root_cause="JS runtime error",
                business_impact="Potential broken UI paths",
                suggested_solution="Fix JS error",
            )


def api_feature_suite() -> None:
    """Execute backend features via HTTP as customer API would."""
    lead_r = requests.get(BASE + "/api/leads", timeout=60)
    lead = lead_r.json()[0] if lead_r.ok and lead_r.json() else None
    suite = []

    def run(name, method, path, **kw):
        t0 = time.perf_counter()
        res = http(method, path, **kw)
        res["feature"] = name
        res["wall_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        suite.append(res)
        if not res.get("ok"):
            add_issue(
                severity="high",
                title=f"API failed: {name}",
                reproduction=[f"{method} {path}", str(kw.get("json", ""))[:100]],
                expected="2xx response",
                actual=f"status {res.get('status')} {res.get('error', res.get('body_preview', ''))[:100]}",
                evidence=json.dumps(res)[:200],
                screenshot="",
                affected_api=f"{method} {path}",
                possible_root_cause="Validation, timeout, or server error",
                business_impact=f"Feature {name} unavailable",
                suggested_solution="Fix API handler or payload contract",
            )
        return res

    run("search_osm_5", "POST", "/api/find", json={"category": "agency", "city": "Київ", "limit": 5, "source": "osm", "enrich": False})
    run("signals_poll", "POST", "/api/signals/poll", json={})
    run("campaigns_list", "GET", "/api/campaigns")
    cid = None
    cr = run("campaign_create", "POST", "/api/campaigns", json={
        "name": f"audit-{uuid.uuid4().hex[:6]}", "category": "agency", "cities": ["Київ"],
        "limit_per_run": 3, "cron": "0 7 * * *", "expand_niche": False,
    })
    if cr.get("ok"):
        camps = requests.get(BASE + "/api/campaigns").json()
        if camps.get("campaigns"):
            cid = camps["campaigns"][-1]["id"]
    if cid:
        run("campaign_run", "POST", f"/api/campaigns/{cid}/run", timeout=300)
        run("campaign_pause", "POST", f"/api/campaigns/{cid}/pause")
        run("campaign_delete", "DELETE", f"/api/campaigns/{cid}")
    run("schedules_list", "GET", "/api/schedules")
    run("run_schedules", "POST", "/api/run_schedules")
    run("outreach_queue", "GET", "/api/outreach/queue")
    run("outreach_process", "POST", "/api/outreach/process")
    if lead:
        run("analyze", "POST", "/api/analyze", json={"lead": lead, "lang": "uk"}, timeout=90)
        run("recommend", "POST", "/api/recommend", json={"lead": lead, "lang": "uk"}, timeout=90)
        run("outreach_gen", "POST", "/api/outreach", json={"lead": lead, "lang": "uk", "channel": "email", "person_index": 0}, timeout=90)
        run("qualify", "POST", "/api/qualify", json={"lead": lead, "lang": "uk"}, timeout=60)
        run("save", "POST", "/api/save", json={"lead": lead})
    run("agent_chat", "POST", "/api/chat", json={"message": "статистика", "lang": "uk"}, timeout=120)
    run("export_csv", "GET", "/api/export.csv?scope=saved")

    usage_before = requests.get(BASE + "/api/usage").json()
    storage = requests.get(BASE + "/api/storage/status").json()
    REPORT["api_features"] = suite
    REPORT["usage_snapshot"] = usage_before
    REPORT["storage_snapshot"] = storage


def rank_issues() -> None:
    severity_weight = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    for iss in REPORT["issues"]:
        sev = severity_weight.get(iss["severity"], 1)
        iss["roi_score"] = sev * 10
        iss["priority_rank"] = sev
    REPORT["issues"].sort(key=lambda x: -x.get("roi_score", 0))


def main() -> None:
    print("Step 1: Sitemap discovery...")
    discover_sitemap_via_http()
    print("Step 3-4: API feature suite...")
    api_feature_suite()
    print("Step 5: Stress tests...")
    stress_search_limits()
    print("Step 6: Adversarial HTTP...")
    adversarial_http()
    print("Step 2-4: Playwright journey...")
    run_playwright_audit()
    rank_issues()
    REPORT["finished"] = datetime.now(timezone.utc).isoformat()
    out = OUT / f"report_{RUN_ID}.json"
    out.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {out}")
    print(f"Issues: {len(REPORT['issues'])}")
    print(f"Features OK: {sum(1 for f in REPORT['features'] if f.get('ok'))}/{len(REPORT['features'])}")


if __name__ == "__main__":
    main()
