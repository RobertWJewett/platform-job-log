#!/usr/bin/env python3
"""Recomputes the "Current Status" tab from the Run Log's raw rows -- one row
per registered job. Meant to be run periodically (e.g. every 15 minutes via
its own Cloud Scheduler job) so the tab stays reasonably fresh; safe to
re-run anytime since it always rewrites the whole tab from scratch rather
than appending.

Usage:
    python3 scripts/update_status.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from platform_job_log import config  # noqa: E402
from platform_job_log.registry import JOBS  # noqa: E402
from platform_job_log.sheets_client import worksheet  # noqa: E402
from platform_job_log.status import RunLogRow, compute_status  # noqa: E402


def _load_rows(raw: list[list[str]]) -> list[RunLogRow]:
    header = raw[0]
    idx = {name: header.index(name) for name in config.RUN_LOG_HEADERS}
    rows = []
    for r in raw[1:]:
        if len(r) < len(header):
            r = r + [""] * (len(header) - len(r))
        rows.append(RunLogRow(**{name: r[i] for name, i in idx.items()}))
    return rows


def main() -> None:
    run_log_ws = worksheet(config.RUN_LOG_TAB)
    rows = _load_rows(run_log_ws.get_all_values())
    now = datetime.now(timezone.utc)
    checked_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    output = [["job_name", "job_type", "reference_time", "last_status", "flag", "detail", "checked_at"]]
    for spec in JOBS.values():
        result = compute_status(spec, rows, now)
        output.append([
            result.job_name, result.job_type, result.reference_time,
            result.last_status, result.flag, result.detail, checked_at,
        ])

    status_ws = worksheet(config.CURRENT_STATUS_TAB)
    status_ws.clear()
    status_ws.update("A1", output)
    status_ws.freeze(rows=1)

    overdue = [r for r in output[1:] if r[4] in ("OVERDUE", "FAILED")]
    print(f"Updated Current Status: {len(output) - 1} job(s), {len(overdue)} flagged.")
    for r in overdue:
        print(f"  {r[4]}: {r[0]} -- {r[5]}")


if __name__ == "__main__":
    main()
