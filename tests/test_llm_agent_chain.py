"""Test agent model chain is respected in complete_with_tools."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from leadgen import llm


class AgentModelChainTest(unittest.TestCase):
    def test_complete_with_tools_uses_models_param(self):
        seen: list[str] = []

        def fake_call(model, payload):
            seen.append(model)
            r = MagicMock()
            r.status_code = 200
            r.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
            return r

        with patch.object(llm, "available", return_value=True), \
             patch.object(llm.usage, "allowed", return_value=True), \
             patch.object(llm, "_call", side_effect=fake_call), \
             patch.object(llm.usage, "record"):
            llm.complete_with_tools(
                [{"role": "user", "content": "hi"}],
                [],
                models=["gpt-4o-mini", "gpt-4o"],
            )
        self.assertEqual(seen[0], "gpt-4o-mini")


if __name__ == "__main__":
    unittest.main()
