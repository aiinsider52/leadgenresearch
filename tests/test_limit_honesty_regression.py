"""Regression: async search + honest limits in UI (ISS-003/004)."""
from __future__ import annotations

import unittest

from static_bundle import load_static_bundle


class LimitHonestyRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = load_static_bundle()

    def test_async_search_api_used(self) -> None:
        self.assertIn("fetch('/api/search'", self.html)
        self.assertIn("pollSearchJob", self.html)
        self.assertIn("SEARCH_ENDPOINTS", self.html)

    def test_limit_status_formatters(self) -> None:
        self.assertIn("formatSearchStatus", self.html)
        self.assertIn("limit_exact", self.html)
        self.assertIn("limit_capped", self.html)
        self.assertIn("lastSearchMeta", self.html)

    def test_normalize_payload_supports_meta(self) -> None:
        self.assertIn("normalizeSearchPayload", self.html)
        self.assertIn("data.meta", self.html)


if __name__ == "__main__":
    unittest.main()
