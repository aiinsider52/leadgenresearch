"""Tests for agent layer, campaigns, outreach queue."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch, MagicMock

from leadgen.agent.tools import execute_tool, TOOL_SCHEMAS
from leadgen.agent import session as chat_session
from leadgen.agent import memory
from leadgen.campaigns import create_campaign, list_campaigns, get_campaign
from leadgen.outreach.queue import enqueue, list_queue, pending_count
from leadgen.service import SearchResult


class AgentToolsTests(unittest.TestCase):
    def test_tool_schemas_valid(self):
        names = {t["function"]["name"] for t in TOOL_SCHEMAS}
        self.assertIn("search_leads", names)
        self.assertIn("create_campaign", names)
        self.assertGreaterEqual(len(names), 15)

    def test_get_stats_tool(self):
        result = json.loads(execute_tool("get_stats", {}, lang="uk"))
        self.assertIn("total_leads", result)

    def test_get_usage_tool(self):
        result = json.loads(execute_tool("get_usage", {}, lang="uk"))
        self.assertIn("openai", result)

    @patch("leadgen.service.find_leads")
    def test_search_leads_tool(self, mock_find):
        mock_find.return_value = SearchResult(leads=[], meta={"requested_limit": 5, "returned": 0,
                                                               "discovered_raw": 0, "capped": False})
        result = json.loads(execute_tool("search_leads", {
            "category": "restaurant", "city": "Київ", "limit": 5, "source": "osm",
        }, lang="uk"))
        self.assertEqual(result["count"], 0)
        mock_find.assert_called_once()


class SessionTests(unittest.TestCase):
    def test_create_and_append(self):
        sid = chat_session.create_session("uk")
        chat_session.append_message(sid, "user", "hello")
        msgs = chat_session.get_messages(sid)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["role"], "user")


class MemoryTests(unittest.TestCase):
    def test_remember_recall(self):
        memory.remember("test insight for unittest", category="test")
        rows = memory.recall(5, category="test")
        self.assertTrue(any("unittest" in r.get("insight", "") for r in rows))


class CampaignTests(unittest.TestCase):
    def test_create_campaign(self):
        cid = create_campaign("Test camp", "agency", ["Київ"], limit_per_run=5)
        self.assertTrue(cid)
        camp = get_campaign(cid)
        self.assertEqual(camp["name"], "Test camp")
        self.assertIn(camp, list_campaigns())


class OutreachQueueTests(unittest.TestCase):
    def test_enqueue(self):
        qid = enqueue(lead_id="test-lead", channel="email", subject="Hi",
                      body="Hello", to_email="test@example.com")
        self.assertTrue(qid)
        self.assertGreaterEqual(pending_count(), 0)
        items = list_queue(limit=5)
        self.assertTrue(any(i["id"] == qid for i in items))


if __name__ == "__main__":
    unittest.main()
