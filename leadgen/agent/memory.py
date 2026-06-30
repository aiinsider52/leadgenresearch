"""Agent long-term memory — insights from campaigns and user feedback."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from ..config import data_dir

MEMORY_FILE = data_dir() / "agent_memory.jsonl"
_LOCK = threading.Lock()


def remember(insight: str, *, category: str = "general", source: str = "agent") -> None:
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "insight": insight.strip(),
        "category": category,
        "source": source,
    }
    with _LOCK:
        with MEMORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def recall(limit: int = 10, category: str | None = None) -> list[dict]:
    if not MEMORY_FILE.exists():
        return []
    rows: list[dict] = []
    try:
        for line in MEMORY_FILE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if category and row.get("category") != category:
                continue
            rows.append(row)
    except OSError:
        return []
    return rows[-limit:][::-1]
