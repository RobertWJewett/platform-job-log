"""One-time (safe to re-run) cleanup of stale Run Log rows left behind by
'frequent'-type jobs from before log_run_complete started upserting a single
standing row per job on success (see logger.py). Deletes every
now-redundant older success row for each frequent job, keeping only the most
recent one -- failure rows are never touched, and scheduled-type jobs are
never touched (their one-row-per-day volume was never the problem).

Safe to run more than once: after the first run there is at most one
success row per frequent job left, so a second run finds nothing to delete.
"""
from __future__ import annotations

from platform_job_log import config
from platform_job_log.registry import JOBS
from platform_job_log.sheets_client import worksheet


def stale_success_rows(rows: list[list[str]], header: list[str], frequent_job_names: set[str]) -> list[int]:
    """Returns 1-based sheet row numbers safe to delete: every row but the
    last (most recent) success row for each frequent job in
    `frequent_job_names`. Descending order, ready to feed straight into a
    batch of deleteDimension requests without index shifting."""
    name_col = header.index("job_name")
    status_col = header.index("status")

    success_rows_by_job: dict[str, list[int]] = {}
    for i, row in enumerate(rows[1:], start=2):  # 1-based, +1 to skip header
        if len(row) <= max(name_col, status_col):
            continue
        name = row[name_col]
        if name in frequent_job_names and row[status_col].strip().lower() == "success":
            success_rows_by_job.setdefault(name, []).append(i)

    to_delete: list[int] = []
    for row_indices in success_rows_by_job.values():
        to_delete.extend(row_indices[:-1])  # keep the last (most recent), drop the rest
    return sorted(to_delete, reverse=True)


def cleanup_frequent_history(spreadsheet_id: str | None = None) -> None:
    ws = worksheet(config.RUN_LOG_TAB, spreadsheet_id)
    rows = ws.get_all_values()
    frequent_job_names = {name for name, spec in JOBS.items() if spec.job_type == "frequent"}

    to_delete = stale_success_rows(rows, rows[0], frequent_job_names)
    if not to_delete:
        print("No stale frequent-job success rows to clean up.")
        return

    requests = [
        {"deleteDimension": {"range": {
            "sheetId": ws.id, "dimension": "ROWS", "startIndex": r - 1, "endIndex": r,
        }}}
        for r in to_delete
    ]
    ws.spreadsheet.batch_update({"requests": requests})
    print(f"Deleted {len(to_delete)} stale frequent-job success row(s) from '{ws.title}'.")


if __name__ == "__main__":
    cleanup_frequent_history()
