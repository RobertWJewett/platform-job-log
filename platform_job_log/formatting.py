"""One-time (re-run-safe) visual setup for the "Current Status" tab: color
the flag column so a glance tells you if anything needs attention, and put
the tab first so it's what opens by default -- the Run Log tab stays as a
background detail/audit view most days.

Only needs the ordinary `spreadsheets` scope already used everywhere else in
this package (conditional formatting, cell formatting, and tab reordering
are all plain Sheets API operations, not Drive operations) -- unlike
scripts/setup_sheet.py's sharing step, this needs no special Drive scope and
can run as the job's own runtime service account.
"""
from __future__ import annotations

from platform_job_log import config
from platform_job_log.sheets_client import open_spreadsheet

_FLAG_COLORS = {
    "FAILED": {"red": 0.96, "green": 0.78, "blue": 0.78},
    "OVERDUE": {"red": 1.0, "green": 0.90, "blue": 0.70},
    "NO DATA": {"red": 0.90, "green": 0.90, "blue": 0.90},
    "OK": {"red": 0.83, "green": 0.94, "blue": 0.83},
}

# Row 1 = headline, row 2 = column headers, data starts at row 3. Ranged
# generously past any realistic job count so newly-registered jobs are
# covered without touching this file again.
_DATA_START_ROW = 3
_DATA_END_ROW = 300
_FLAG_COL_LETTER = "E"  # job_name, job_type, reference_time, last_status, flag, ...


def _clear_existing_conditional_formats(sh, sheet_id: int) -> int:
    metadata = sh.fetch_sheet_metadata()
    rule_count = 0
    for s in metadata.get("sheets", []):
        if s["properties"]["sheetId"] == sheet_id:
            rule_count = len(s.get("conditionalFormats", []))
            break
    # Deleting index 0 repeatedly removes every rule -- each delete shifts
    # the remaining rules down by one.
    return rule_count


def apply_dashboard_formatting(spreadsheet_id: str | None = None) -> None:
    sh = open_spreadsheet(spreadsheet_id)
    status_ws = sh.worksheet(config.CURRENT_STATUS_TAB)
    run_log_ws = sh.worksheet(config.RUN_LOG_TAB)
    sheet_id = status_ws.id

    requests = []
    existing_rule_count = _clear_existing_conditional_formats(sh, sheet_id)
    requests += [{"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 0}}
                 for _ in range(existing_rule_count)]

    data_range = {
        "sheetId": sheet_id,
        "startRowIndex": _DATA_START_ROW - 1,
        "endRowIndex": _DATA_END_ROW,
        "startColumnIndex": 0,
        "endColumnIndex": 7,
    }
    for flag, color in _FLAG_COLORS.items():
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [data_range],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": f'=${_FLAG_COL_LETTER}{_DATA_START_ROW}="{flag}"'}],
                        },
                        "format": {"backgroundColor": color},
                    },
                },
                "index": 0,
            }
        })

    sh.batch_update({"requests": requests})
    sh.reorder_worksheets([status_ws, run_log_ws])
    print(
        f"Dashboard formatting applied to '{status_ws.title}': "
        f"{existing_rule_count} old conditional format rule(s) replaced with {len(_FLAG_COLORS)}, "
        f"tab order set to ['{status_ws.title}', '{run_log_ws.title}', ...]."
    )


if __name__ == "__main__":
    apply_dashboard_formatting()
