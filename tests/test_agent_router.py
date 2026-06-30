"""Tests for agent fast router and reply formatting."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from leadgen.agent.format_reply import format_leads_reply
from leadgen.agent.router import try_fast_path, _parse_category, _parse_cities


class RouterTests(unittest.TestCase):
    def test_parse_cities(self):
        self.assertIn("Київ", _parse_cities("знайди agency у Києві"))
        cities = _parse_cities("Київ, Львів, Одеса")
        self.assertGreaterEqual(len(cities), 2)

    def test_parse_category(self):
        self.assertIn("marketing", _parse_category("знайди marketing agency у Києві").lower())

    @patch("leadgen.agent.router.execute_tool")
    def test_fast_search(self, mock_tool):
        import json
        mock_tool.return_value = json.dumps({
            "count": 2,
            "fast": True,
            "leads": [
                {"name": "Acme", "city": "Київ", "score": 80, "tier": "hot", "emails": ["a@acme.test"]},
                {"name": "Beta", "city": "Київ", "score": 55, "tier": "warm"},
            ],
        })
        reply = try_fast_path("знайди marketing agency у Києві", lang="uk")
        self.assertIn("Acme", reply)
        self.assertIn("2", reply)
        mock_tool.assert_called_once()
        args = mock_tool.call_args[0]
        self.assertEqual(args[0], "search_leads")


class FormatTests(unittest.TestCase):
    def test_format_leads(self):
        text = format_leads_reply(
            count=1,
            leads=[{"name": "Test Co", "score": 70, "tier": "warm", "city": "Київ"}],
            lang="uk",
            fast=True,
        )
        self.assertIn("Test Co", text)
        self.assertIn("70", text)


if __name__ == "__main__":
    unittest.main()
