"""Track active search generation so superseded requests skip DB persistence (ISS-005)."""
from __future__ import annotations

import threading

_lock = threading.Lock()
_current_seq: int | None = None


def register_search(search_seq: int | None) -> None:
    """Mark the latest in-flight search generation."""
    if search_seq is None:
        return
    global _current_seq
    with _lock:
        _current_seq = search_seq


def should_persist(search_seq: int | None) -> bool:
    """Return True when this search generation is still the active one."""
    if search_seq is None:
        return True
    with _lock:
        return _current_seq == search_seq


def reset_for_tests() -> None:
    global _current_seq
    with _lock:
        _current_seq = None
