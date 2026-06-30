#!/usr/bin/env python3
"""Before/after benchmark for ISS-001 skeleton vs hydrated lead card interaction."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from test_lead_card_skeleton_playwright import run_playwright_flow

OUT = ROOT / "data" / "cto_audit" / "iss001_skeleton_benchmark.json"


def main() -> None:
    t0 = time.perf_counter()
    timings = run_playwright_flow()
    wall = round((time.perf_counter() - t0) * 1000, 1)
    payload = {
        "issue": "ISS-001",
        "description": "skeleton non-interactive; modal only after hydration",
        "wall_ms": wall,
        "timings": timings,
        "assertions": {
            "skeleton_pointer_events": "none",
            "skeleton_click_opens_modal": False,
            "hydrated_click_opens_modal": True,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
