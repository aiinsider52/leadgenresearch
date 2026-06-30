"""Unit tests for async search jobs (ISS-004)."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from leadgen import worker
from leadgen.service import Lead, SearchResult


class SearchAsyncTests(unittest.TestCase):
    def test_submit_search_enqueues_search_kind(self) -> None:
        with patch.object(worker, "submit", return_value="job123") as submit:
            jid = worker.submit_search("find", {"category": "agency", "city": "Kyiv"}, {}, search_seq=7)
        self.assertEqual(jid, "job123")
        submit.assert_called_once()
        self.assertEqual(submit.call_args[0][0], "search")
        payload = submit.call_args[0][1]
        self.assertEqual(payload["endpoint"], "find")
        self.assertEqual(payload["params"]["search_seq"], 7)

    def test_dispatch_search_packages_leads_and_meta(self) -> None:
        lead = Lead(company={"name": "Acme", "city": "Kyiv"}, enrichment={},
                    score={"score": 50, "tier": "warm"})
        meta = {"requested_limit": 5, "returned": 1, "discovered_raw": 3,
                "deduped_before_enrichment": 2, "capped": True, "cap_reason": "source_exhausted"}
        with patch("leadgen.search_jobs.run_search", return_value=SearchResult(leads=[lead], meta=meta)):
            with patch("leadgen.search_response.saved_ids", return_value=[]):
                out = worker._dispatch("search", {"endpoint": "find", "params": {}, "filters": {}})
        self.assertEqual(len(out["leads"]), 1)
        self.assertEqual(out["meta"]["returned"], 1)
        self.assertTrue(out["meta"]["capped"])

    @patch("leadgen.search_jobs.find_leads")
    def test_run_search_passes_category_like_sync_route(self, mock_find: MagicMock) -> None:
        mock_find.return_value = SearchResult(leads=[], meta={"requested_limit": 5, "returned": 0,
                                                              "discovered_raw": 0, "capped": False})
        from leadgen import search_jobs
        search_jobs.run_search("find", {
            "category": "agency",
            "city": "Київ",
            "country": "Ukraine",
            "limit": 10,
            "lang": "uk",
            "enrich": False,
            "source": "osm",
            "search_seq": 3,
        })
        mock_find.assert_called_once()
        self.assertEqual(mock_find.call_args[0][0], "agency")
        self.assertEqual(mock_find.call_args[0][1], "Київ")
        self.assertEqual(mock_find.call_args.kwargs.get("search_seq"), 3)

    def test_cancel_job_marks_cancelled(self) -> None:
        with patch.object(worker, "get_job", return_value={"id": "x", "status": "running"}):
            with patch.object(worker, "_update_job") as upd:
                ok = worker.cancel_job("x")
        self.assertTrue(ok)
        upd.assert_called_once()
        self.assertEqual(upd.call_args.kwargs.get("status"), "cancelled")


if __name__ == "__main__":
    unittest.main()
