"""Unit tests for search generation guard (ISS-005)."""
from __future__ import annotations

import unittest

from leadgen import search_guard


class SearchGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        search_guard.reset_for_tests()

    def test_none_seq_always_persists(self) -> None:
        self.assertTrue(search_guard.should_persist(None))

    def test_register_and_persist_latest_only(self) -> None:
        search_guard.register_search(1)
        self.assertTrue(search_guard.should_persist(1))
        search_guard.register_search(2)
        self.assertFalse(search_guard.should_persist(1))
        self.assertTrue(search_guard.should_persist(2))

    def test_superseded_seq_skips_persist(self) -> None:
        search_guard.register_search(10)
        search_guard.register_search(11)
        self.assertFalse(search_guard.should_persist(10))
        self.assertTrue(search_guard.should_persist(11))


if __name__ == "__main__":
    unittest.main()
