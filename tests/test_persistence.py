"""Persistence layer tests — SQLite fallback (no live Postgres required)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from leadgen import kv, storage
from leadgen.db import backend, init_schema, connect


class StorageRoundtripTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._data = Path(self._tmp.name) / "data"
        self._data.mkdir()
        self._db_file = self._data / "leadgen.db"
        self._patches = [
            patch.dict(os.environ, {}, clear=False),
            patch("leadgen.config.data_dir", return_value=self._data),
            patch("leadgen.db.DB_FILE", self._db_file),
        ]
        for p in self._patches:
            p.start()
        os.environ.pop("DATABASE_URL", None)
        init_schema()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_storage_upsert_and_load(self) -> None:
        lead = {
            "company": {"name": "Acme", "city": "Kyiv", "source": "osm"},
            "score": {"score": 80, "tier": "hot"},
        }
        storage.upsert_lead("acme-kyiv", lead)
        rows = storage.load_all_leads()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["company"]["name"], "Acme")

    def test_kv_json_file_fallback(self) -> None:
        path = self._data / "saved.json"
        kv.save_json("saved", path, {"a": {"company": {"name": "X"}}})
        loaded = kv.load_json("saved", path, {})
        self.assertIn("a", loaded)

    def test_sqlite_backend_without_database_url(self) -> None:
        self.assertEqual(backend(), "sqlite")


class DatabaseUrlTest(unittest.TestCase):
    def test_postgres_url_normalized(self) -> None:
        from leadgen.db import _database_url

        with patch.dict(os.environ, {"DATABASE_URL": "postgres://u:p@h/db"}, clear=False):
            url = _database_url()
            self.assertTrue(url and url.startswith("postgresql://"))


if __name__ == "__main__":
    unittest.main()
