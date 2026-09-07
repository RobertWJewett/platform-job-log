#!/usr/bin/env python3
"""CLI entrypoint for platform-job-log's own maintenance tasks -- deployed as
a small Cloud Run Job, triggered on its own Cloud Scheduler schedules:

    python3 main.py update-status   # recomputes the Current Status tab (every 15 min)
    python3 main.py seed-scheduled  # extends the pre-seeded expected-run window (daily)
    python3 main.py setup-format    # one-time/re-run-safe dashboard formatting (not scheduled)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from platform_job_log import formatting  # noqa: E402
from scripts import seed_scheduled, update_status  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["update-status", "seed-scheduled", "setup-format"])
    args = parser.parse_args()

    if args.command == "update-status":
        update_status.main()
    elif args.command == "seed-scheduled":
        seed_scheduled.main(argv=[])
    else:
        formatting.apply_dashboard_formatting()


if __name__ == "__main__":
    main()
