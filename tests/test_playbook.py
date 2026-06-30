"""Playbook and intent engine tests."""
from __future__ import annotations

import unittest

from leadgen import intent_engine, playbook


class PlaybookTest(unittest.TestCase):
    def test_roi(self) -> None:
        r = playbook.roi_estimate(leads=100, conversion_pct=5, deal_usd=2000)
        self.assertEqual(r["expected_clients"], 5.0)
        self.assertGreater(r["pipeline_value_usd"], 0)

    def test_playbook_steps(self) -> None:
        pb = playbook.get_playbook()
        self.assertGreaterEqual(len(pb.get("steps", [])), 4)

    def test_intent_filter(self) -> None:
        leads = [
            {"company": {"name": "A"}, "enrichment": {"signals": {"hiring": True}}, "score": {"score": 80}},
            {"company": {"name": "B"}, "enrichment": {}, "score": {"score": 10}},
        ]
        out = intent_engine.filter_intent_leads(leads)
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
