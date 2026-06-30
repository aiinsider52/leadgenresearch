"""Unit tests for honest limit metadata (ISS-003)."""
from __future__ import annotations

import unittest

from leadgen.search_meta import build_limit_meta, cap_reason, merge_multi_meta


class SearchMetaTests(unittest.TestCase):
    def test_exact_limit_not_capped(self) -> None:
        meta = build_limit_meta(requested_limit=50, returned=50, discovered_raw=80,
                                 deduped_before_enrichment=60)
        self.assertFalse(meta["capped"])
        self.assertIsNone(meta["cap_reason"])

    def test_source_exhausted_when_fewer_raw_than_requested(self) -> None:
        meta = build_limit_meta(requested_limit=500, returned=212, discovered_raw=212,
                                 deduped_before_enrichment=212)
        self.assertTrue(meta["capped"])
        self.assertEqual(meta["cap_reason"], "source_exhausted")

    def test_dedupe_reason(self) -> None:
        self.assertEqual(cap_reason(100, 80, 150, 90), "dedupe_filter")

    def test_merge_multi_meta_sums_discovery(self) -> None:
        parts = [
            build_limit_meta(requested_limit=20, returned=20, discovered_raw=30,
                             deduped_before_enrichment=25, source="osm"),
            build_limit_meta(requested_limit=20, returned=18, discovered_raw=22,
                             deduped_before_enrichment=20, source="osm"),
        ]
        merged = merge_multi_meta(parts, 30)
        self.assertEqual(merged["discovered_raw"], 52)
        self.assertEqual(merged["deduped_before_enrichment"], 45)


if __name__ == "__main__":
    unittest.main()
