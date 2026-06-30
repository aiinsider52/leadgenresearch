"""Chat session persistence for the conversational agent."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..config import data_dir

SESSIONS_FILE = data_dir() / "chat_sessions.json"
_LOCK = threading.Lock()
_MAX_MESSAGES = 40


def _read() -> dict:
    if SESSIONS_FILE.exists():
        try:
            return json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"sessions": {}}


def _write(data: dict) -> None:
    SESSIONS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def create_session(lang: str = "uk") -> str:
    sid = str(uuid.uuid4())
    with _LOCK:
        data = _read()
        data["sessions"][sid] = {
            "id": sid,
            "lang": lang,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "messages": [],
        }
        _write(data)
    return sid


def get_session(session_id: str) -> dict | None:
    return _read().get("sessions", {}).get(session_id)


def list_sessions(limit: int = 20) -> list[dict]:
    sessions = list(_read().get("sessions", {}).values())
    sessions.sort(key=lambda s: s.get("updated_at") or s.get("created_at", ""), reverse=True)
    return sessions[:limit]


def append_message(session_id: str, role: str, content: str, *, meta: dict | None = None) -> None:
    with _LOCK:
        data = _read()
        sess = data["sessions"].get(session_id)
        if not sess:
            return
        msg = {"role": role, "content": content, "ts": datetime.now(timezone.utc).isoformat()}
        if meta:
            msg["meta"] = meta
        sess["messages"].append(msg)
        sess["messages"] = sess["messages"][-_MAX_MESSAGES:]
        sess["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write(data)


def get_messages(session_id: str) -> list[dict]:
    sess = get_session(session_id)
    return list(sess.get("messages", [])) if sess else []


def set_lang(session_id: str, lang: str) -> None:
    with _LOCK:
        data = _read()
        if session_id in data["sessions"]:
            data["sessions"][session_id]["lang"] = lang
            _write(data)
