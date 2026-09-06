#!/usr/bin/env python3
"""One-time setup: creates the "JH Law - Job Run Log" Google Sheet, its two
tabs with headers, and shares it with the given email. Run once; prints the
spreadsheet ID to paste into platform_job_log/config.py's SPREADSHEET_ID.

Usage:
    python3 scripts/create_sheet.py --share-with robert@jewettlaw.net
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from platform_job_log import config  # noqa: E402
from platform_job_log.sheets_client import get_client  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--share-with", required=True, help="Email to share the sheet with as editor")
    parser.add_argument("--title", default="JH Law - Job Run Log")
    args = parser.parse_args()

    gc = get_client()
    sh = gc.create(args.title)
    sh.share(args.share_with, perm_type="user", role="writer")

    run_log = sh.sheet1
    run_log.update_title(config.RUN_LOG_TAB)
    run_log.update("A1", [config.RUN_LOG_HEADERS])
    run_log.freeze(rows=1)

    status = sh.add_worksheet(title=config.CURRENT_STATUS_TAB, rows=100, cols=8)
    status.update("A1", [["job_name", "job_type", "reference_time", "last_status", "flag", "detail", "checked_at"]])
    status.freeze(rows=1)

    print(f"Created spreadsheet: {sh.url}")
    print(f"Spreadsheet ID: {sh.id}")
    print("Paste this into platform_job_log/config.py's SPREADSHEET_ID default, "
          "or set JOB_LOG_SPREADSHEET_ID in every consuming job's environment.")


if __name__ == "__main__":
    main()
