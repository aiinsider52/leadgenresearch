#!/usr/bin/env python3
"""Run scheduled searches, campaigns, outreach queue, and signal listeners.

Local crontab (every morning at 7:00):
    0 7 * * * cd /path/to/leadgen && python3 run_scheduled.py >> data/cron.log 2>&1
"""
from leadgen.service import run_schedules
from leadgen.campaigns import run_due_campaigns
from leadgen.outreach.sender import process_queue
from leadgen.signals.listeners import poll_signals
from leadgen import observability


def main() -> None:
    def progress(msg: str) -> None:
        print("…", msg, flush=True)

    print("=== schedules ===")
    summary = run_schedules(progress=progress)
    print("DONE schedules:", summary)

    print("=== campaigns (cron-due only) ===")
    camp_results = run_due_campaigns(progress=progress)
    print("DONE campaigns:", camp_results)
    if not camp_results:
        print("(no campaigns due — check cron schedule vs last_run)")

    print("=== outreach queue ===")
    outreach = process_queue(limit=20, progress=progress)
    print("DONE outreach:", outreach)
    observability.track_outreach(outreach.get("sent", 0), outreach.get("failed", 0))

    print("=== signals ===")
    signals = poll_signals(progress=progress)
    print("DONE signals:", signals)


if __name__ == "__main__":
    main()
