"""The explicit list of jobs registered with the Job Run Log -- not an
auto-discovered list of every Cloud Scheduler job on the platform. Adding a
job here is a deliberate step (per the design brief's "register the
highest-stakes jobs first, expand from there").

Two job types, matching two different failure-detection strategies:

- "scheduled": runs once (or a small, fixed number of times) per day, on a
  known cron schedule. A missing run is only detectable by knowing in
  advance when it was expected -- see scripts/seed_scheduled.py, which
  pre-seeds expected-run rows into the Run Log ahead of time.
- "frequent": runs many times per day (every few minutes). A missing run is
  self-evident from the gap since the last successful row alone -- no
  pre-seeding needed. Flagged only if no success in `gap_minutes` minutes,
  and only within `business_hours` (to match "I only need to know if it's
  failed consistently for over an hour between 7am and 7pm" -- a job that's
  quiet from 7pm-7am might just have nothing to do that hour, not be broken).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JobSpec:
    name: str
    job_type: str  # "scheduled" or "frequent"
    cron: str | None = None  # required for "scheduled"
    timezone: str = "UTC"  # timezone the cron expression is defined in
    gap_minutes: int = 60  # "frequent" only: flag if no success within this long
    business_hours: tuple[int, int] = (7, 19)  # "frequent" only: local hour range to evaluate in
    business_hours_timezone: str = "America/Chicago"
    notes: str = ""


JOBS: dict[str, JobSpec] = {
    "clio-reporting-sync-job": JobSpec(
        name="clio-reporting-sync-job",
        job_type="scheduled",
        cron="0 3 * * 0-5",
        timezone="UTC",
        notes="Nightly Clio reporting warehouse sync. Skips Saturdays (standing maintenance window).",
    ),
    "deliver-clio-recordings": JobSpec(
        name="deliver-clio-recordings",
        job_type="frequent",
        gap_minutes=60,
        business_hours=(7, 19),
        business_hours_timezone="America/Chicago",
        notes="RC call/voicemail recording delivery to Clio Documents API, every 15 minutes.",
    ),
}
