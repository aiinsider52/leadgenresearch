"""Tests for cron scheduling and Facebook source."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from leadgen.cron_util import cron_is_due, cron_matches
from leadgen.service import ALL_SOURCES
from leadgen.sources.facebook import discover_facebook


class CronTests(unittest.TestCase):
    def test_daily_match(self):
        dt = datetime(2026, 6, 30, 7, 0, tzinfo=timezone.utc)
        self.assertTrue(cron_matches("0 7 * * *", dt))
        self.assertFalse(cron_matches("0 8 * * *", dt))

    def test_due_after_slot(self):
        last = "2026-06-29T07:05:00+00:00"
        now = datetime(2026, 6, 30, 7, 10, tzinfo=timezone.utc)
        self.assertTrue(cron_is_due("0 7 * * *", last, now))

    def test_not_due_same_day(self):
        last = "2026-06-30T07:05:00+00:00"
        now = datetime(2026, 6, 30, 7, 10, tzinfo=timezone.utc)
        self.assertFalse(cron_is_due("0 7 * * *", last, now))

    def test_first_run_always_due(self):
        self.assertTrue(cron_is_due("0 7 * * *", None))


class FacebookSourceTests(unittest.TestCase):
    def test_in_all_sources(self):
        self.assertIn("facebook", ALL_SOURCES)

    @patch("leadgen.sources.facebook.usage.record")
    @patch("leadgen.sources.facebook.usage.allowed", return_value=True)
    @patch("leadgen.sources.facebook.requests.post")
    @patch("leadgen.sources.facebook.cfg", return_value="tok")
    def test_maps_apify_payload(self, cfg, post, allowed, record):
        post.return_value.status_code = 200
        post.return_value.json.return_value = [{
            "title": "Acme Agency",
            "pageUrl": "https://facebook.com/acme",
            "email": "hi@acme.test",
            "website": "https://acme.test",
            "phone": "+380441112233",
            "likes": 1200,
        }]
        companies = discover_facebook("marketing agency", "Kyiv", "Ukraine", 5)
        self.assertEqual(companies[0].name, "Acme Agency")
        self.assertEqual(companies[0].source, "facebook")
        self.assertIn("hi@acme.test", companies[0].raw_tags["_enrichment"]["emails"])


if __name__ == "__main__":
    unittest.main()
