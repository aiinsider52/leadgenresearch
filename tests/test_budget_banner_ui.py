#!/usr/bin/env python3
"""Playwright: budget banner visible when API budgets exceeded."""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"


def run() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        page.goto(BASE, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1500)
        banner = page.locator("#budgetBanner")
        visible = banner.is_visible()
        text = banner.inner_text() if visible else ""
        usage = page.request.get(f"{BASE}/api/usage").json()
        blocked = usage.get("budget", {}).get("blocked_providers", [])
        assert blocked, "precondition: need blocked budgets for this test"
        assert visible, f"budget banner should be visible when blocked={blocked}"
        assert "Apify" in text or "Brave" in text or "API" in text or "бюджет" in text.lower(), text
        # brave_places chip should be disabled when brave blocked
        if "brave" in blocked:
            chip = page.locator('.src-chip[data-src="brave_places"]')
            assert chip.count(), "brave_places chip missing"
            assert chip.get_attribute("disabled") is not None or "disabled" in (chip.get_attribute("class") or "")
        browser.close()
        print("OK budget banner Playwright verification")


if __name__ == "__main__":
    run()
