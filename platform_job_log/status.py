"""Computes each registered job's current status from the Run Log's raw rows.

Deliberately plain Python, not a live Sheets formula -- the "Current Status"
tab is written by scripts/update_status.py rather than computed in-sheet, so
this logic is unit-testable without ever opening a browser (not something
this session can do) and is easy to get exactly right for two genuinely
different job types.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from platform_job_log.registry import JobSpec

# How long past an expected run before a still-incomplete scheduled job counts
# as overdue rather than just "hasn't reported back yet" -- covers ordinary
# job duration/latency, not a real problem.
_SCHEDULED_GRACE = timedelta(minutes=30)


def _parse(ts: str) -> datetime | None:
    if not ts:
        return None
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


@dataclass
class RunLogRow:
    job_name: str
    job_type: str
    expected_at: str
    actual_start: str
    completion_time: str
    status: str
    notes: str


@dataclass
class JobStatus:
    job_name: str
    job_type: str
    reference_time: str  # expected_at (scheduled) or last success time (frequent)
    last_status: str
    flag: str  # "OK", "OVERDUE", "FAILED", "NO DATA"
    detail: str


def compute_scheduled_status(spec: JobSpec, rows: list[RunLogRow], now: datetime) -> JobStatus:
    candidates = [
        r for r in rows
        if r.job_name == spec.name and r.expected_at and _parse(r.expected_at) <= now
    ]
    if not candidates:
        return JobStatus(spec.name, spec.job_type, "", "", "NO DATA", "no expected row on or before now")

    latest = max(candidates, key=lambda r: _parse(r.expected_at))
    expected_dt = _parse(latest.expected_at)

    if not latest.completion_time:
        if now > expected_dt + _SCHEDULED_GRACE:
            return JobStatus(
                spec.name, spec.job_type, latest.expected_at, "",
                "OVERDUE", f"expected {latest.expected_at}, no completion recorded",
            )
        return JobStatus(spec.name, spec.job_type, latest.expected_at, "", "OK", "within grace period")

    if latest.status.lower() == "failed":
        return JobStatus(spec.name, spec.job_type, latest.expected_at, latest.status, "FAILED", latest.notes)

    return JobStatus(spec.name, spec.job_type, latest.expected_at, latest.status, "OK", "")


def compute_frequent_status(spec: JobSpec, rows: list[RunLogRow], now: datetime) -> JobStatus:
    successes = [
        r for r in rows
        if r.job_name == spec.name and r.completion_time and r.status.lower() == "success"
    ]
    if not successes:
        return JobStatus(spec.name, spec.job_type, "", "", "NO DATA", "no successful run recorded yet")

    latest = max(successes, key=lambda r: _parse(r.completion_time))
    last_success_dt = _parse(latest.completion_time)
    gap = now - last_success_dt

    local_hour = now.astimezone(ZoneInfo(spec.business_hours_timezone)).hour
    start_hour, end_hour = spec.business_hours
    in_business_hours = start_hour <= local_hour < end_hour

    if gap > timedelta(minutes=spec.gap_minutes) and in_business_hours:
        return JobStatus(
            spec.name, spec.job_type, latest.completion_time, latest.status,
            "OVERDUE", f"no success in {int(gap.total_seconds() // 60)} min (business hours)",
        )
    return JobStatus(spec.name, spec.job_type, latest.completion_time, latest.status, "OK", "")


def compute_status(spec: JobSpec, rows: list[RunLogRow], now: datetime | None = None) -> JobStatus:
    now = now or datetime.now(timezone.utc)
    if spec.job_type == "scheduled":
        return compute_scheduled_status(spec, rows, now)
    return compute_frequent_status(spec, rows, now)
