"""Background job queue — threaded workers for non-blocking searches."""
from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

from .config import data_dir
from .db import init_schema, connect

JOBS_FILE = data_dir() / "jobs.jsonl"
_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="leadgen-worker")
_LOCK = threading.Lock()


def enqueue_job(kind: str, payload: dict) -> str:
    jid = str(uuid.uuid4())[:12]
    row = {
        "id": jid,
        "kind": kind,
        "payload": payload,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _LOCK:
        with JOBS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    try:
        init_schema()
        with connect() as con:
            con.execute(
                "INSERT INTO jobs(id,kind,payload_json,status,created_at) VALUES(?,?,?,?,?)",
                (jid, kind, json.dumps(payload), "pending", row["created_at"]),
            )
    except Exception:
        pass
    return jid


def _update_job(jid: str, **fields) -> None:
    if not JOBS_FILE.exists():
        return
    rows = []
    for line in JOBS_FILE.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("id") == jid:
            row.update(fields)
        rows.append(row)
    with _LOCK:
        with JOBS_FILE.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _run_job(jid: str, kind: str, payload: dict) -> None:
    job = get_job(jid)
    if job and job.get("status") == "cancelled":
        return
    _update_job(jid, status="running", started_at=datetime.now(timezone.utc).isoformat())
    try:
        if get_job(jid) and get_job(jid).get("status") == "cancelled":
            return
        result = _dispatch(kind, payload)
        if get_job(jid) and get_job(jid).get("status") == "cancelled":
            return
        _update_job(jid, status="done", finished_at=datetime.now(timezone.utc).isoformat(),
                    result=result)
    except Exception as exc:
        _update_job(jid, status="failed", finished_at=datetime.now(timezone.utc).isoformat(),
                    error=str(exc))


def _dispatch(kind: str, payload: dict) -> Any:
    if kind == "search":
        from . import search_jobs
        from .search_response import package_search_result

        endpoint = payload["endpoint"]
        params = dict(payload.get("params") or {})
        filters = payload.get("filters") or {}
        result = search_jobs.run_search(endpoint, params)
        return package_search_result(result, filters)
    if kind == "find_leads":
        from . import service
        from .search_response import package_search_result

        res = service.find_leads(**payload)
        return package_search_result(res)
    if kind == "campaign":
        from .campaigns import run_campaign
        return run_campaign(payload["campaign_id"])
    if kind == "outreach":
        from .outreach.sender import process_queue
        return process_queue(limit=payload.get("limit", 10))
    if kind == "signals":
        from .signals.listeners import poll_signals
        return poll_signals()
    if kind == "agent":
        from .agent.brain import run_agent
        return {"reply": run_agent(payload["session_id"], payload["message"],
                                   lang=payload.get("lang", "uk"))}
    raise ValueError(f"unknown job kind: {kind}")


def cancel_job(jid: str) -> bool:
    job = get_job(jid)
    if not job or job.get("status") in ("done", "failed", "cancelled"):
        return False
    _update_job(jid, status="cancelled", finished_at=datetime.now(timezone.utc).isoformat(),
                error="cancelled by client")
    return True


def submit(kind: str, payload: dict) -> str:
    jid = enqueue_job(kind, payload)
    _EXECUTOR.submit(_run_job, jid, kind, payload)
    return jid


def submit_search(endpoint: str, params: dict, filters: dict | None = None,
                  search_seq: int | None = None) -> str:
    payload = {
        "endpoint": endpoint,
        "params": {**params, "search_seq": search_seq},
        "filters": filters or {},
    }
    return submit("search", payload)


def get_job(jid: str) -> dict | None:
    if not JOBS_FILE.exists():
        return None
    for line in JOBS_FILE.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("id") == jid:
            return row
    return None


def list_jobs(limit: int = 20) -> list[dict]:
    if not JOBS_FILE.exists():
        return []
    rows = []
    for line in JOBS_FILE.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows[::-1]
