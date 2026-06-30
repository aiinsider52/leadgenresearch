"""User authentication tests."""
from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient

from leadgen import auth
from leadgen.app import app
from leadgen.db import DB_FILE, init_schema


class AuthFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop("DATABASE_URL", None)
        os.environ["REQUIRE_AUTH"] = "true"
        if DB_FILE.exists():
            DB_FILE.unlink()
        init_schema()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        os.environ.pop("REQUIRE_AUTH", None)
        if DB_FILE.exists():
            DB_FILE.unlink()

    def test_register_login_and_me(self) -> None:
        r = self.client.post(
            "/api/auth/register",
            json={"email": "test@example.com", "password": "secret123", "name": "Test"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertIn("token", data)
        self.assertEqual(data["user"]["email"], "test@example.com")

        r2 = self.client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "secret123"},
        )
        self.assertEqual(r2.status_code, 200)
        token = r2.json()["token"]

        r3 = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r3.status_code, 200)
        self.assertEqual(r3.json()["email"], "test@example.com")

    def test_duplicate_email_rejected(self) -> None:
        payload = {"email": "dup@example.com", "password": "secret123"}
        self.assertEqual(self.client.post("/api/auth/register", json=payload).status_code, 200)
        r = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(r.status_code, 400)

    def test_dashboard_redirects_when_auth_required(self) -> None:
        self.client.post(
            "/api/auth/register",
            json={"email": "gate@example.com", "password": "secret123"},
        )
        r = self.client.get("/", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers.get("location", ""))

    def test_token_roundtrip(self) -> None:
        token = auth.make_token("user-abc")
        self.assertEqual(auth.verify_token(token), "user-abc")


if __name__ == "__main__":
    unittest.main()
