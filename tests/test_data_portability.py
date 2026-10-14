from datetime import datetime, timezone

import pytest

from calendar_feed.service import escape_ical, render_icalendar
from task_import.service import ImportValidationError, parse_import_file


def test_csv_import_keeps_missing_deadline_null_and_maps_export_columns():
    data = (
        "ID,Task,Status,Priority,Deadline,Recurring,Tags,Description,Pinned\n"
        "1,Write report,Pending,3,,,work,Quarterly report,true\n"
    ).encode()

    result = parse_import_file(data, "tasks.csv", "Asia/Bangkok", "no_deadline")

    assert len(result) == 1
    assert result[0].task == "Write report"
    assert result[0].deadline is None
    assert result[0].priority == 3
    assert result[0].tags == "work"
    assert result[0].is_pinned is True


def test_import_defaults_missing_deadline_to_one_day():
    data = b'[{"task":"Review design","priority":1}]'
    before = datetime.now(timezone.utc)

    result = parse_import_file(data, "tasks.json", "UTC", "default_1_day")
    deadline = datetime.fromisoformat(result[0].deadline)

    delta = deadline - before
    assert 23 * 3600 < delta.total_seconds() < 25 * 3600


def test_json_import_accepts_iso8601_deadline():
    data = b'[{"task":"Prepare release","deadline":"2030-04-05T18:30:00+02:00"}]'

    result = parse_import_file(data, "tasks.json", "UTC", "no_deadline")

    assert result[0].deadline == "2030-04-05T16:30:00+00:00"


def test_import_rejects_entire_file_when_any_row_is_invalid():
    data = b'[{"task":"Valid"},{"task":"","priority":9}]'

    with pytest.raises(ImportValidationError, match="Row 2"):
        parse_import_file(data, "tasks.json", "UTC", "no_deadline")


def test_recurring_import_cannot_have_no_deadline():
    data = b'[{"task":"Recurring task","recurring":"weekly"}]'

    with pytest.raises(ImportValidationError, match="must have a deadline"):
        parse_import_file(data, "tasks.json", "UTC", "no_deadline")


def test_ical_escapes_text_and_uses_crlf():
    assert escape_ical("a,b;c\\d\nnext") == "a\\,b\\;c\\\\d\\nnext"
    rendered = render_icalendar([], now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert rendered.startswith("BEGIN:VCALENDAR\r\n")
    assert rendered.endswith("END:VCALENDAR\r\n")
    assert "\n" not in rendered.replace("\r\n", "")


def test_ical_folds_utf8_lines_to_rfc_octet_limit():
    rendered = render_icalendar([{
        "task_id": 1,
        "task": "งาน" * 80,
        "description": None,
        "deadline": "2026-06-01T12:00:00+00:00",
        "updated_at": None,
    }], now=datetime(2026, 1, 1, tzinfo=timezone.utc))

    for line in rendered.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75
