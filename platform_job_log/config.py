"""Shared config for platform_job_log.

The spreadsheet ID is not a secret (knowing it grants nothing without also
being an authorized editor on the sheet), so it's a plain constant here --
filled in once by scripts/create_sheet.py, overridable via env var for local
testing against a scratch sheet.
"""
from __future__ import annotations

import os

# Filled in by scripts/create_sheet.py once the sheet is created.
SPREADSHEET_ID = os.environ.get("JOB_LOG_SPREADSHEET_ID", "1IwS5Fypr2gTlHHTOJy1pzNx161yibIgCA_MX4-mkt_o")

RUN_LOG_TAB = "Run Log"
CURRENT_STATUS_TAB = "Current Status"

RUN_LOG_HEADERS = [
    "job_name", "job_type", "expected_at", "actual_start",
    "completion_time", "status", "notes",
]
