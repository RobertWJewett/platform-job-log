# CLAUDE.md — platform-job-log

## Required reading (session start)

Before doing any work in this repo, read:
- `~/my-automations/jh-law-scripts/PLATFORM_OVERVIEW.md` — infra/environment state
- `~/my-automations/jh-law-scripts/PROJECT_TRACKER.md` — active worklist across all projects
- `platform-job-monitoring-brief.md` (this repo, once copied in — currently at
  `~/my-automations/clio-reporting/platform-job-monitoring-brief.md`) — the full design
  rationale: why an in-job alert can't catch a job that never starts at all, the
  dead-man's-switch principle, and the decisions that shaped this build.

## What this is

A shared, platform-wide job monitoring system — **not specific to Clio or any
one project**, even though it was born out of a real incident while building
`clio-reporting` (a scheduler-invoker IAM bug left that project's nightly
sync silently failing for its first day in production, discovered only
because someone happened to check).

The core idea: an alert that lives *inside* the job it's watching can never
catch that job failing to start at all (a crashed container, a disabled
billing account, a laptop that never woke up). The fix is a **dead man's
switch** — something external keeps time, independent of whether the job
ever runs. Concretely: a Google Sheet ("JH Law — Job Run Log") with
pre-seeded "expected run" rows for scheduled jobs, so a blank row next to an
already-passed expected time is itself the failure signal, visible on a
normal morning glance — no push notification, no SMS, matching Robert's
explicit preference (every failure on this platform needs his own manual
review to resolve regardless of how fast he hears about it).

## Two job types, two different checks

- **`scheduled`** — runs once (or a small fixed number of times) per day on
  a known cron schedule. Checked via pre-seeded expected-run rows
  (`scripts/seed_scheduled.py`) — a missing run is only detectable by
  knowing in advance when it was expected.
- **`frequent`** — runs many times per day (every few minutes). No
  pre-seeding needed: a missing run is self-evident from the gap since the
  last logged success alone. Per Robert's explicit rule (2026-09-06): flag
  only if there's been no success in the last hour, and only within business
  hours (7am–7pm Central) — a quiet stretch outside those hours isn't
  necessarily broken.

See `platform_job_log/registry.py` for the actual registered jobs and
`platform_job_log/status.py` for the flag logic (unit-tested in
`tests/test_status.py` — the "Current Status" tab is computed by Python via
`scripts/update_status.py`, not live Sheets formulas, since this session has
no way to visually verify spreadsheet formulas render correctly).

## Where things live

| What | Where |
|---|---|
| Repo | `~/my-automations/platform-job-log` |
| Remote | `github.com/RobertWJewett/platform-job-log` (private) |
| GCP project | `jh-law-rc-clio-personal`, `us-central1` — same as everything else on the platform |
| The Sheet | "JH Law — Job Run Log", created by `scripts/create_sheet.py`, shared with `robert@jewettlaw.net`. Spreadsheet ID lives in `platform_job_log/config.py` |
| Service account (for local/Cloud Run jobs authenticating as themselves) | Each consuming job uses its own existing runtime service account — Sheets access is governed by sharing the Sheet with that SA's email directly, not by any new IAM role. See "Registering a new job" below |

## Registering a new job

1. Add a `JobSpec` to `platform_job_log/registry.py` (`scheduled` or `frequent`).
2. **Share the Google Sheet with that job's own runtime service account's email**
   (Editor access) — this is the step most likely to be forgotten. A job's
   own Cloud Run/GCP identity needs to be a direct Sheets collaborator; being
   in the same GCP project grants nothing here.
3. Add `platform-job-log @ git+https://github.com/RobertWJewett/platform-job-log@main`
   to that job's `requirements.txt`. If its Dockerfile is based on a
   `-slim` image, it needs `git` installed (`apt-get install -y git`) for the
   `git+https` dependency to resolve — a real build failure hit twice already
   on this platform (`clio-reporting`, then here) before being fixed both
   times the same way.
4. For a `scheduled` job: call `log_run_start(job_name)` at the top of the
   run, keep the returned row reference, and `log_run_complete(job_name,
   status, notes, row_ref=...)` at the end (success or failure — wrap in
   try/except so the completion call always fires).
5. For a `frequent` job: just call `log_run_complete(job_name, "success" |
   "failed", notes)` once per invocation — no `log_run_start` needed.
6. If it's `scheduled`, re-run `scripts/seed_scheduled.py` so it gets
   pre-seeded expected rows going forward.

Both logging calls catch their own exceptions and never raise — a
monitoring failure must never break the job it's monitoring.

## Current status

Built 2026-09-06. Two jobs registered as the initial proof of the pattern
before expanding further: `clio-reporting-sync-job` (scheduled) and
`deliver-clio-recordings` (frequent, in `rc-recording-delivery`). See
`PROJECT_TRACKER.md` for what's actually live vs. still pending.

## Open items (from the original design brief)

- Review cadence — Robert picking a daily-glance habit, not a blocker to building.
- Whether "start" rows are worth writing for every scheduled job, or only
  ones long enough that a hang (not just a crash) is a real risk — currently
  writing them for `clio-reporting-sync-job` (a multi-minute job where a hang
  is plausible), not for `frequent`-type jobs (short-lived, low hang risk).
- If a future job's failure mode ever needs faster-than-daily attention, a
  cheap real-time nudge (Pushover, etc.) layered on top remains a reasonable
  option to revisit — nothing in the current job set needs it today.
