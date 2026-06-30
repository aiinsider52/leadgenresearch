#!/usr/bin/env python3
"""Playwright: skeleton cards are not clickable; modal opens only after hydration (ISS-001)."""
from __future__ import annotations

import json
import time
import unittest

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"

MOCK_LEADS_JS = json.dumps(
    [
        {
            "_id": "iss001-test-lead",
            "company": {
                "name": "ISS001 Test Agency",
                "city": "Київ",
                "address": "вул. Тестова 1",
                "source": "osm",
            },
            "enrichment": {"emails": []},
            "score": {"score": 72, "tier": "warm"},
        }
    ]
)


def _modal_hidden(page) -> bool:
    return page.locator("#leadModal").evaluate("el => el.classList.contains('hidden')")


def run_playwright_flow() -> dict[str, float]:
    timings: dict[str, float] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        page.goto(BASE, wait_until="networkidle", timeout=90000)
        page.click('.tabbtn[data-tab="search"]')

        page.evaluate("() => { tab = 'search'; loadingCards(); }")
        page.locator(".lead-card-skeleton").first.wait_for(state="attached", timeout=5000)

        assert page.locator("#results").get_attribute("aria-busy") == "true"
        assert page.locator(".lead-card[data-hydrated='true']").count() == 0

        skel = page.locator(".lead-card-skeleton").first
        pe = skel.evaluate("el => getComputedStyle(el).pointerEvents")
        cur = skel.evaluate("el => getComputedStyle(el).cursor")
        assert pe == "none", f"expected pointer-events:none, got {pe}"
        assert cur == "wait", f"expected cursor:wait, got {cur}"

        t0 = time.perf_counter()
        skel.click(force=True, timeout=3000)
        timings["skeleton_click_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        page.wait_for_timeout(100)
        assert _modal_hidden(page), "modal must not open when clicking skeleton"

        page.evaluate(
            f"""() => {{
              lastLeads = {MOCK_LEADS_JS};
              renderCurrent();
            }}"""
        )
        page.wait_for_selector('.lead-card[data-hydrated="true"]', timeout=5000)
        assert page.locator("#results").get_attribute("aria-busy") is None
        assert page.locator(".lead-card-skeleton").count() == 0

        card = page.locator('.lead-card[data-hydrated="true"]').first
        t1 = time.perf_counter()
        card.click(timeout=5000)
        page.wait_for_function(
            "() => !document.getElementById('leadModal').classList.contains('hidden')",
            timeout=5000,
        )
        timings["hydrated_open_ms"] = round((time.perf_counter() - t1) * 1000, 2)
        assert "ISS001 Test Agency" in page.locator("#lmHead").inner_text()

        browser.close()
    return timings


class LeadCardSkeletonPlaywrightTests(unittest.TestCase):
    def test_skeleton_not_clickable_hydrated_opens_modal(self) -> None:
        timings = run_playwright_flow()
        print(f"ISS-001 benchmark timings: {json.dumps(timings)}")
        self.assertLess(timings["skeleton_click_ms"], 500)
        self.assertLess(timings["hydrated_open_ms"], 3000)


if __name__ == "__main__":
    timings = run_playwright_flow()
    print("OK lead card skeleton Playwright verification")
    print(f"benchmark: {json.dumps(timings)}")
