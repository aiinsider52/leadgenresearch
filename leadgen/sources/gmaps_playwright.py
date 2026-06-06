"""Real Google Maps discovery via a Playwright (headless Chromium) worker.

Unlike the requests-based gmaps.py (blocked by Google's JS gating), this
renders the page, scrolls the results feed, and extracts businesses with
rating + review counts + website — signals OSM lacks.

Setup (one-time):
    pip install playwright
    playwright install chromium

⚠️ Scraping Google Maps is against Google's ToS. Use responsibly, keep
volume low, and prefer OSM for bulk. This worker is opt-in (source="gmaps").
"""
from __future__ import annotations

import re
from typing import Optional

from .osm import Company

MAPS_URL = "https://www.google.com/maps/search/{query}/?hl={hl}&gl={gl}"
# Pre-accepting the consent cookie avoids the EU consent interstitial.
SOCS_COOKIE = {
    "name": "SOCS", "value": "CAESEwgDEgk0ODE3Nzk3MjQaAmVuIAEaBgiA_LyaBg",
    "domain": ".google.com", "path": "/",
}


def _size_from_reviews(n: Optional[int]) -> Optional[str]:
    if n is None:
        return None
    return "micro" if n < 20 else "small" if n < 100 else "medium" if n < 500 else "large"


def _to_int(raw: str) -> Optional[int]:
    raw = (raw or "").strip().strip("()").replace("\xa0", "").replace(" ", "").replace(",", ".")
    mult = 1
    if raw[-1:] in ("K", "k", "Т", "т", "тис."):
        mult, raw = 1000, raw[:-1]
    try:
        return int(float(raw) * mult)
    except ValueError:
        return None


def discover_gmaps_pw(
    category: str,
    city: str,
    country: Optional[str] = "Ukraine",
    limit: int = 20,
    hl: str = "uk",
    gl: str = "ua",
    headless: bool = True,
    max_scrolls: int = 8,
    deep: bool = True,
) -> list[Company]:
    from playwright.sync_api import sync_playwright

    query = f"{category} {city}".replace(" ", "+")
    url = MAPS_URL.format(query=query, hl=hl, gl=gl)
    companies: list[Company] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(
            locale="uk-UA",
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        )
        ctx.add_cookies([SOCS_COOKIE])
        # Speed up: don't download images/media/fonts — we only need the DOM.
        ctx.route("**/*", lambda route: route.abort()
                  if route.request.resource_type in ("image", "media", "font")
                  else route.continue_())
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)

        # Dismiss consent if it still appears.
        for label in ("Reject all", "Accept all", "Прийняти все", "Відхилити все", "Я погоджуюсь"):
            try:
                btn = page.get_by_role("button", name=label)
                if btn.count():
                    btn.first.click(timeout=2500)
                    break
            except Exception:
                pass

        # Wait for the results feed.
        try:
            page.wait_for_selector('div[role="feed"]', timeout=15000)
        except Exception:
            browser.close()
            return []

        feed = page.locator('div[role="feed"]')
        stalls = 0
        for _ in range(max_scrolls * 2):
            links = page.locator("a.hfpxzc")
            if links.count() >= limit:
                break
            prev = links.count()
            feed.evaluate("el => el.scrollBy(0, el.scrollHeight)")
            page.wait_for_timeout(1400)
            if page.locator("a.hfpxzc").count() == prev:
                stalls += 1
                if stalls >= 3:  # genuinely no more results
                    break
            else:
                stalls = 0

        links = page.locator("a.hfpxzc")
        n = links.count()
        seen_names: set[str] = set()
        for i in range(n):
            if len(companies) >= limit:
                break
            link = links.nth(i)
            try:
                name = link.get_attribute("aria-label", timeout=1500)
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                card = link.locator("xpath=ancestor::div[@jsaction][1]")
                if card.inner_text()[:18].strip().startswith(("Реклама", "Sponsored", "Ad ·")):
                    continue  # skip paid placements (no reliable data)

                rating = None
                rt = card.locator("span.MW4etd")
                if rt.count():
                    try:
                        rating = float(rt.first.inner_text().replace(",", "."))
                    except ValueError:
                        pass

                # Category + address live on the descriptor line "Cat · … · Addr".
                cat_label, address = None, None
                for line in card.inner_text().split("\n"):
                    if " · " in line:
                        parts = [p.strip() for p in line.split(" · ")
                                 if p.strip() and not any(0xE000 <= ord(ch) <= 0xF8FF for ch in p)]
                        if parts:
                            cat_label = parts[0]
                            if len(parts) > 1:
                                address = parts[-1]
                        break

                website, phone, rev = None, None, None
                if deep:
                    website, phone, rev = _open_detail(page, link)

                companies.append(Company(
                    name=name, category=category, city=city, country=country or "",
                    website=website, phone=phone, address=address,
                    lat=None, lon=None, source="gmaps",
                    raw_tags={"rating": rating, "reviews": rev, "gmaps_category": cat_label,
                              "size_band": _size_from_reviews(rev)},
                ))
            except Exception:
                continue
        browser.close()
    return companies


def _open_detail(page, link):
    """Click a result and read website/phone/reviews from the detail panel."""
    website = phone = rev = None
    try:
        link.click(timeout=4000)
        page.wait_for_timeout(1200)
        wl = page.locator('a[data-item-id="authority"]')
        if wl.count():
            website = wl.first.get_attribute("href")
        pb = page.locator('button[data-item-id^="phone:tel:"]')
        if pb.count():
            phone = (pb.first.get_attribute("data-item-id") or "").replace("phone:tel:", "") or None
        fr = page.locator("div.F7nice")
        if fr.count():
            m = re.search(r"\(([\d\s.,]+)\)", fr.first.inner_text())
            if m:
                rev = _to_int(m.group(1))
    except Exception:
        pass
    return website, phone, rev


if __name__ == "__main__":
    import json
    import sys
    cat = sys.argv[1] if len(sys.argv) > 1 else "restaurant"
    town = sys.argv[2] if len(sys.argv) > 2 else "Львів"
    headless = "--show" not in sys.argv
    res = discover_gmaps_pw(cat, town, limit=12, headless=headless)
    print(f"Found {len(res)}")
    for c in res:
        print("•", c.name, "|", c.raw_tags, "|", c.website or "")
