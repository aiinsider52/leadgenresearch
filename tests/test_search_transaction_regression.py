"""Regression: search must behave as a single transaction (ISS-005)."""
from __future__ import annotations

import unittest

from static_bundle import load_static_bundle


class SearchTransactionRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = load_static_bundle()

    def test_abort_controller_used(self) -> None:
        self.assertIn("new AbortController()", self.html)
        self.assertIn("signal:searchAbort.signal", self.html)

    def test_single_flight_and_seq_guard(self) -> None:
        self.assertIn("let searchSeq=0", self.html)
        self.assertIn("if(mySeq!==searchSeq)return", self.html)
        self.assertIn("if(searchInFlight&&payloadKey===lastSearchPayload)return", self.html)

    def test_buttons_disabled_while_busy(self) -> None:
        self.assertIn("run.disabled=busy", self.html)
        self.assertIn("map.disabled=busy", self.html)

    def test_cancel_ui_and_esc(self) -> None:
        self.assertIn('id="cancelSearch"', self.html)
        self.assertIn("function cancelSearch()", self.html)
        self.assertIn("if(searchInFlight){e.preventDefault();cancelSearch();return;}", self.html)

    def test_visual_progress(self) -> None:
        self.assertIn('id="searchProgress"', self.html)
        self.assertIn("search-progress-bar", self.html)
        self.assertIn("search_progress", self.html)

    def test_search_seq_sent_to_api(self) -> None:
        self.assertIn("search_seq:mySeq", self.html)


if __name__ == "__main__":
    unittest.main()
