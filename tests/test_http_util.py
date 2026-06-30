"""HTTP helper tests."""
from __future__ import annotations

import unittest

from leadgen.http_util import api_from_result


class HttpUtilTest(unittest.TestCase):
    def test_not_found(self) -> None:
        r = api_from_result({"error": "campaign not found"})
        self.assertEqual(r.status_code, 404)

    def test_ok(self) -> None:
        r = api_from_result({"campaign_id": "x", "leads_found": 3})
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
