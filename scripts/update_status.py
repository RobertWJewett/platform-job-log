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


# Sort order within the Current Status tab -- anything that needs a look
# floats to the top; healthy jobs sink to the bottom.
_FLAG_SORT_ORDER = {"FAILED": 0, "OVERDUE": 1, "NO DATA": 2, "OK": 3}

_HEADER_ROW = ["job_name", "job_type", "reference_time", "last_status", "flag", "detail", "checked_at"]


def main() -> None:
    run_log_ws = worksheet(config.RUN_LOG_TAB)
    rows = _load_rows(run_log_ws.get_all_values())
    now = datetime.now(timezone.utc)
    checked_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    results = [compute_status(spec, rows, now) for spec in JOBS.values()]
    results.sort(key=lambda r: (_FLAG_SORT_ORDER.get(r.flag, 4), r.job_name))

    flagged = [r for r in results if r.flag in ("OVERDUE", "FAILED")]
    if flagged:
        headline = f"⚠ {len(flagged)} job(s) need attention — checked {checked_at}"
        headline_color = {"red": 0.96, "green": 0.80, "blue": 0.80}
    else:
        headline = f"✅ All {len(results)} job(s) healthy — checked {checked_at}"
        headline_color = {"red": 0.80, "green": 0.94, "blue": 0.80}

    data_rows = [
        [r.job_name, r.job_type, r.reference_time, r.last_status, r.flag, r.detail, checked_at]
        for r in results
    ]

    status_ws = worksheet(config.CURRENT_STATUS_TAB)
    status_ws.clear()
    status_ws.update([[headline] + [""] * (len(_HEADER_ROW) - 1), _HEADER_ROW] + data_rows, "A1")
    status_ws.merge_cells("A1:G1")
    status_ws.format("A1:G1", {
        "backgroundColor": headline_color,
        "textFormat": {"bold": True, "fontSize": 12},
        "horizontalAlignment": "CENTER",
    })
    status_ws.format("A2:G2", {"textFormat": {"bold": True}})
    status_ws.freeze(rows=2)

    print(f"Updated Current Status: {len(results)} job(s), {len(flagged)} flagged.")
    for r in flagged:
        print(f"  {r.flag}: {r.job_name} -- {r.detail}")


if __name__ == "__main__":
    main()
