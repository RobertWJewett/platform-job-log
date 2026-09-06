# Platform Job Monitoring — Design Brief

_A platform-wide gap, surfaced while building the Clio Reporting Platform
but not specific to it. This is the exact thing `PROJECT_TRACKER.md` already
proposed and never built, after a real incident — see below._

**Revised 2026-09-06**: originally scoped around Healthchecks.io + SMS
alerting (see "Superseded approach" at the bottom). Robert reconsidered:
he doesn't need real-time notification, since every failure this platform
produces requires his own manual review to resolve anyway — a push alert
at 3:07 AM doesn't get anything fixed faster than the same information
sitting in a log he checks each morning. The design below replaces that
plan with a logged, reviewed-on-demand approach: a Google Sheet showing,
per job, next scheduled run / actual run time / completion time /
completion status.

## Why this is worth fixing now, not later

This isn't a new idea — it's a documented, known gap that got proposed once
and quietly dropped. On 2026-07-09, the GCP billing account for
`jh-law-rc-clio-personal` was closed for ~20.5 hours: every webhook 500'd,
and all four nightly Cloud Run Jobs silently never started (Cloud
Scheduler's own control plane is itself billing-gated). The existing
`job_alert.py`-style failure alerting never fired — **because it can only
alert from inside a running container, and a billing-disabled outage
prevents the container from ever starting.** An external watchdog was
proposed at the time and never built.

That same structural weakness — an alert mechanism that lives inside the
thing it's supposed to watch — is also why several other real incidents on
this platform went unnoticed for weeks or months instead of hours: a stale
crontab entry silently broke a Lawmatics contact sync for 6+ weeks with no
error; duplicate Calendly webhook subscriptions silently double-processed
bookings for months; RingCentral's answer-rate reporting silently measured
the wrong phone line for the project's entire existence; `clio-hotstrings`
forgot to redeploy its nightly cache-population job after a field change and
it ran stale code for two days while still reporting `status: ok`.
A second, live example surfaced during the Clio Reporting Platform's own
first real night: `clio-reporting-sync-job`'s 3:00 AM run 403'd on a Cloud
Run V2 Jobs IAM quirk and had been silently broken since deployment — found
only because someone happened to check. None of these looked like failures
from the inside. That's the pattern worth solving once, centrally, rather
than continuing to discover it project by project.

## The underlying principle still holds — just logged, not alerted

The standard pattern for "did this job actually run" is a **dead man's
switch**: something outside the job itself has to be the one keeping time,
because a job that never starts (crashed container, disabled billing
account, a laptop that never woke up) can't be the one reporting its own
absence. That principle doesn't go away just because Robert doesn't want a
text message — it just changes what the external thing does with the
information: instead of raising an alarm, it makes the absence *visible* the
next time someone looks.

Concretely, that means the "next scheduled run" column can't be filled in
by the job when it runs — if the job never runs, nothing would ever write
that row, and a job that silently stopped existing would just look like a
sheet with no evidence anything was ever expected. **Expected-run rows have
to be pre-seeded ahead of time**, from each job's known cron schedule,
independent of whether the job actually fires. Then a job filling in its own
"actual start / completion / status" is just confirming a row that was
already sitting there — and a blank actual/completion next to an expected
time that's already passed is the failure signal, visible on a normal
morning check with no push notification required.

This still complements, not replaces, `job_alert.py` — the log's status
column is where an in-job error gets recorded (what broke); the pre-seeded
expected row is what catches the job never showing up at all (that it
didn't run).

## Recommended design: one Google Sheet, two tabs

**"JH Law — Job Run Log"**, built in the same GCP project
(`jh-law-rc-clio-personal`) as everything else, using a service-account
key stored in Secret Manager — same credential-gating convention the rest
of the platform already follows, no new auth system to maintain (this is
the reason Google Sheets won out over Excel/OneDrive here: writing to
OneDrive programmatically would mean standing up a second, Microsoft-side
auth flow — Graph API app registration, admin consent, token refresh —
alongside the GCP one this platform already runs, for no real gain).

- **Current Status tab** — one row per job, showing its most recent
  expected run, actual start, completion time, and status, plus (via
  conditional formatting) a red highlight for any row where the expected
  time has passed with actual/completion still blank, or where status is
  a failure. This is the tab Robert actually looks at; everything else
  supports it.
- **Run Log tab** — append-only history, one row per job per scheduled
  run: job name, expected run time, actual start time, completion time,
  status (success / failed / no-show), notes (error message, if any).
  Rows are never overwritten in place — same append-only convention the
  reporting platform's own snapshot tables already use, so a later
  "how often does this job actually fail" review is a filter, not a
  rebuild.

**Pre-seeding mechanism**: since every job's cron schedule is already
known and rarely changes, generate a rolling window of future expected-run
rows (e.g., the next 60 days) directly from each job's schedule, refreshed
periodically so the window never runs out. This can be as simple as a
small script that regenerates the window whenever it's run (by hand, or on
its own modest schedule) — it doesn't need to be perfectly real-time,
since the whole point is that the expected row is sitting there well in
advance of the run it describes.

**Shared write helper**: one small Python module (not a per-job copy — same
principle as `job_alert.py`'s already-flagged per-job-duplication problem),
using `gspread` + the service-account key, exposing something like
`log_run_start(job_name)` and `log_run_complete(job_name, status,
notes="")`. Callable from Cloud Run jobs and local launchd/cron scripts
alike — the local jobs (`ringcentral`'s reporting, `clio-hotstrings`'
client-folder-nav batch job, `scan-temp-filer`) have zero visibility today
and cost nothing to add, since this is just two HTTP calls via the Sheets
API, no email or SMS infrastructure involved.

## How to get there from here

1. **Create the Google Sheet and a service account** scoped to just that
   sheet; store the service account key in Secret Manager, share the sheet
   with the service account's email.
2. **Build the pre-seeding script** — reads each job's known cron schedule,
   writes/extends the rolling window of expected-run rows into the Run Log
   tab.
3. **Build the shared logging helper**, `log_run_start` / `log_run_complete`,
   living in `jh-clio-lib` (not Clio/Lawmatics-specific, but matches the
   platform's existing precedent for "one shared thing everyone imports")
   or alongside `job_alert.py`'s conventions in `jh-law-scripts` — a small
   decision, not a blocking one.
4. **Build the Current Status tab** as a formula-driven view over the Run
   Log tab (e.g. `QUERY`/`FILTER` pulling each job's latest row), with
   conditional formatting rules for overdue-and-blank and failed rows.
5. **Register the highest-stakes jobs first** — anything touching trust
   funds or client money: `lawpay-ingest-job`, `matterkey-maintenance-job`,
   and `clio-reporting-sync-job` — the last of these now doubly justified,
   having already proven it can fail silently during its own first week in
   production.
6. **Expand to everything else**, Cloud Run Jobs and local launchd/cron
   alike.
7. **Retire the open incident note**: the 2026-07-09 billing-outage entry
   in `jh-law-scripts`'s shared docs proposed an external watchdog and never
   closed it out — this closes that loop, in the lighter-weight form Robert
   actually wants. Document the convention itself in `PLATFORM_OVERVIEW.md`
   so every future scheduled job gets registered in the log as part of
   being built, not bolted on after the fact.

## Open items

- Review cadence — worth Robert picking a habit (e.g., a daily morning
  glance at the Current Status tab) now, before the sheet exists, so it
  doesn't become a thing that's built but not actually checked. Not a
  blocker to building it.
- Where the shared logging helper actually lives (`jh-clio-lib` vs.
  `jh-law-scripts`) — a small decision, not a blocking one.
- Whether "start" rows are worth writing for every job, or only for the
  ones long enough that a hang (not just a crash) is a real risk worth
  distinguishing from "did it finish."
- If a future job ever comes with real time pressure — something where a
  multi-hour delay before Robert's next check would cause actual harm —
  that job specifically might still warrant a real-time nudge (even a
  cheap one, like Pushover) layered on top of this log rather than relying
  on it alone. Nothing in the current job set rises to that today.

## Superseded approach (kept for reference, not the current plan)

The original version of this brief recommended Healthchecks.io — an
external heartbeat/dead-man's-switch service with built-in SMS via Twilio
(free tier: 20 checks, 5 SMS/month) — precisely because it doesn't live
inside the infrastructure it watches. Robert decided real-time SMS isn't
needed, since every failure here requires his own manual fix regardless of
how fast he learns about it. The dead-man's-switch *principle* carries over
into the design above (pre-seeded expected rows play the same role
Healthchecks.io's external clock would have); what's dropped is the
external SaaS account, the SMS delivery, and the per-check pricing tiers
that came with it. Healthchecks.io (or Pushover, as a cheap real-time
add-on) stays a reasonable option to revisit if a future job's failure mode
ever needs faster-than-daily attention.
