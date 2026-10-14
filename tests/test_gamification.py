from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from gamification import service


class FakeConnection:
    def __init__(self, *, timezone_name: str, streak_days: int, last_day: date | None,
                 remaining_tasks: bool = False) -> None:
        self.user = {
            "timezone": timezone_name,
            "streak_days": streak_days,
            "streak_last_completion": last_day,
        }
        self.remaining_tasks = remaining_tasks
        self.executed: list[tuple[str, tuple]] = []
        self.achievements: set[str] = set()

    async def execute(self, query: str, *params):
        self.executed.append((query, params))
        if "UPDATE users SET streak_days" in query:
            self.user["streak_days"] = params[0]
            self.user["streak_last_completion"] = params[1]

    async def fetchrow(self, query: str, *params):
        if "FROM users WHERE user_id=$1 FOR UPDATE" in query:
            return self.user
        if "INSERT INTO user_achievements" in query:
            badge = params[1]
            if badge in self.achievements:
                return None
            self.achievements.add(badge)
            return {"achievement_id": len(self.achievements)}
        raise AssertionError(f"Unexpected fetchrow: {query}")

    async def fetchval(self, query: str, *params):
        assert "owner_id=$1" in query
        return self.remaining_tasks


class FakeReminderConnection:
    async def fetchrow(self, query: str, *params):
        self.query = query
        self.params = params
        return {"user_id": params[0]}


class FakeAcquireContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False


def _completion_task(**overrides):
    task = {
        "task_id": 12,
        "task": "Prepare presentation",
        "priority": 7,
        "deadline": "2026-06-06T08:30:00+07:00",
        "project_id": None,
        "guild_id": None,
    }
    task.update(overrides)
    return task


def test_next_streak_uses_local_calendar_days():
    today = date(2026, 6, 5)
    assert service._next_streak(5, today, today) == 5
    assert service._next_streak(5, date(2026, 6, 4), today) == 6
    assert service._next_streak(5, date(2026, 6, 3), today) == 1
    assert service._next_streak(5, None, today) == 1


@pytest.mark.asyncio
async def test_completion_snapshots_timezone_streak_and_awards_eligible_badges():
    conn = FakeConnection(
        timezone_name="Asia/Bangkok",
        streak_days=4,
        last_day=date(2026, 6, 4),
    )
    completed_at = datetime(2026, 6, 5, 0, 30, tzinfo=timezone.utc)

    awarded = await service._record_completion(
        conn, _completion_task(), "user-1", completed_at
    )

    assert conn.user["streak_days"] == 5
    assert conn.user["streak_last_completion"] == date(2026, 6, 5)
    # Completion is 07:30 in Bangkok, before 09:00; deadline is 25 hours later.
    assert set(awarded) == {"early_bird", "speed_demon", "p7_slayer", "inbox_zero"}
    update = next(
        params for query, params in conn.executed
        if "UPDATE users SET streak_days" in query
    )
    assert update == (5, date(2026, 6, 5), "user-1")
    event_insert = next(
        params for query, params in conn.executed
        if "INSERT INTO task_completion_events" in query
    )
    assert event_insert[1:4] == ("user-1", None, None)
    assert event_insert[5] == 7
    assert event_insert[7] == completed_at


@pytest.mark.asyncio
async def test_inbox_zero_is_not_awarded_with_open_due_or_overdue_work():
    conn = FakeConnection(
        timezone_name="UTC",
        streak_days=1,
        last_day=date(2026, 6, 4),
        remaining_tasks=True,
    )

    awarded = await service._record_completion(
        conn,
        _completion_task(priority=0, deadline="2026-06-08T12:00:00+00:00"),
        "user-1",
        datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
    )

    assert "inbox_zero" not in awarded


def test_productivity_score_has_documented_weighting():
    assert service._productivity_score(6, 3, 6, 5, 1) == 80.0
    assert service._productivity_score(6, 3, 3, 5, 1) == 100.0
    assert service._productivity_score(0, 0, 0, 0, 0) == 0.0


def test_schema_migration_adds_completion_and_reminder_state():
    from core.database import MIGRATIONS, SCHEMA_VERSION

    migration = dict(MIGRATIONS)[19]
    assert SCHEMA_VERSION == 22
    assert "streak_last_completion DATE" in migration
    assert "streak_reminder_date DATE" in migration
    assert "CREATE TABLE IF NOT EXISTS task_completion_events" in migration
    assert "idx_completion_guild_time" in migration


@pytest.mark.asyncio
async def test_leaderboard_is_scoped_to_guild_and_ranks_by_scoped_score():
    rows = [
        {
            "user_id": "user-a",
            "completed": 4,
            "deadline_count": 4,
            "on_time": 4,
            "active_days": 2,
            "p7_completed": 0,
        },
        {
            "user_id": "user-b",
            "completed": 6,
            "deadline_count": 6,
            "on_time": 3,
            "active_days": 5,
            "p7_completed": 1,
        },
    ]
    with patch.object(service.db, "afetchall", new=AsyncMock(return_value=rows)) as fetch:
        result = await service.get_guild_leaderboard("guild-42", "week")

    assert [row["user_id"] for row in result] == ["user-b", "user-a"]
    sql, params = fetch.await_args.args
    assert "WHERE guild_id=$1 AND completed_at >= $2" in sql
    assert params[0] == "guild-42"


@pytest.mark.asyncio
async def test_streak_reminder_claim_is_persistently_deduplicated():
    connection = FakeReminderConnection()
    acquire = FakeAcquireContext(connection)
    with patch.object(
        service.db,
        "acquire",
        return_value=acquire,
    ), patch.object(service.db.query_cache, "invalidate_tables") as invalidate:
        claimed = await service.claim_streak_reminder("user-1", date(2026, 6, 5))

    assert claimed
    assert "streak_reminder_date IS DISTINCT FROM $2" in connection.query
    assert connection.params == ("user-1", date(2026, 6, 5))
    invalidate.assert_called_once_with(["users"])
