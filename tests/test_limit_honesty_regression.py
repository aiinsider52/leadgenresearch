"""Regression: async search + honest limits in UI (ISS-003/004)."""
from __future__ import annotations

import unittest
from pathlib import Path

INDEX = Path(__file__).resolve().parent.parent / "leadgen" / "static" / "index.html"


class LimitHonestyRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = INDEX.read_text(encoding="utf-8")

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
