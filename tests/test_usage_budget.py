"""Budget status API for ISS-002 — banners and source availability."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from leadgen import usage


class BudgetStatusTest(unittest.TestCase):
    def test_budget_status_blocked_apify(self):
        fake = {
            "month": "2026-06",
            "apify_runs": 300,
            "apify_usd": 30.0,
            "openai_calls": 0,
            "openai_usd": 0.0,
            "brave_calls": 0,
            "brave_usd": 0.0,
            "apollo_calls": 0,
            "apollo_usd": 0.0,
            "hunter_calls": 0,
            "hunter_usd": 0.0,
        }
        with patch.object(usage, "_read", return_value=fake), \
             patch.object(usage, "_cap", side_effect=lambda k: {"apify": 25, "openai": 10, "brave": 5}.get(k, 10)):
            st = usage.budget_status()
        self.assertIn("apify", st["blocked_providers"])
        self.assertIn("instagram", st["unavailable_sources"])
        self.assertIn("facebook", st["unavailable_sources"])
        self.assertTrue(st["providers"]["apify"]["blocked"])
        self.assertFalse(st["providers"]["openai"]["blocked"])

    def test_is_source_available_osm_always(self):
        with patch.object(usage, "allowed", return_value=False):
            self.assertTrue(usage.is_source_available("osm"))
            self.assertTrue(usage.is_source_available("all_sources"))
            self.assertFalse(usage.is_source_available("instagram"))

    def test_summary_includes_budget(self):
        with patch.object(usage, "_read", return_value={"month": "2026-06", "apify_runs": 0, "apify_usd": 0,
                                                        "openai_calls": 0, "openai_usd": 0,
                                                        "brave_calls": 0, "brave_usd": 0,
                                                        "apollo_calls": 0, "apollo_usd": 0,
                                                        "hunter_calls": 0, "hunter_usd": 0}):
            s = usage.summary()
        self.assertIn("budget", s)
        self.assertIn("blocked", s["apify"])
        self.assertIn("providers", s["budget"])


if __name__ == "__main__":
    unittest.main()
