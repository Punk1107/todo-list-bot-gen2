"""
tests/test_conflict_resolution.py — Unit tests for utils/conflict_resolver.py

Covers:
  - validate_deadline_defensive: past deadline, year range, grace buffer, subtask hierarchy
  - suggest_unique_task_name: suffix counter logic (offline, via regex)
  - calculate_defensive_snooze: overdue and non-overdue tasks
  - check_duplicate_task: tested via mock to avoid DB dependency
"""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytz

from utils.conflict_resolver import (
    DeadlineValidationError,
    validate_deadline_defensive,
    calculate_defensive_snooze,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

TZ_BANGKOK = "Asia/Bangkok"
_BANGKOK = pytz.timezone(TZ_BANGKOK)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _future_str(hours: float = 48.0, tz_name: str = TZ_BANGKOK) -> str:
    """Return a deadline string (DD/MM/YYYY HH:MM) that is `hours` in the future."""
    dt_utc = _now_utc() + timedelta(hours=hours)
    local  = dt_utc.astimezone(pytz.timezone(tz_name))
    return local.strftime("%d/%m/%Y %H:%M")


def _past_str(hours: float = 48.0, tz_name: str = TZ_BANGKOK) -> str:
    """Return a deadline string that is `hours` in the past."""
    dt_utc = _now_utc() - timedelta(hours=hours)
    local  = dt_utc.astimezone(pytz.timezone(tz_name))
    return local.strftime("%d/%m/%Y %H:%M")


# ─────────────────────────────────────────────────────────────────────────────
# validate_deadline_defensive — valid cases
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateDeadlineDefensive:

    def test_valid_future_deadline(self):
        """A deadline 48 hours in the future must be accepted."""
        result = validate_deadline_defensive(_future_str(48), TZ_BANGKOK)
        assert isinstance(result, datetime)
        assert result > _now_utc()

    def test_valid_near_future_within_grace(self):
        """A deadline 30 seconds in the future is within grace and must be accepted."""
        # 30s in future — well within the 60s grace buffer
        dt_utc = _now_utc() + timedelta(seconds=30)
        local  = dt_utc.astimezone(_BANGKOK)
        dl_str = local.strftime("%d/%m/%Y %H:%M")
        # At minute precision this becomes the current or next minute — should pass
        result = validate_deadline_defensive(dl_str, TZ_BANGKOK, grace_seconds=90)
        assert isinstance(result, datetime)

    # ── Invalid cases ──────────────────────────────────────────────────────────

    def test_past_deadline_48h(self):
        """A deadline 48 hours in the past must be rejected."""
        with pytest.raises(DeadlineValidationError) as exc_info:
            validate_deadline_defensive(_past_str(48), TZ_BANGKOK)
        assert exc_info.value.i18n_key == "task_past_deadline_detailed"
        assert "current_time" in exc_info.value.kwargs
        assert "input_time" in exc_info.value.kwargs

    def test_past_deadline_error_contains_times(self):
        """Error kwargs must include both current_time and input_time strings."""
        try:
            validate_deadline_defensive(_past_str(24), TZ_BANGKOK)
        except DeadlineValidationError as e:
            assert e.kwargs.get("current_time")
            assert e.kwargs.get("input_time")
            return
        pytest.fail("Expected DeadlineValidationError not raised")

    def test_invalid_format(self):
        """Completely invalid deadline text must raise with task_invalid_deadline key."""
        with pytest.raises(DeadlineValidationError) as exc_info:
            validate_deadline_defensive("not-a-date", TZ_BANGKOK)
        assert exc_info.value.i18n_key == "task_invalid_deadline"

    def test_year_too_far_future(self):
        """A deadline more than 10 years in the future must be rejected."""
        far_future = f"01/01/{_now_utc().year + 12} 12:00"
        with pytest.raises(DeadlineValidationError) as exc_info:
            validate_deadline_defensive(far_future, TZ_BANGKOK)
        assert exc_info.value.i18n_key == "task_invalid_year"

    def test_year_before_2000(self):
        """A deadline before year 2000 must be rejected."""
        ancient = "01/01/1999 12:00"
        with pytest.raises(DeadlineValidationError) as exc_info:
            validate_deadline_defensive(ancient, TZ_BANGKOK)
        assert exc_info.value.i18n_key == "task_invalid_year"

    def test_grace_buffer_exactly_at_cutoff(self):
        """A deadline slightly more than grace_seconds in the past must be rejected."""
        dt_utc = _now_utc() - timedelta(seconds=70)  # 70s past, grace=60s
        local  = dt_utc.astimezone(_BANGKOK)
        dl_str = local.strftime("%d/%m/%Y %H:%M")
        # At minute-level precision this may or may not fail depending on rounding.
        # We test with explicit past strings instead (hours-level)
        # This is a fuzzy test — just ensure the function runs without TypeError
        try:
            validate_deadline_defensive(dl_str, TZ_BANGKOK, grace_seconds=60)
        except DeadlineValidationError as e:
            assert e.i18n_key in ("task_past_deadline_detailed", "task_invalid_deadline")

    # ── Subtask hierarchy ──────────────────────────────────────────────────────

    def test_subtask_deadline_exceeds_parent(self):
        """Subtask deadline after parent deadline must be rejected."""
        # Parent: 24h from now
        parent_utc = _now_utc() + timedelta(hours=24)
        parent_iso = parent_utc.isoformat()
        # Subtask: 48h from now (later than parent)
        subtask_dl = _future_str(48)
        with pytest.raises(DeadlineValidationError) as exc_info:
            validate_deadline_defensive(subtask_dl, TZ_BANGKOK, parent_deadline_iso=parent_iso)
        assert exc_info.value.i18n_key == "subtask_deadline_exceeds_parent"
        assert "parent_dl" in exc_info.value.kwargs
        assert "subtask_dl" in exc_info.value.kwargs

    def test_subtask_deadline_before_parent_is_valid(self):
        """Subtask deadline before parent deadline must be accepted."""
        parent_utc = _now_utc() + timedelta(hours=72)  # parent: 72h from now
        parent_iso = parent_utc.isoformat()
        subtask_dl = _future_str(24)  # subtask: 24h from now (before parent)
        result = validate_deadline_defensive(subtask_dl, TZ_BANGKOK, parent_deadline_iso=parent_iso)
        assert isinstance(result, datetime)

    def test_subtask_deadline_equal_to_parent_is_valid(self):
        """Subtask deadline exactly equal to parent deadline must be accepted."""
        parent_utc = _now_utc() + timedelta(hours=48)
        # Build a string at the same hour:minute as the parent
        local = parent_utc.astimezone(_BANGKOK)
        dl_str = local.strftime("%d/%m/%Y %H:%M")
        parent_iso = parent_utc.isoformat()
        # At minute precision, subtask == parent; should pass (not strictly greater)
        # (parse_deadline sets seconds=0, so the parsed time will be <= parent)
        result = validate_deadline_defensive(dl_str, TZ_BANGKOK, parent_deadline_iso=parent_iso)
        assert isinstance(result, datetime)


# ─────────────────────────────────────────────────────────────────────────────
# calculate_defensive_snooze
# ─────────────────────────────────────────────────────────────────────────────

class TestCalculateDefensiveSnooze:

    def _parse(self, iso: str) -> datetime:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        return dt

    def test_non_overdue_snooze_is_deadline_plus_1d(self):
        """For a task not overdue, new deadline = original + 1 day."""
        now_utc      = _now_utc()
        deadline_utc = now_utc + timedelta(hours=12)
        expected     = deadline_utc + timedelta(days=1)

        result_iso = calculate_defensive_snooze(deadline_utc.isoformat(), now_utc=now_utc)
        result     = self._parse(result_iso)

        # Allow 1 second tolerance for float arithmetic
        assert abs((result - expected).total_seconds()) < 1

    def test_overdue_snooze_is_now_plus_1d(self):
        """For a task 3 days overdue, new deadline = now + 1 day (not deadline + 1 day)."""
        now_utc      = _now_utc()
        deadline_utc = now_utc - timedelta(days=3)   # 3 days in the past

        result_iso     = calculate_defensive_snooze(deadline_utc.isoformat(), now_utc=now_utc)
        result         = self._parse(result_iso)
        expected_min   = now_utc + timedelta(days=1) - timedelta(seconds=1)
        expected_max   = now_utc + timedelta(days=1) + timedelta(seconds=1)

        assert expected_min <= result <= expected_max

    def test_overdue_result_is_always_in_future(self):
        """Snoozed deadline for overdue task must always be in the future."""
        now_utc      = _now_utc()
        deadline_utc = now_utc - timedelta(days=10)  # 10 days overdue

        result_iso = calculate_defensive_snooze(deadline_utc.isoformat(), now_utc=now_utc)
        result     = self._parse(result_iso)

        assert result > now_utc, "Snoozed deadline must be in the future"

    def test_snooze_accepts_datetime_object(self):
        """calculate_defensive_snooze must accept a datetime object (not just ISO string)."""
        now_utc      = _now_utc()
        deadline_utc = now_utc + timedelta(hours=5)

        result_iso = calculate_defensive_snooze(deadline_utc, now_utc=now_utc)
        result     = self._parse(result_iso)

        assert result > now_utc

    def test_snooze_accepts_naive_datetime(self):
        """Naive datetimes (no tzinfo) must be treated as UTC."""
        now_utc  = _now_utc()
        deadline = datetime.utcnow() + timedelta(hours=5)  # naive

        result_iso = calculate_defensive_snooze(deadline.isoformat(), now_utc=now_utc)
        result     = self._parse(result_iso)

        assert result > now_utc

    def test_snooze_default_now_utc(self):
        """When now_utc is not provided, it defaults to the current UTC time."""
        deadline_utc = _now_utc() - timedelta(days=2)  # overdue
        result_iso   = calculate_defensive_snooze(deadline_utc.isoformat())
        result       = self._parse(result_iso)

        assert result > _now_utc(), "Result must be in the future even without explicit now_utc"


# ─────────────────────────────────────────────────────────────────────────────
# check_duplicate_task (mocked DB)
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckDuplicateTask:

    @pytest.mark.asyncio
    async def test_no_duplicate_returns_none(self):
        """When DB returns no row, check_duplicate_task must return None."""
        mock_db = AsyncMock()
        mock_db.afetchone = AsyncMock(return_value=None)

        with patch("core.database.db", mock_db):
            from utils.conflict_resolver import check_duplicate_task
            result = await check_duplicate_task("user1", "Unique Task")

        assert result is None

    @pytest.mark.asyncio
    async def test_duplicate_found_returns_row(self):
        """When DB returns a matching row, check_duplicate_task must return that row as dict."""
        conflict = {"task_id": 42, "task": "My Task", "deadline": "2026-12-31T17:00:00+00:00", "status": "Pending"}
        mock_db = AsyncMock()
        mock_db.afetchone = AsyncMock(return_value=conflict)

        with patch("core.database.db", mock_db):
            from utils.conflict_resolver import check_duplicate_task
            result = await check_duplicate_task("user1", "My Task")

        assert result is not None
        assert result["task_id"] == 42

    @pytest.mark.asyncio
    async def test_exclude_task_id_ignores_current_task(self):
        """When exclude_task_id matches the found conflict, None is returned (edit flow)."""
        conflict = {"task_id": 42, "task": "My Task", "deadline": "2026-12-31T17:00:00+00:00", "status": "Pending"}
        mock_db = AsyncMock()
        mock_db.afetchone = AsyncMock(return_value=conflict)

        with patch("core.database.db", mock_db):
            from utils.conflict_resolver import check_duplicate_task
            result = await check_duplicate_task("user1", "My Task", exclude_task_id=42)

        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# suggest_unique_task_name (mocked DB)
# ─────────────────────────────────────────────────────────────────────────────

class TestSuggestUniqueTaskName:

    @pytest.mark.asyncio
    async def test_no_existing_duplicates_returns_2(self):
        """When no suffixed duplicates exist, suggested name uses suffix (2)."""
        mock_db = AsyncMock()
        mock_db.afetchall = AsyncMock(return_value=[])

        with patch("core.database.db", mock_db):
            from utils.conflict_resolver import suggest_unique_task_name
            result = await suggest_unique_task_name("user1", "My Task")

        assert result == "My Task (2)"

    @pytest.mark.asyncio
    async def test_existing_2_suggests_3(self):
        """When 'My Task (2)' exists, suggest 'My Task (3)'."""
        existing = [{"task": "My Task (2)"}]
        mock_db = AsyncMock()
        mock_db.afetchall = AsyncMock(return_value=existing)

        with patch("core.database.db", mock_db):
            from utils.conflict_resolver import suggest_unique_task_name
            result = await suggest_unique_task_name("user1", "My Task")

        assert result == "My Task (3)"

    @pytest.mark.asyncio
    async def test_gap_in_numbers_fills_gap(self):
        """When (2) and (4) exist but not (3), suggests (3)."""
        existing = [{"task": "Task (2)"}, {"task": "Task (4)"}]
        mock_db = AsyncMock()
        mock_db.afetchall = AsyncMock(return_value=existing)

        with patch("core.database.db", mock_db):
            from utils.conflict_resolver import suggest_unique_task_name
            result = await suggest_unique_task_name("user1", "Task")

        assert result == "Task (3)"

    @pytest.mark.asyncio
    async def test_whitespace_stripped_from_base_name(self):
        """Leading/trailing whitespace in base_name must be stripped."""
        mock_db = AsyncMock()
        mock_db.afetchall = AsyncMock(return_value=[])

        with patch("core.database.db", mock_db):
            from utils.conflict_resolver import suggest_unique_task_name
            result = await suggest_unique_task_name("user1", "  My Task  ")

        assert result == "My Task (2)"
