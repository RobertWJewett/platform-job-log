"""log_run_start / log_run_complete -- the two calls any job on the platform
makes to report itself into the shared Job Run Log. Deliberately never
raises: a monitoring failure must never break the job it's monitoring, so
every real error here is caught and printed (surfaces in the job's own
Cloud Run logs) rather than propagated.
"""
from __future__ import annotations

import re
import traceback
from datetime import datetime, timezone

from platform_job_log import config
from platform_job_log.registry import JOBS
from platform_job_log.sheets_client import worksheet

_UPDATED_RANGE_ROW_RE = re.compile(r"![A-Z]+(\d+)")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _appended_row_number(append_response: dict) -> int:
    """Extracts the real row number Sheets actually wrote to from append_row's
    own response (`updates.updatedRange`, e.g. "'Run Log'!A61:G61") -- the
    authoritative, race-safe source, unlike re-reading row count afterward.
    Confirmed live 2026-09-06: three jobs' log_run_start calls landing within
    the same second caused `len(get_all_values())`-after-append to
    mis-attribute rows between them (one job's row went missing, another's
    stayed permanently incomplete) -- concurrent scheduled-job runs are a
    real scenario (a manual trigger overlapping the nightly schedule, two
    jobs sharing a run time), not a hypothetical to design around later."""
    updated_range = append_response["updates"]["updatedRange"]
    match = _UPDATED_RANGE_ROW_RE.search(updated_range)
    return int(match.group(1))


def log_run_start(job_name: str) -> int | None:
    """For a 'scheduled' job: finds today's pre-seeded expected row for this job
    (nearest expected_at <= now with no actual_start yet) and writes actual_start.
    Returns that row's 1-based sheet row number to pass to log_run_complete, or
    None if no matching row exists (or on any error).

    No-op for a 'frequent' job (returns None) -- see registry.py's docstring for
    why those only need log_run_complete.
    """
    spec = JOBS.get(job_name)
    if spec is None or spec.job_type != "scheduled":
        return None
    try:
        ws = worksheet(config.RUN_LOG_TAB)
        rows = ws.get_all_values()
        header = rows[0]
        name_col = header.index("job_name")
        expected_col = header.index("expected_at")
        actual_start_col = header.index("actual_start")
        now = datetime.now(timezone.utc)

        best_row_idx = None
        best_expected = None
        for i, row in enumerate(rows[1:], start=2):  # 1-based, +1 to skip header
            if len(row) <= max(name_col, expected_col, actual_start_col):
                continue
            if row[name_col] != job_name or row[actual_start_col]:
                continue
            expected_str = row[expected_col]
            if not expected_str:
                continue
            expected_dt = datetime.strptime(expected_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if expected_dt > now:
                continue
            if best_expected is None or expected_dt > best_expected:
                best_expected = expected_dt
                best_row_idx = i

        if best_row_idx is None:
            # No pre-seeded row found (a pre-seeding gap, or this job was just
            # registered) -- append a fresh row rather than silently losing this
            # run's evidence entirely. Row number comes from the append response
            # itself (see _appended_row_number), not a follow-up read -- safe
            # even if another job's log_run_start appends at the same instant.
            response = ws.append_row(
                [job_name, spec.job_type, "", _now_iso(), "", "", "no pre-seeded row found"]
            )
            return _appended_row_number(response)

        ws.update_cell(best_row_idx, actual_start_col + 1, _now_iso())
        return best_row_idx
    except Exception:
        print(f"platform_job_log: log_run_start failed for {job_name}: {traceback.format_exc()}", flush=True)
        return None


def log_run_complete(job_name: str, status: str, notes: str = "", row_ref: int | None = None) -> None:
    """Marks completion on the row `row_ref` (from log_run_start), or appends a
    fresh row if row_ref is None -- the normal path for 'frequent' jobs, which
    typically call only this, not log_run_start (see registry.py)."""
    spec = JOBS.get(job_name)
    job_type = spec.job_type if spec else "unknown"
    now = _now_iso()
    try:
        ws = worksheet(config.RUN_LOG_TAB)
        if row_ref is not None:
            header = ws.row_values(1)
            ws.update_cell(row_ref, header.index("completion_time") + 1, now)
            ws.update_cell(row_ref, header.index("status") + 1, status)
            if notes:
                ws.update_cell(row_ref, header.index("notes") + 1, notes)
        else:
            ws.append_row([job_name, job_type, "", now, now, status, notes])
    except Exception:
        print(f"platform_job_log: log_run_complete failed for {job_name}: {traceback.format_exc()}", flush=True)
