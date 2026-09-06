#!/usr/bin/env python3
"""One-time (or re-run-safe) setup for the "JH Law - Job Run Log" Google
Sheet: builds the two tabs with headers, and shares it with every
registered job's own runtime service account (plus any extra emails
given).

**The spreadsheet must already exist and be shared as an Editor with
whichever identity runs this script** -- a plain (non-Workspace) GCP
service account has zero Drive storage quota and cannot create a new
Sheet itself (confirmed live 2026-09-06: `spreadsheets.create` 403s with
"The user's Drive storage quota has been exceeded"). A human creates the
blank sheet by hand in the Sheets web UI and shares it with the setup
identity once; this script does everything after that point.

Usage:
    python3 scripts/setup_sheet.py --share-with extra@example.com
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import google.auth  # noqa: E402
import gspread  # noqa: E402

from platform_job_log import config  # noqa: E402
from platform_job_log.registry import JOBS  # noqa: E402

# Full Drive scope (not the narrower drive.file the rest of the package uses)
# is required here specifically: sharing a file this identity didn't create
# and wasn't explicitly opened-via-Drive needs the broader scope, confirmed
# live 2026-09-06 (drive.file 404'd on Permissions.create for exactly this
# reason). Regular log_run_start/log_run_complete calls never need this --
# only this one-time admin operation does.
_SETUP_SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--share-with", action="append", default=[],
                         help="Extra email(s) to share as Editor, beyond the registered jobs' own service accounts")
    args = parser.parse_args()

    credentials, _ = google.auth.default(scopes=_SETUP_SCOPES)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_key(config.SPREADSHEET_ID)

    run_log = sh.sheet1
    if run_log.title != config.RUN_LOG_TAB:
        run_log.update_title(config.RUN_LOG_TAB)
    if run_log.row_values(1) != config.RUN_LOG_HEADERS:
        run_log.update("A1", [config.RUN_LOG_HEADERS])
        run_log.freeze(rows=1)

    existing_titles = [ws.title for ws in sh.worksheets()]
    if config.CURRENT_STATUS_TAB not in existing_titles:
        status = sh.add_worksheet(title=config.CURRENT_STATUS_TAB, rows=100, cols=8)
        status.update("A1", [["job_name", "job_type", "reference_time", "last_status", "flag", "detail", "checked_at"]])
        status.freeze(rows=1)

    print("Tabs:", [ws.title for ws in sh.worksheets()])

    already_shared = {p["emailAddress"] for p in sh.list_permissions() if "emailAddress" in p}
    to_share = {spec.name: None for spec in JOBS.values()}  # placeholder, resolved below
    service_account_emails = _service_account_emails_for_registered_jobs()
    for email in service_account_emails + args.share_with:
        if email in already_shared:
            print(f"already shared: {email}")
            continue
        sh.share(email, perm_type="user", role="writer")
        print(f"shared (writer): {email}")


def _service_account_emails_for_registered_jobs() -> list[str]:
    """Not auto-discoverable from the registry (JobSpec doesn't record a
    service account -- deliberately, since it's a deploy-time fact, not a
    monitoring-config fact). Kept here as the one explicit list to update
    when a new job is registered."""
    return [
        "clio-reporting-sync@jh-law-rc-clio-personal.iam.gserviceaccount.com",  # clio-reporting-sync-job
        "1731274938-compute@developer.gserviceaccount.com",  # rc-webhook-listener (deliver-clio-recordings)
    ]


if __name__ == "__main__":
    main()
