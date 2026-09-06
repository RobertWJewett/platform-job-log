from __future__ import annotations

from platform_job_log.logger import _appended_row_number


def test_appended_row_number_parses_real_sheets_api_response():
    # Real shape from gspread's append_row() -- confirmed live 2026-09-06 after
    # a concurrency bug (len(get_all_values()) read right after an append raced
    # with a sibling job's own append, mis-attributing rows between them).
    response = {
        "spreadsheetId": "abc123",
        "tableRange": "'Run Log'!A1:G60",
        "updates": {
            "spreadsheetId": "abc123",
            "updatedRange": "'Run Log'!A61:G61",
            "updatedRows": 1,
            "updatedColumns": 7,
            "updatedCells": 7,
        },
    }
    assert _appended_row_number(response) == 61


def test_appended_row_number_handles_multi_digit_rows():
    response = {"updates": {"updatedRange": "'Run Log'!A123:G123"}}
    assert _appended_row_number(response) == 123
