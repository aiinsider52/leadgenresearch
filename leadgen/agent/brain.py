"""Conversational agent brain — fast router + lean LLM tool loop."""
from __future__ import annotations

import json
import queue
import threading
from typing import Any, Callable, Generator, Optional

from .. import llm
from ..service import get_icp
from . import session
from .format_reply import format_leads_reply
from .prompts import system_prompt
from .router import try_fast_path
from .tools import AGENT_TOOL_SCHEMAS, SEARCH_TOOLS, execute_tool

MAX_TOOL_ROUNDS = 4
MAX_HISTORY = 12
ProgressFn = Optional[Callable[[str], None]]


def _emit(progress: Optional[ProgressFn], event: str, data: Any = None) -> None:
    if progress:
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        progress(payload)


def _messages_for_llm(session_id: str, lang: str) -> list[dict[str, Any]]:
    icp = get_icp()
    msgs: list[dict[str, Any]] = [{"role": "system", "content": system_prompt(lang, icp)}]
    for m in session.get_messages(session_id)[-MAX_HISTORY:]:
        role = m.get("role")
        if role in ("user", "assistant"):
            msgs.append({"role": role, "content": m.get("content", "")})
    return msgs


def _tool_progress_bridge(outer: Optional[ProgressFn]) -> Callable[[str], None]:
    def inner(msg: str) -> None:
        if msg.startswith("discover:") or msg.startswith("enrich:"):
            human = msg.replace("discover:", "🔍 ").replace("enrich:", "📇 ")
            human = human.replace("_failed:", " помилка: ").replace(":", " — ", 1)
            _emit(outer, "progress", human)
        elif outer:
            _emit(outer, "progress", msg)
    return inner


def _format_search_payload(data: dict, lang: str) -> str:
    return format_leads_reply(
        count=data.get("count", 0),
        leads=data.get("leads", []),
        lang=lang,
        fast=bool(data.get("fast", True)),
    )


def run_agent(session_id: str, user_message: str, *, lang: str = "uk",
              progress: Optional[ProgressFn] = None) -> str:
    """Synchronous agent run. Returns final assistant text."""
    session.append_message(session_id, "user", user_message)
    bridge = _tool_progress_bridge(progress)
    final_text = ""

    # Fast path — no LLM round-trip for typical "find X in Y".
    fast = try_fast_path(user_message, lang=lang, progress=bridge)
    if fast:
        final_text = fast
        session.append_message(session_id, "assistant", final_text)
        _emit(progress, "done", final_text)
        return final_text

    msgs = _messages_for_llm(session_id, lang)
    last_search: dict | None = None

    if not llm.available():
        final_text = _offline_reply(user_message, lang, bridge)
    else:
        for _ in range(MAX_TOOL_ROUNDS):
            resp = llm.complete_with_tools(
                msgs, AGENT_TOOL_SCHEMAS, models=llm.agent_model_chain(),
            )
            if not resp:
                final_text = _offline_reply(user_message, lang, bridge)
                break

            tool_calls = resp.get("tool_calls") or []
            content = (resp.get("content") or "").strip()

            if tool_calls:
                msgs.append({
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": tool_calls,
                })
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    tname = fn.get("name", "")
                    try:
                        targs = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        targs = {}
                    _emit(progress, "tool_start", {"tool": tname, "args": targs})
                    result = execute_tool(tname, targs, lang=lang, progress=bridge)
                    _emit(progress, "tool_done", {"tool": tname})
                    if tname in SEARCH_TOOLS:
                        try:
                            parsed = json.loads(result)
                            if "leads" in parsed:
                                last_search = parsed
                                _emit(progress, "leads", parsed.get("leads", [])[:8])
                        except json.JSONDecodeError:
                            pass
                    msgs.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id"),
                        "content": result,
                    })
                continue

            if last_search and "leads" in last_search:
                intro = content.split("\n")[0].strip() if content else ""
                body = _format_search_payload(last_search, lang)
                final_text = f"{intro}\n\n{body}".strip() if intro and intro not in body else body
            else:
                final_text = content or "Готово."
            break
        else:
            if last_search:
                final_text = _format_search_payload(last_search, lang)
            else:
                final_text = content if content else "Досягнуто ліміт кроків. Спробуйте уточнити запит."

    session.append_message(session_id, "assistant", final_text)
    _emit(progress, "done", final_text)
    return final_text


def _offline_reply(user_message: str, lang: str, progress: ProgressFn) -> str:
    """Deterministic fallback when OpenAI is off."""
    _emit(progress, "progress", "⚠️ AI вимкнено — швидкий пошук")
    fast = try_fast_path(user_message, lang=lang, progress=progress)
    if fast:
        return fast
    hints = {
        "uk": "AI вимкнено. Увімкніть OPENAI_API_KEY або сформулюйте: «знайди marketing agency у Києві».",
        "ru": "AI выключен. Включите OPENAI_API_KEY или напишите: «найди marketing agency в Киеве».",
        "en": "AI is off. Set OPENAI_API_KEY or try: «find marketing agency in Kyiv».",
    }
    return hints.get(lang, hints["uk"])


def run_agent_stream(session_id: str, user_message: str, *,
                     lang: str = "uk") -> Generator[str, None, None]:
    """SSE generator — yields `data: {...}\\n\\n` lines."""
    q: "queue.Queue[Optional[str]]" = queue.Queue()

    def on_progress(payload: str) -> None:
        q.put(payload)

    def worker() -> None:
        try:
            run_agent(session_id, user_message, lang=lang, progress=on_progress)
        except Exception as exc:
            q.put(json.dumps({"event": "error", "data": str(exc)}, ensure_ascii=False))
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()
    while True:
        item = q.get()
        if item is None:
            break
        yield f"data: {item}\n\n"
