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
    "lawpay-ingest-job": JobSpec(
        name="lawpay-ingest-job",
        job_type="scheduled",
        cron="0 13 * * 0-5",
        timezone="UTC",
        notes="Nightly LawPay settled-trust-transaction ingest/reconcile (ingest only, no Clio posting). "
              "Skips Saturdays.",
    ),
    "matterkey-maintenance-job": JobSpec(
        name="matterkey-maintenance-job",
        job_type="scheduled",
        cron="0 8 * * 0-5",
        timezone="UTC",
        notes="Nightly MatterKey custom-field extract/mint across all Clio matters. Skips Saturdays.",
    ),
    "matterkey-lm-index-job": JobSpec(
        name="matterkey-lm-index-job",
        job_type="scheduled",
        cron="0 9 * * 0-5",
        timezone="UTC",
        notes="Nightly Clio<->Lawmatics MatterKey index build (clio_matterkey_index in Firestore). "
              "Skips Saturdays.",
    ),
    # ── email-processor (single service, 9 scheduler-triggered routes) ──────
    "retry-calendly-bookings": JobSpec(
        name="retry-calendly-bookings",
        job_type="scheduled",
        cron="0 7 * * 0-5",
        timezone="UTC",
        notes="Retries Calendly bookings that failed to file on first attempt. Skips Saturdays.",
    ),
    "renew-graph-subscription": JobSpec(
        name="renew-graph-subscription",
        job_type="scheduled",
        cron="0 0 */2 * *",
        timezone="UTC",
        notes="Renews the Microsoft Graph mailbox-change subscription every 2 days (subscriptions expire).",
    ),
    "nightly-lm-duplicate-check": JobSpec(
        name="nightly-lm-duplicate-check",
        job_type="scheduled",
        cron="0 7 * * 0-5",
        timezone="America/Chicago",
        notes="Nightly Lawmatics duplicate-contact/matter scan. Skips Saturdays.",
    ),
    "calendly-filing-digest-nightly": JobSpec(
        name="calendly-filing-digest-nightly",
        job_type="scheduled",
        cron="0 7 * * 0-5",
        timezone="America/Chicago",
        notes="Nightly digest email summarizing Calendly bookings filed the prior day. Skips Saturdays.",
    ),
    "renew-clio-webhooks": JobSpec(
        name="renew-clio-webhooks",
        job_type="scheduled",
        cron="0 5 * * *",
        timezone="America/Chicago",
        notes="Daily renewal of Clio Manage webhook subscriptions (no Saturday skip -- webhooks expire "
              "on a fixed clock regardless of maintenance window).",
    ),
    "mail-tracking-sync": JobSpec(
        name="mail-tracking-sync",
        job_type="frequent",
        gap_minutes=60,
        business_hours=(7, 19),
        business_hours_timezone="America/Chicago",
        notes="Syncs USPS/carrier mail-tracking events into Firestore, every 30 minutes.",
    ),
    "poll-clio-grow": JobSpec(
        name="poll-clio-grow",
        job_type="frequent",
        gap_minutes=60,
        business_hours=(7, 19),
        business_hours_timezone="America/Chicago",
        notes="Polls Clio Grow for new intakes, every 10 minutes.",
    ),
    "refresh-clio-manage-token": JobSpec(
        name="refresh-clio-manage-token",
        job_type="scheduled",
        cron="0 7 */25 * *",
        timezone="UTC",
        notes="Refreshes the long-lived Clio Manage OAuth token before its ~30-day expiry. Runs every 25 days.",
    ),
    "refresh-clio-grow-token": JobSpec(
        name="refresh-clio-grow-token",
        job_type="scheduled",
        cron="0 6 */25 * *",
        timezone="UTC",
        notes="Refreshes the long-lived Clio Grow OAuth token before its ~30-day expiry. Runs every 25 days.",
    ),
    # ── email-processor (separate Cloud Run Jobs, shared image, different entrypoints) ──
    "ntc-letters-sweep-job": JobSpec(
        name="ntc-letters-sweep-job",
        job_type="scheduled",
        cron="0 9 * * 0-5",
        timezone="UTC",
        notes="Nightly NTC (notice-to-client) letters sweep, --window 7 --apply. Skips Saturdays. "
              "Registered under the Cloud Run Job resource name (scheduler trigger is "
              "'ntc-letters-sweep-nightly').",
    ),
    "clients-contact-sync-job": JobSpec(
        name="clients-contact-sync-job",
        job_type="scheduled",
        cron="0 7 * * 1-5",
        timezone="UTC",
        notes="Nightly sync of Firestore clio_matters client/prospect emails into the Outlook Clients "
              "contact folder. Weekdays only (already excludes Sat+Sun). Must run after nightly-clio-sync. "
              "Registered under the Cloud Run Job resource name (scheduler trigger is "
              "'clients-contact-sync-nightly').",
    ),
    # ── rc-recording-delivery ────────────────────────────────────────────────
    "retry-call-recordings": JobSpec(
        name="retry-call-recordings",
        job_type="frequent",
        gap_minutes=60,
        business_hours=(7, 19),
        business_hours_timezone="America/Chicago",
        notes="Retries RC call/voicemail recordings that failed delivery to Clio, every 5 minutes.",
    ),
    "renew-rc-webhook": JobSpec(
        name="renew-rc-webhook",
        job_type="scheduled",
        cron="0 6 * * *",
        timezone="UTC",
        notes="Daily renewal of the RingCentral webhook subscription.",
    ),
    # ── clio-email-filer ─────────────────────────────────────────────────────
    "clio-filer-archive-closed-nightly": JobSpec(
        name="clio-filer-archive-closed-nightly",
        job_type="scheduled",
        cron="0 9 * * 0-5",
        timezone="UTC",
        notes="Nightly archive of completed Clio tasks. Skips Saturdays.",
    ),
    "clio-filer-file-sent-items-nightly": JobSpec(
        name="clio-filer-file-sent-items-nightly",
        job_type="scheduled",
        cron="0 10 * * 0-5",
        timezone="UTC",
        notes="Nightly filing of sent-items emails into Clio. Skips Saturdays.",
    ),
    # ── other platform jobs ──────────────────────────────────────────────────
    "activecampaign-badexperience-nightly": JobSpec(
        name="activecampaign-badexperience-nightly",
        job_type="scheduled",
        cron="0 11 * * 0-5",
        timezone="UTC",
        notes="Nightly matter-level BadExperience check against ActiveCampaign/Lawmatics data. Skips Saturdays.",
    ),
    "clio-phone-backfill-weekly": JobSpec(
        name="clio-phone-backfill-weekly",
        job_type="scheduled",
        cron="0 5 * * 0",
        timezone="UTC",
        notes="Weekly phone-number-format wash for Clio contacts (idempotent). Runs Sundays only. "
              "Registered under the scheduler job name (Cloud Run Job resource is 'clio-phone-backfill-job').",
    ),
    "clio-hotstrings-populate-nightly": JobSpec(
        name="clio-hotstrings-populate-nightly",
        job_type="scheduled",
        cron="0 4 * * 0-5",
        timezone="UTC",
        notes="Nightly wash-and-repopulate of hotstrings_cache/matters + hotstrings_field_values from "
              "live Clio data. Skips Saturdays.",
    ),
    "nightly-clio-sync": JobSpec(
        name="nightly-clio-sync",
        job_type="scheduled",
        cron="0 6 * * 1-5",
        timezone="UTC",
        notes="Nightly Clio matters -> Firestore sync (clio_matters + phone/email/cause reverse indexes). "
              "Weekdays only (already excludes Sat+Sun). Registered under the scheduler job name "
              "(Cloud Run Job resource is 'clio-sync-job').",
    ),
}
