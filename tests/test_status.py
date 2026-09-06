from __future__ import annotations

from datetime import datetime, timezone

from platform_job_log.registry import JobSpec
from platform_job_log.status import RunLogRow, compute_status

SCHEDULED = JobSpec(name="nightly-thing", job_type="scheduled", cron="0 3 * * *")
FREQUENT = JobSpec(name="frequent-thing", job_type="frequent", gap_minutes=60,
                    business_hours=(7, 19), business_hours_timezone="America/Chicago")


def row(**kwargs):
    base = dict(job_name="", job_type="", expected_at="", actual_start="",
                completion_time="", status="", notes="")
    base.update(kwargs)
    return RunLogRow(**base)


def test_scheduled_ok_when_completed():
    rows = [row(job_name="nightly-thing", expected_at="2026-09-06T03:00:00Z",
                completion_time="2026-09-06T03:05:00Z", status="success")]
    now = datetime(2026, 9, 6, 4, 0, tzinfo=timezone.utc)
    result = compute_status(SCHEDULED, rows, now)
    assert result.flag == "OK"


def test_scheduled_within_grace_period_is_ok():
    rows = [row(job_name="nightly-thing", expected_at="2026-09-06T03:00:00Z")]
    now = datetime(2026, 9, 6, 3, 10, tzinfo=timezone.utc)  # 10 min after, still in grace
    result = compute_status(SCHEDULED, rows, now)
    assert result.flag == "OK"


def test_scheduled_overdue_past_grace_with_no_completion():
    rows = [row(job_name="nightly-thing", expected_at="2026-09-06T03:00:00Z")]
    now = datetime(2026, 9, 6, 4, 0, tzinfo=timezone.utc)  # 1hr after, past 30min grace
    result = compute_status(SCHEDULED, rows, now)
    assert result.flag == "OVERDUE"


def test_scheduled_failed_status_flagged():
    rows = [row(job_name="nightly-thing", expected_at="2026-09-06T03:00:00Z",
                completion_time="2026-09-06T03:05:00Z", status="failed", notes="boom")]
    now = datetime(2026, 9, 6, 4, 0, tzinfo=timezone.utc)
    result = compute_status(SCHEDULED, rows, now)
    assert result.flag == "FAILED"
    assert result.detail == "boom"


def test_scheduled_no_data_before_first_expected_run():
    rows = [row(job_name="nightly-thing", expected_at="2026-09-07T03:00:00Z")]  # future
    now = datetime(2026, 9, 6, 4, 0, tzinfo=timezone.utc)
    result = compute_status(SCHEDULED, rows, now)
    assert result.flag == "NO DATA"


def test_scheduled_uses_the_most_recent_applicable_expected_row():
    rows = [
        row(job_name="nightly-thing", expected_at="2026-09-04T03:00:00Z",
            completion_time="2026-09-04T03:05:00Z", status="success"),
        row(job_name="nightly-thing", expected_at="2026-09-05T03:00:00Z"),  # not completed
    ]
    now = datetime(2026, 9, 5, 4, 0, tzinfo=timezone.utc)  # 1hr after the 2nd, past grace
    result = compute_status(SCHEDULED, rows, now)
    assert result.reference_time == "2026-09-05T03:00:00Z"
    assert result.flag == "OVERDUE"


def test_frequent_ok_within_gap_during_business_hours():
    rows = [row(job_name="frequent-thing", completion_time="2026-09-06T14:50:00Z", status="success")]
    now = datetime(2026, 9, 6, 15, 0, tzinfo=timezone.utc)  # 10 min gap, 10am Chicago
    result = compute_status(FREQUENT, rows, now)
    assert result.flag == "OK"


def test_frequent_overdue_when_gap_exceeds_threshold_during_business_hours():
    rows = [row(job_name="frequent-thing", completion_time="2026-09-06T13:00:00Z", status="success")]
    now = datetime(2026, 9, 6, 15, 0, tzinfo=timezone.utc)  # 2hr gap, 10am Chicago (in business hours)
    result = compute_status(FREQUENT, rows, now)
    assert result.flag == "OVERDUE"


def test_frequent_not_flagged_outside_business_hours_even_with_large_gap():
    rows = [row(job_name="frequent-thing", completion_time="2026-09-06T13:00:00Z", status="success")]
    # 2am Chicago the next day -- big gap, but outside the 7am-7pm window
    now = datetime(2026, 9, 7, 7, 0, tzinfo=timezone.utc)
    result = compute_status(FREQUENT, rows, now)
    assert result.flag == "OK"


def test_frequent_no_data_when_never_succeeded():
    result = compute_status(FREQUENT, [], datetime(2026, 9, 6, 15, 0, tzinfo=timezone.utc))
    assert result.flag == "NO DATA"


def test_frequent_ignores_failed_rows_when_looking_for_last_success():
    rows = [
        row(job_name="frequent-thing", completion_time="2026-09-06T13:00:00Z", status="success"),
        row(job_name="frequent-thing", completion_time="2026-09-06T14:55:00Z", status="failed"),
    ]
    now = datetime(2026, 9, 6, 15, 0, tzinfo=timezone.utc)  # 2hr since last SUCCESS, business hours
    result = compute_status(FREQUENT, rows, now)
    assert result.flag == "OVERDUE"
