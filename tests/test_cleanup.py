from __future__ import annotations

from platform_job_log.cleanup import stale_success_rows

HEADER = ["job_name", "job_type", "expected_at", "actual_start", "completion_time", "status", "notes"]


def _row(job_name, status):
    return [job_name, "frequent", "", "t", "t", status, ""]


def test_keeps_only_the_last_success_row_per_frequent_job():
    rows = [
        HEADER,
        _row("job-a", "success"),   # row 2
        _row("job-a", "success"),   # row 3
        _row("job-a", "success"),   # row 4 -- keep this one (last)
        _row("job-b", "success"),   # row 5 -- keep this one (only one)
    ]
    result = stale_success_rows(rows, HEADER, {"job-a", "job-b"})
    assert result == [3, 2]  # descending order, row 4 and 5 kept


def test_never_touches_failure_rows():
    rows = [
        HEADER,
        _row("job-a", "success"),  # row 2
        _row("job-a", "failed"),   # row 3
        _row("job-a", "success"),  # row 4 -- last success, kept
    ]
    result = stale_success_rows(rows, HEADER, {"job-a"})
    assert result == [2]


def test_ignores_jobs_not_in_the_frequent_set():
    rows = [
        HEADER,
        _row("scheduled-job", "success"),
        _row("scheduled-job", "success"),
    ]
    result = stale_success_rows(rows, HEADER, {"some-other-frequent-job"})
    assert result == []


def test_no_stale_rows_when_only_one_success_per_job():
    rows = [
        HEADER,
        _row("job-a", "success"),
        _row("job-b", "success"),
    ]
    result = stale_success_rows(rows, HEADER, {"job-a", "job-b"})
    assert result == []


def test_empty_run_log_returns_nothing():
    assert stale_success_rows([HEADER], HEADER, {"job-a"}) == []
