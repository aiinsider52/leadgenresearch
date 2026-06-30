"""Structured observability — metrics and cost-per-lead tracking."""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone

from .config import data_dir
from .db import record_metric

LOG_FILE = data_dir() / "leadgen.log"
_LOCK = threading.Lock()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("leadgen")


def _file_handler():
    try:
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        return fh
    except OSError:
        return None


_fh = _file_handler()
if _fh:
    logger.addHandler(_fh)


def log_event(event: str, **fields) -> None:
    payload = {"event": event, "ts": datetime.now(timezone.utc).isoformat(), **fields}
    with _LOCK:
        logger.info(json.dumps(payload, ensure_ascii=False, default=str))


def track_search(*, source: str, city: str, found: int, cost_usd: float = 0) -> None:
    log_event("search_complete", source=source, city=city, found=found, cost_usd=cost_usd)
    if found:
        record_metric("cost_per_lead", cost_usd / found, {"source": source})
    record_metric("leads_found", float(found), {"source": source, "city": city})


def track_campaign(campaign_id: str, leads: int, hot: int) -> None:
    log_event("campaign_run", campaign_id=campaign_id, leads=leads, hot=hot)
    record_metric("campaign_leads", float(leads), {"campaign_id": campaign_id})


def track_outreach(sent: int, failed: int) -> None:
    log_event("outreach_batch", sent=sent, failed=failed)
    record_metric("outreach_sent", float(sent), {})
