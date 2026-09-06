#!/usr/bin/env python3
"""CLI entrypoint for platform-job-log's own maintenance tasks -- deployed as
a small Cloud Run Job, triggered on its own Cloud Scheduler schedules:

    python3 main.py update-status   # recomputes the Current Status tab (every 15 min)
    python3 main.py seed-scheduled  # extends the pre-seeded expected-run window (daily)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts import seed_scheduled, update_status  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["update-status", "seed-scheduled"])
    args = parser.parse_args()

    if args.command == "update-status":
        update_status.main()
    else:
        seed_scheduled.main(argv=[])


if __name__ == "__main__":
    main()
