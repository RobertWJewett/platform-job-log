from __future__ import annotations

from platform_job_log import logger
from platform_job_log.logger import _appended_row_number, log_run_complete
from platform_job_log.registry import JobSpec

_HEADER = ["job_name", "job_type", "expected_at", "actual_start", "completion_time", "status", "notes"]


class FakeWorksheet:
    """Minimal stand-in for gspread.Worksheet covering only what logger.py calls."""

    def __init__(self, rows):
        self.data = [list(r) for r in rows]

    def get_all_values(self):
        return [list(r) for r in self.data]

    def row_values(self, n):
        return list(self.data[n - 1])

    def update_cell(self, row, col, value):
        self.data[row - 1][col - 1] = value

    def append_row(self, row):
        self.data.append(list(row))
        n = len(self.data)
        return {"updates": {"updatedRange": f"'Run Log'!A{n}:G{n}"}}


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


def test_frequent_success_upserts_existing_row_instead_of_appending(monkeypatch):
    ws = FakeWorksheet([
        _HEADER,
        ["frequent-thing", "frequent", "", "2026-09-06T13:00:00Z", "2026-09-06T13:00:00Z", "success", "old note"],
    ])
    monkeypatch.setitem(logger.JOBS, "frequent-thing", JobSpec(name="frequent-thing", job_type="frequent"))
    monkeypatch.setattr(logger, "worksheet", lambda tab: ws)

    log_run_complete("frequent-thing", "success", "new note")

    assert len(ws.data) == 2  # no new row appended
    assert ws.data[1][4] == ws.data[1][3]  # completion_time == actual_start (both refreshed to "now")
    assert ws.data[1][5] == "success"
    assert ws.data[1][6] == "new note"


def test_frequent_success_appends_when_no_existing_row(monkeypatch):
    ws = FakeWorksheet([_HEADER])
    monkeypatch.setitem(logger.JOBS, "frequent-thing", JobSpec(name="frequent-thing", job_type="frequent"))
    monkeypatch.setattr(logger, "worksheet", lambda tab: ws)

    log_run_complete("frequent-thing", "success", "first run")

    assert len(ws.data) == 2
    assert ws.data[1][0] == "frequent-thing"
    assert ws.data[1][5] == "success"


def test_frequent_failure_always_appends_a_new_row(monkeypatch):
    ws = FakeWorksheet([
        _HEADER,
        ["frequent-thing", "frequent", "", "2026-09-06T13:00:00Z", "2026-09-06T13:00:00Z", "success", ""],
    ])
    monkeypatch.setitem(logger.JOBS, "frequent-thing", JobSpec(name="frequent-thing", job_type="frequent"))
    monkeypatch.setattr(logger, "worksheet", lambda tab: ws)

    log_run_complete("frequent-thing", "failed", "boom")

    assert len(ws.data) == 3  # existing success row untouched, new failure row appended
    assert ws.data[1][5] == "success"
    assert ws.data[2][5] == "failed"
    assert ws.data[2][6] == "boom"


def test_scheduled_no_row_ref_still_appends_not_upserts(monkeypatch):
    ws = FakeWorksheet([_HEADER])
    monkeypatch.setitem(logger.JOBS, "nightly-thing", JobSpec(name="nightly-thing", job_type="scheduled", cron="0 3 * * *"))
    monkeypatch.setattr(logger, "worksheet", lambda tab: ws)

    log_run_complete("nightly-thing", "success", "no pre-seeded row found")

    assert len(ws.data) == 2
    assert ws.data[1][5] == "success"
