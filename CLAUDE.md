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

**Live and verified end-to-end as of 2026-09-06.** The "System Status"
Google Sheet (id in `platform_job_log/config.py`) was created by hand by
Robert (a plain GCP service account has zero Drive storage quota and can't
create a new file itself — confirmed live, see `scripts/setup_sheet.py`'s
docstring) and shared as Editor with three service accounts:
`platform-job-log@...` (this repo's own maintenance job),
`clio-reporting-sync@...`, and `1731274938-compute@developer.gserviceaccount.com`
(rc-webhook-listener's runtime identity, used by `deliver-clio-recordings`).

**Five jobs registered as of 2026-09-06**, all confirmed logging real rows:
`clio-reporting-sync-job`, `lawpay-ingest-job`, `matterkey-maintenance-job`,
`matterkey-lm-index-job` (all `scheduled`), and `deliver-clio-recordings` in
`rc-recording-delivery` (`frequent`). Sheet shared with the runtime service
account of every registered job (`clio-reporting-sync@...`,
`lawpay-connector@...`, `1731274938-compute@developer.gserviceaccount.com`
— shared across `deliver-clio-recordings`, `matterkey-maintenance-job`, and
`matterkey-lm-index-job`, all three's default runtime identity — and
`platform-job-log@...` for this repo's own maintenance job).

`platform-job-log` itself runs as **two** Cloud Run Jobs sharing one image
(`platform-job-log` for the every-15-min Current Status refresh,
`platform-job-log-seed` for the daily 8:00 UTC pre-seed window extension,
via the scheduler job `platform-job-log-seed-scheduled`) — split into two
specifically because a Cloud Scheduler `containerOverrides` body 403s even
with the correct IAM binding in place (see `PLATFORM_OVERVIEW.md`'s Cloud
Run V2 Jobs entry); each has its args baked in at deploy time instead. Both
needed the same per-job `run.invoker` IAM binding documented there too —
applied from the start on both, not discovered the hard way again.

**A real concurrency bug found and fixed registering the last three jobs**:
running all three simultaneously for a first test caused `log_run_start`'s
fallback append path (`len(get_all_values())` read immediately after
`append_row()`) to race between the concurrent processes — one job's row
went missing entirely, another's stayed permanently stuck with no
completion (its `log_run_complete` updated a *different* job's row instead
of its own). Fixed by reading the real row number out of `append_row`'s own
API response (`updates.updatedRange`) instead of a follow-up read — this is
authoritative and safe under concurrency since it reflects the Sheets
API's own placement decision for that specific request. All 7 consumer
jobs/services were redeployed to pick up the fix (cheap, and the bug is
real for any of them, not just the three that happened to trigger it);
the corrupted test rows were deleted from the sheet before re-verifying
with a clean sequential run.

`platform-job-log` itself had to be made **public** on GitHub (matching
`jh-clio-lib`'s precedent) — Cloud Build's anonymous `git clone` can't
authenticate to a private repo, and this repo has no secrets in it (the
spreadsheet ID isn't sensitive on its own).

One real bug caught live during this rollout, worth remembering: the
spreadsheet ID was set locally in `config.py` but not committed before the
first deploy, so the deployed job pulled an older version of this package
with no ID configured and failed with `RuntimeError: No spreadsheet id
configured` — logging failed silently (by design — a monitoring failure must
never break the job it's monitoring) and was only caught by checking the
Cloud Run Job's own stdout logs directly. Same root-cause shape as the
`extra_params` miss on `jh-clio-lib` earlier the same day: always confirm a
git-dependency change is actually pushed, not just saved locally, before
trusting a redeploy to pick it up.

See `PROJECT_TRACKER.md` for the rollout list of what's registered vs. still
pending expansion.

**Expanded to 24 registered jobs and given real dashboard styling, 2026-09-07.**
Robert flagged the Run Log tab hitting ~1000 rows and asked how to make the
sheet dashboard-style rather than a wall of raw rows. Root cause: every
`frequent`-type job's *successful* run appended a brand-new row forever, even
though `status.py`'s `compute_frequent_status` only ever reads the single
most recent one — `deliver-clio-recordings` alone (every 15 min) produced
most of the existing bloat in ~2 days, and registering three more frequent
jobs the same day (`mail-tracking-sync` /30min, `poll-clio-grow` /10min,
`retry-call-recordings` /5min) would have made growth roughly 5-6x worse.

Fixed two ways, both requested together ("go ahead with both", accepting the
tradeoff that a frequent job's Run Log history now shows only its last
success plus any failures, not a row for every single run — nothing reads
that per-run history, and each job's own Cloud Run execution log already has
the real per-run audit trail if it's ever needed):

- **`logger.py`'s `log_run_complete`**: a `frequent`-type job's successful
  run now **upserts** a single standing row per job (finds the last existing
  row for that job with `status=success` and overwrites `actual_start`/
  `completion_time`/`status`/`notes` in place) instead of appending a new
  row every time. A **failure** still always appends a fresh, distinct row —
  those are rare and worth keeping as dated history. `scheduled`-type jobs
  and the "no pre-seeded row found" fallback path are unaffected (still
  append). See `tests/test_logger.py`'s `FakeWorksheet`-based tests for the
  upsert/append boundary cases.
- **`platform_job_log/formatting.py`** (new, `setup-format` CLI command, not
  scheduled — one-time/re-run-safe): colors the "Current Status" tab's data
  rows by `flag` value via Sheets conditional formatting (red=FAILED,
  orange=OVERDUE, gray=NO DATA, green=OK) and reorders tabs so "Current
  Status" opens first, "Run Log" second. Only needs the ordinary
  `spreadsheets` scope already used everywhere else in this package —
  conditional formatting, cell formatting, and tab reordering are plain
  Sheets API operations, not Drive operations, unlike `setup_sheet.py`'s
  sharing step. Run once via `gcloud run jobs execute platform-job-log
  --args=setup-format --region=us-central1` after a deploy (or any time the
  rules need re-applying — it clears and re-adds its own conditional format
  rules first, so re-running is safe).
- **`scripts/update_status.py`** rewritten to sort jobs (FAILED → OVERDUE →
  NO DATA → OK, alphabetical within each) so anything needing attention
  floats to the top, and to write a merged, colored headline row 1
  ("✅ All N job(s) healthy" / "⚠ N job(s) need attention — checked ...")
  above the column headers (now row 2) and data (now row 3+). Frozen rows
  bumped from 1 to 2 to match.

Also folded into this session's work: the remaining 19 known Cloud Scheduler
jobs on the platform were registered and wired (bringing the total from the
initial 5-job pilot to 24) — see `PROJECT_TRACKER.md` for the full list.
One pre-existing, unrelated finding surfaced while triggering them for the
first time: the `nightly-lm-duplicate-check` Cloud Scheduler trigger was
sitting **PAUSED** — not something this session changed, but worth Robert
confirming whether that's intentional, since on its normal schedule it
currently won't fire at all.

## Open items (from the original design brief)

- Review cadence — Robert picking a daily-glance habit, not a blocker to building.
- Whether "start" rows are worth writing for every scheduled job, or only
  ones long enough that a hang (not just a crash) is a real risk — currently
  writing them for `clio-reporting-sync-job` (a multi-minute job where a hang
  is plausible), not for `frequent`-type jobs (short-lived, low hang risk).
- If a future job's failure mode ever needs faster-than-daily attention, a
  cheap real-time nudge (Pushover, etc.) layered on top remains a reasonable
  option to revisit — nothing in the current job set needs it today.
