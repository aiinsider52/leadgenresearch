"""Unit: superseded search_seq must skip save_leads (ISS-005)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from leadgen import search_guard
from leadgen.service import Company, _process


class SearchPersistUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        search_guard.reset_for_tests()

    @patch("leadgen.service.save_leads")
    @patch("leadgen.service.recommend_templates", return_value=[])
    @patch("leadgen.service.match_company", return_value=[])
    def test_superseded_seq_skips_save(self, _match, _templates, mock_save) -> None:
        companies = [
            Company(
                name="Acme",
                city="Kyiv",
                country="Ukraine",
                category="agency",
                raw_tags={},
            )
        ]
        search_guard.register_search(1)
        search_guard.register_search(2)
        _process(companies, "uk", enrich=False, progress=None, category="agency",
                 discover_websites=False, search_seq=1)
        mock_save.assert_not_called()

    @patch("leadgen.service.save_leads")
    @patch("leadgen.service.recommend_templates", return_value=[])
    @patch("leadgen.service.match_company", return_value=[])
    def test_active_seq_persists(self, _match, _templates, mock_save) -> None:
        companies = [
            Company(
                name="Beta",
                city="Kyiv",
                country="Ukraine",
                category="agency",
                raw_tags={},
            )
        ]
        search_guard.register_search(3)
        _process(companies, "uk", enrich=False, progress=None, category="agency",
                 discover_websites=False, search_seq=3)
        mock_save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
