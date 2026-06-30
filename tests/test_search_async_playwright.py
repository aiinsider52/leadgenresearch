#!/usr/bin/env python3
"""Playwright: async search returns job_id immediately and completes with meta (ISS-004)."""
from __future__ import annotations

import json
import time
import unittest

from playwright.sync_api import sync_playwright

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from playwright_search_mock import MOCK_META, install_instant_search_mock, mock_lead

BASE = "http://127.0.0.1:8000"
MOCK_LEADS = [mock_lead("iss004-lead", "ISS004 Agency")]


def run_flow() -> dict:
    timings: dict[str, float] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        install_instant_search_mock(page, MOCK_LEADS, MOCK_META)

        page.goto(BASE, wait_until="networkidle", timeout=90000)
        page.click('.tabbtn[data-tab="search"]')
        page.fill("#category", "agency")
        page.fill("#city", "Київ")
        page.evaluate("localStorage.setItem('lg_src','osm')")
        page.evaluate("document.getElementById('expandNiche').checked=false")

        t0 = time.perf_counter()
        page.locator("#runCity").click()
        page.locator(".lead-card-skeleton").first.wait_for(state="attached", timeout=8000)
        timings["skeleton_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        page.wait_for_selector('.lead-card[data-hydrated="true"]', timeout=60000)
        status = page.locator("#status").inner_text().lower()
        timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        assert "iss004 agency" in page.locator("#results").inner_text().lower()
        assert "100" in status or "запитан" in status or "requested" in status
        assert "1" in status

        browser.close()
    return timings


class SearchAsyncPlaywrightTests(unittest.TestCase):
    def test_async_search_completes_with_honest_limit(self) -> None:
        timings = run_flow()
        print(f"ISS-004/003 Playwright: {json.dumps(timings)}")
        self.assertLess(timings["total_ms"], 60000)


if __name__ == "__main__":
    run_flow()
    print("OK async search Playwright verification")
