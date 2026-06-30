"""Regression: skeleton placeholders must never be interactive lead cards (ISS-001)."""
from __future__ import annotations

import unittest
from pathlib import Path

INDEX = Path(__file__).resolve().parent.parent / "leadgen" / "static" / "index.html"


class LeadCardSkeletonRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = INDEX.read_text(encoding="utf-8")

    def test_skeleton_uses_dedicated_class_not_lead_card(self) -> None:
        self.assertIn("lead-card-skeleton", self.html)
        start = self.html.index("function loadingCards()")
        end = self.html.index("function clearSearchLoading()", start)
        body = self.html[start:end]
        self.assertIn("lead-card-skeleton", body)
        self.assertNotIn('class="lead-card"', body)

    def test_skeleton_css_non_interactive(self) -> None:
        self.assertRegex(self.html, r"\.lead-card-skeleton\s*\{[^}]*pointer-events:\s*none")
        self.assertRegex(self.html, r"\.lead-card-skeleton\s*\{[^}]*cursor:\s*wait")

    def test_hydrated_cards_required_for_detail(self) -> None:
        self.assertIn('data-hydrated="true"', self.html)
        self.assertIn("isHydratedLeadCard", self.html)
        self.assertIn("if(searchLoading||!id)return", self.html)

    def test_results_aria_busy_during_load(self) -> None:
        self.assertIn("setAttribute('aria-busy','true')", self.html)
        self.assertIn("removeAttribute('aria-busy')", self.html)

    def test_delegated_click_guarded_by_loading_flag(self) -> None:
        self.assertIn("let searchLoading=false", self.html)
        block = self.html.split("$('#results').addEventListener('click'")[1][:500]
        self.assertIn("if(searchLoading)return", block)
        self.assertIn("isHydratedLeadCard", block)


if __name__ == "__main__":
    unittest.main()
