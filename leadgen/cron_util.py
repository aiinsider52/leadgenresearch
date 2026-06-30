"""Minimal 5-field cron matcher (UTC) for campaign scheduling."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _expand_field(field: str, lo: int, hi: int) -> set[int]:
    if field == "*":
        return set(range(lo, hi + 1))
    out: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        if part.startswith("*/"):
            step = max(1, int(part[2:]))
            out.update(range(lo, hi + 1, step))
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
            continue
        out.add(int(part))
    return out


def _py_weekday_to_cron(py_dow: int) -> int:
    """Python Mon=0..Sun=6 → cron Sun=0, Mon=1, … Sat=6."""
    return (py_dow + 1) % 7


def cron_matches(expr: str, dt: datetime) -> bool:
    parts = expr.strip().split()
    if len(parts) != 5:
        return True
    mi, hr, dom, mon, dow = parts
    cron_dow = _py_weekday_to_cron(dt.weekday())
    dow_vals = _expand_field(dow, 0, 7)
    if cron_dow not in dow_vals and not (cron_dow == 0 and 7 in dow_vals):
        return False
    return (
        dt.minute in _expand_field(mi, 0, 59)
        and dt.hour in _expand_field(hr, 0, 23)
        and dt.day in _expand_field(dom, 1, 31)
        and dt.month in _expand_field(mon, 1, 12)
    )


def cron_is_due(expr: str, last_run_iso: str | None, now: datetime | None = None) -> bool:
    """True if a cron slot occurred since `last_run` (or never run before)."""
    now = (now or datetime.now(timezone.utc)).replace(second=0, microsecond=0)
    if not last_run_iso:
        return True
    last = datetime.fromisoformat(last_run_iso.replace("Z", "+00:00")).replace(second=0, microsecond=0)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    t = last + timedelta(minutes=1)
    while t <= now:
        if cron_matches(expr, t):
            return True
        t += timedelta(minutes=1)
    return False
