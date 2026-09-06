#!/usr/bin/env python3
"""Pre-seeds expected-run rows for every 'scheduled' job in the registry, for
a rolling window of days ahead. Idempotent: skips any (job_name, expected_at)
pair that's already in the Run Log, so re-running (by hand, or on its own
schedule) just extends the window rather than duplicating rows.

This is what makes the dead-man's-switch work: the expected row exists in
the sheet whether or not the job ever actually runs. See
platform_job_log/registry.py and the design brief for the full rationale.

Usage:
    python3 scripts/seed_scheduled.py [--days 60]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from croniter import croniter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from platform_job_log import config  # noqa: E402
from platform_job_log.registry import JOBS  # noqa: E402
from platform_job_log.sheets_client import worksheet  # noqa: E402


def _expected_runs(cron: str, tz_name: str, start: datetime, end: datetime) -> list[datetime]:
    tz = ZoneInfo(tz_name)
    base = start.astimezone(tz)
    it = croniter(cron, base)
    runs = []
    while True:
        nxt = it.get_next(datetime).replace(tzinfo=tz)
        if nxt > end:
            break
        runs.append(nxt.astimezone(timezone.utc))
    return runs


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=60, help="How many days ahead to pre-seed")
    args = parser.parse_args(argv)

    ws = worksheet(config.RUN_LOG_TAB)
    existing_rows = ws.get_all_values()
    header = existing_rows[0]
    name_col = header.index("job_name")
    expected_col = header.index("expected_at")
    existing = {
        (row[name_col], row[expected_col])
        for row in existing_rows[1:]
        if len(row) > max(name_col, expected_col) and row[expected_col]
    }

    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=args.days)

    new_rows = []
    for spec in JOBS.values():
        if spec.job_type != "scheduled":
            continue
        for run_at in _expected_runs(spec.cron, spec.timezone, now, window_end):
            expected_str = run_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            if (spec.name, expected_str) in existing:
                continue
            new_rows.append([spec.name, spec.job_type, expected_str, "", "", "", ""])

    if new_rows:
        ws.append_rows(new_rows)
    print(f"Seeded {len(new_rows)} new expected-run row(s) through {window_end.date()}.")


if __name__ == "__main__":
    main()
