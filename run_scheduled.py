#!/usr/bin/env python3
"""Run all saved scheduled searches once. Point cron at this.

Local crontab (every morning at 8:00):
    0 8 * * * cd /path/to/leadgen && /usr/bin/python3 run_scheduled.py >> data/cron.log 2>&1

Render: add a Cron Job service with command `python run_scheduled.py`.
"""
from leadgen.service import run_schedules

if __name__ == "__main__":
    summary = run_schedules(progress=lambda s: print("…", s, flush=True))
    print("DONE:", summary)
