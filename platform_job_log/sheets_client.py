"""Low-level Google Sheets access via ADC -- works unmodified on Cloud Run
(metadata-server credentials for the job's own runtime service account) and
locally (GOOGLE_APPLICATION_CREDENTIALS pointing at a key file), matching
this platform's established ADC-first pattern (jh_clio_lib.clio_auth's
Firestore access is the model here).

The calling identity (a Cloud Run job's runtime SA, or a human/local SA)
must be shared as an Editor on the actual Google Sheet -- Sheets access is
governed by Drive-style sharing, not IAM roles, so `roles/editor` on the GCP
project grants nothing here on its own.
"""
from __future__ import annotations

import functools

import google.auth
import gspread

from platform_job_log import config

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


@functools.lru_cache(maxsize=1)
def get_client() -> gspread.Client:
    credentials, _ = google.auth.default(scopes=_SCOPES)
    return gspread.authorize(credentials)


def open_spreadsheet(spreadsheet_id: str | None = None) -> gspread.Spreadsheet:
    sheet_id = spreadsheet_id or config.SPREADSHEET_ID
    if not sheet_id:
        raise RuntimeError(
            "No spreadsheet id configured -- set JOB_LOG_SPREADSHEET_ID or "
            "fill in platform_job_log/config.py's SPREADSHEET_ID."
        )
    return get_client().open_by_key(sheet_id)


def worksheet(tab_name: str, spreadsheet_id: str | None = None) -> gspread.Worksheet:
    return open_spreadsheet(spreadsheet_id).worksheet(tab_name)
