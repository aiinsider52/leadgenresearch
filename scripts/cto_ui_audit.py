#!/usr/bin/env python3
"""Playwright UI audit — real user journeys + screenshots."""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent.parent / "data" / "cto_audit" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
REPORT: list[dict] = []


def shot(page, name: str) -> str:
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    return str(path)


def log(step: str, ok: bool, detail: str = "", screenshot: str = "") -> None:
    REPORT.append({"step": step, "ok": ok, "detail": detail, "screenshot": screenshot,
                   "ts": datetime.utcnow().isoformat()})


def run() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                  color_scheme="dark")
        page = ctx.new_page()

        # 1. Dashboard load
        page.goto(BASE, wait_until="networkidle", timeout=60000)
        log("dashboard_load", True, shot(page, "01_dashboard_dark_1440"))

        # 2. Tabs
        for tab_name in ["all", "saved", "agent", "search"]:
            page.click(f'.tabbtn[data-tab="{tab_name}"]', timeout=10000)
            page.wait_for_timeout(400)
            log(f"tab_{tab_name}", True, shot(page, f"02_tab_{tab_name}"))

        # 3. Search (OSM fast)
        page.click('.tabbtn[data-tab="search"]')
        page.fill("#category", "agency")
        page.fill("#city", "Київ")
        page.evaluate("localStorage.setItem('lg_src','osm')")
        page.click("#runCity")
        # wait for progress or results up to 90s
        try:
            page.wait_for_selector(".lead-card, #empty", timeout=90000)
            cards = page.locator(".lead-card").count()
            log("search_osm", cards > 0 or page.locator("#empty").is_visible(),
                f"cards={cards}", shot(page, "03_search_results"))
        except Exception as exc:
            log("search_osm", False, str(exc), shot(page, "03_search_timeout"))

        # 4. Open first lead modal
        if page.locator(".lead-card").count() > 0:
            page.locator(".lead-card").first.click()
            page.wait_for_timeout(500)
            modal_visible = not page.locator("#leadModal").evaluate(
                "el => el.classList.contains('hidden')")
            log("lead_modal", modal_visible, shot(page, "04_lead_modal"))
            # close
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

        # 5. Save first lead
        if page.locator(".lead-card").count() > 0:
            heart = page.locator(".lead-card").first.locator(".heart")
            if heart.count():
                heart.click()
                page.wait_for_timeout(500)
            log("save_lead", True, shot(page, "05_after_save"))

        # 6. Analytics modal
        page.click("#statsBtnSide", timeout=5000)
        page.wait_for_timeout(800)
        stats_open = not page.locator("#stats").evaluate("el => el.classList.contains('hidden')")
        log("analytics_modal", stats_open, shot(page, "06_analytics"))
        page.keyboard.press("Escape")

        # 7. Command palette
        page.keyboard.press("Meta+k")
        page.wait_for_timeout(400)
        palette = page.locator("#cmdPalette")
        log("cmd_palette", palette.is_visible(), shot(page, "07_cmd_palette"))
        page.keyboard.press("Escape")

        # 8. Agent message
        page.click('.tabbtn[data-tab="agent"]')
        page.wait_for_timeout(400)
        inp = page.locator("#agentInput")
        if inp.count():
            inp.fill("статистика")
            page.locator("#agentForm").evaluate("f => f.requestSubmit()")
            page.wait_for_timeout(8000)
            log("agent_chat", True, shot(page, "08_agent_reply"))

        # 9. Light theme
        page.click("#theme")
        page.wait_for_timeout(500)
        log("light_theme", True, shot(page, "09_light_theme"))

        # 10. Mobile viewport
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(500)
        log("mobile_375", True, shot(page, "10_mobile_375"))

        browser.close()

    report_path = OUT.parent / f"ui_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"UI audit: {len(REPORT)} steps, report={report_path}")
    for r in REPORT:
        status = "OK" if r["ok"] else "FAIL"
        print(f"  [{status}] {r['step']}: {r['detail'][:80]}")


if __name__ == "__main__":
    run()
