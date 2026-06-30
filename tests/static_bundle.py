"""Load concatenated static frontend sources for regression assertions."""
from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "leadgen" / "static"


def load_static_bundle() -> str:
    parts: list[str] = []
    index = STATIC / "index.html"
    if index.exists():
        parts.append(index.read_text(encoding="utf-8"))
    for folder in ("js", "css"):
        root = STATIC / folder
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix in {".js", ".css"} and path.is_file():
                parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)
