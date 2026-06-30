#!/usr/bin/env python3
"""Benchmark ISS-003 (limit meta) + ISS-004 (async search API)."""
from __future__ import annotations

import json
import sys
import time

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def poll_job(job_id: str, timeout: float = 120.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{BASE}/api/jobs/{job_id}", timeout=30)
        job = r.json()
        if job.get("status") == "done":
            return job["result"]
        if job.get("status") in ("failed", "cancelled"):
            raise RuntimeError(job.get("error") or job["status"])
        time.sleep(0.5)
    raise TimeoutError(job_id)


def main() -> None:
    payload = {
        "endpoint": "find",
        "params": {
            "category": "agency",
            "city": "Київ",
            "country": "Ukraine",
            "limit": 500,
            "lang": "uk",
            "enrich": False,
            "source": "osm",
            "discover_websites": False,
            "brave_people": False,
            "brave_news": False,
            "brave_intent": False,
        },
        "filters": {},
        "search_seq": 1,
    }
    t0 = time.perf_counter()
    start = requests.post(f"{BASE}/api/search", json=payload, timeout=30)
    start.raise_for_status()
    body = start.json()
    t_submit = time.perf_counter() - t0
    result = poll_job(body["job_id"])
    t_total = time.perf_counter() - t0
    meta = result.get("meta") or {}
    print(json.dumps({
        "submit_ms": round(t_submit * 1000, 1),
        "total_ms": round(t_total * 1000, 1),
        "job_id": body["job_id"],
        "leads": len(result.get("leads") or []),
        "meta": meta,
        "honest_limit": meta.get("capped") and meta.get("returned", 0) < meta.get("requested_limit", 0),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
