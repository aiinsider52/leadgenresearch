#!/usr/bin/env python3
"""Playwright: search transaction — single flight, cancel, spam clicks (ISS-005)."""
from __future__ import annotations

import json
import time
import unittest

from playwright.sync_api import sync_playwright

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from playwright_search_mock import (
    SEARCH_POST,
    install_hanging_search_post,
    install_instant_search_mock,
    mock_lead,
)

BASE = "http://127.0.0.1:8000"
MOCK_LEADS = [mock_lead("iss005-test-lead", "ISS005 Agency")]


def _prep_search_page(page) -> None:
    page.goto(BASE, wait_until="networkidle", timeout=90000)
    page.click('.tabbtn[data-tab="search"]')
    page.fill("#category", "agency")
    page.fill("#city", "Київ")
    page.evaluate("localStorage.setItem('lg_src','osm')")
    page.evaluate("const el=document.getElementById('expandNiche'); if(el) el.checked=false")


def run_playwright_flow() -> dict:
    timings: dict[str, float] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        _prep_search_page(page)

        pending: list = []
        request_count: dict[str, int] = {}

        install_hanging_search_post(page, pending, request_count)
        page.fill("#category", "iss005-hang-test")
        page.locator("#runCity").click()
        page.locator(".lead-card-skeleton").first.wait_for(state="attached", timeout=5000)
        assert page.locator("#runCity").is_disabled()
        assert page.locator("#cancelSearch").is_visible()
        assert page.locator("#searchProgress").is_visible()

        t0 = time.perf_counter()
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        status_text = page.locator("#status").inner_text().lower()
        timings["esc_cancel_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        assert any(x in status_text for x in ("скасовано", "cancelled", "отменён")), status_text
        timings["hung_requests"] = request_count.get("search_posts", 0)
        assert not page.locator("#runCity").is_disabled()

        for route in pending:
            try:
                route.abort()
            except Exception:
                pass
        page.unroute(SEARCH_POST)

        counters: dict[str, int] = {}
        install_instant_search_mock(page, MOCK_LEADS, counters=counters)
        request_count = counters
        page.fill("#category", "agency")
        page.evaluate(
            """async () => {
              const body = {
                category: 'agency', city: 'Київ', country: 'Ukraine', limit: 5,
                lang: 'uk', enrich: false, source: 'osm',
                discover_websites: false, brave_people: false, brave_news: false, brave_intent: false
              };
              await Promise.all(Array.from({length: 10}, () => runSearch('/api/find', body)));
            }"""
        )
        timings["concurrent_runSearch_requests"] = request_count.get("search_posts", 0)
        page.wait_for_timeout(300)

        request_count["search_posts"] = 0
        page.locator("#runCity").click()
        page.wait_for_selector('.lead-card[data-hydrated="true"]', timeout=15000)
        timings["success_requests"] = request_count.get("search_posts", 0)
        assert "ISS005 Agency" in page.locator("#results").inner_text()

        browser.close()
    return timings


class SearchTransactionPlaywrightTests(unittest.TestCase):
    def test_spam_esc_and_single_request(self) -> None:
        timings = run_playwright_flow()
        print(f"ISS-005 benchmark: {json.dumps(timings)}")
        self.assertEqual(timings["hung_requests"], 1)
        self.assertEqual(timings["concurrent_runSearch_requests"], 1)
        self.assertEqual(timings["success_requests"], 1)
        self.assertLess(timings["esc_cancel_ms"], 3000)


if __name__ == "__main__":
    timings = run_playwright_flow()
    print("OK search transaction Playwright verification")
    print(f"benchmark: {json.dumps(timings)}")
