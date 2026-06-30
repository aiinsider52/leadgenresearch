#!/usr/bin/env python3
"""Before/after benchmark for ISS-005 search transaction."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from test_search_transaction_playwright import run_playwright_flow

OUT = ROOT / "data" / "cto_audit" / "iss005_search_benchmark.json"


def main() -> None:
    t0 = time.perf_counter()
    timings = run_playwright_flow()
    wall = round((time.perf_counter() - t0) * 1000, 1)
    payload = {
        "issue": "ISS-005",
        "description": "search as single transaction; AbortController; no duplicate requests",
        "wall_ms": wall,
        "timings": timings,
        "assertions": {
            "concurrent_runSearch_single_request": timings.get("concurrent_runSearch_requests") == 1,
            "esc_cancel_under_3s": timings.get("esc_cancel_ms", 9999) < 3000,
            "hung_search_single_request": timings.get("hung_requests") == 1,
            "success_single_request": timings.get("success_requests") == 1,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
