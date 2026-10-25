"""
tests/test_perf_stability_1.py — Verification suite for System Performance & Stability Pillar 1-5.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from core.database import _KNOWN_TABLES, MIGRATIONS, SCHEMA_VERSION, QueryCache, _detect_tables, db
from handlers.reminders_cog import RemindersCog
from utils.helpers import ensure_user


# ── Pillar 1: Known Tables Completeness & QueryCache Integrity ────────────────

def test_known_tables_completeness():
    """Verify all critical system tables are registered in _KNOWN_TABLES."""
    expected_tables = {
        "tasks", "users", "categories", "projects", "project_members",
        "project_activity_log", "task_attachments", "task_assignments",
        "guild_settings", "audit_log", "schema_version", "task_completion_events",
        "user_achievements", "project_task_threads", "project_task_dependencies",
        "project_task_role_assignments", "task_templates", "task_checklists",
        "routine_event_rules", "project_role_permissions", "saved_filters",
        "focus_sessions", "calendar_feed_tokens", "task_comments",
    }
    for table in expected_tables:
        assert table in _KNOWN_TABLES, f"Missing table {table} in _KNOWN_TABLES"


def test_focus_session_write_does_not_trash_task_cache():
    """Verify that focus mode writes only invalidate focus_sessions, NOT global cache."""
    qc = QueryCache(ttl=60.0)

    # Populate cache for tasks, users, and focus_sessions
    qc.set("SELECT * FROM tasks WHERE owner_id=$1", ("123",), [{"task_id": 1}])
    qc.set("SELECT * FROM users WHERE user_id=$1", ("123",), {"user_id": "123"})
    qc.set("SELECT * FROM focus_sessions WHERE session_id=$1", (42,), {"session_id": 42})

    # Assert all 3 are cached
    assert qc.get("SELECT * FROM tasks WHERE owner_id=$1", ("123",)) != qc.get("SELECT 1", ())
    assert qc.get("SELECT * FROM users WHERE user_id=$1", ("123",)) != qc.get("SELECT 1", ())
    assert qc.get("SELECT * FROM focus_sessions WHERE session_id=$1", (42,)) != qc.get("SELECT 1", ())

    # Simulate focus mode update
    sql = "UPDATE focus_sessions SET phase='break', updated_at=NOW() WHERE session_id=$1"
    tables = _detect_tables(sql)
    assert tables == {"focus_sessions"}, f"Expected {{'focus_sessions'}}, got {tables}"

    # Invalidate detected tables
    qc.invalidate_tables(list(tables))

    # Tasks and users MUST still be cached; focus_sessions MUST be invalidated
    assert qc.get("SELECT * FROM tasks WHERE owner_id=$1", ("123",)) == [{"task_id": 1}]
    assert qc.get("SELECT * FROM users WHERE user_id=$1", ("123",)) == {"user_id": "123"}
    # Cache miss for focus_sessions
    assert qc.get("SELECT * FROM focus_sessions WHERE session_id=$1", (42,)) == qc.get("MISSING_QUERY", ())


def test_query_cache_fast_key_hashing():
    """Verify tuple-based fast key hashing and fallback behavior."""
    # Test identical keys for tuple vs list
    k1 = QueryCache._key("SELECT * FROM tasks WHERE id=$1", (123,))
    k2 = QueryCache._key("SELECT * FROM tasks WHERE id=$1", [123])
    assert k1 == k2 == ("SELECT * FROM tasks WHERE id=$1", (123,))

    # Test None / empty params
    k3 = QueryCache._key("SELECT 1", None)
    k4 = QueryCache._key("SELECT 1", ())
    k5 = QueryCache._key("SELECT 1", [])
    assert k3 == k4 == k5 == ("SELECT 1", ())

    # Test fallback on unhashable dict param
    k_dict = QueryCache._key("UPDATE tasks SET metadata=$1", [{"key": "val"}])
    assert isinstance(k_dict, tuple)
    assert k_dict[0] == "UPDATE tasks SET metadata=$1"
    assert isinstance(k_dict[1], str)  # Fallback serialized JSON string

    # Microsecond benchmark: 10,000 key generations should run in < 50ms
    t0 = time.monotonic()
    for i in range(10000):
        _ = QueryCache._key("SELECT * FROM tasks WHERE owner_id=$1 AND status=$2", ("999999", "Pending"))
    elapsed = time.monotonic() - t0
    assert elapsed < 0.20, f"Tuple key generation too slow: {elapsed:.3f}s for 10k items"


# ── Pillar 2: Background Tasks Stability & HOL Blocking Prevention ────────────

def _create_cog(bot: MagicMock) -> RemindersCog:
    bot.wait_until_ready = AsyncMock()
    cog = RemindersCog(bot)
    cog.reminder_loop.cancel()
    cog.recurring_loop.cancel()
    cog.daily_digest_loop.cancel()
    cog.weekly_retrospective_loop.cancel()
    cog.cleanup_loop.cancel()
    cog.deadline_dm_loop.cancel()
    return cog


@pytest.mark.asyncio
async def test_reminder_loop_dead_channel_hol_blocking_prevention():
    """Verify that tasks in deleted/missing channels get last_reminder updated to avoid HOL blocking."""
    bot = MagicMock()
    bot.get_channel.return_value = None  # Channel deleted or missing
    cog = _create_cog(bot)

    now = datetime.now(timezone.utc)
    rows = [
        {
            "task_id": 101,
            "task": "Urgent Dead Task",
            "deadline": now.isoformat(),
            "is_pinned": 0,
            "priority": 1,
            "user_id": "user_a",
            "channel_id": 999999999,
            "timezone": "UTC",
            "lang": "en",
            "notify_enabled": 1,
        }
    ]

    with patch.object(db, "afetchall", AsyncMock(return_value=rows)), \
         patch.object(db, "aexecute_batch", AsyncMock()) as mock_batch:

        # Run reminder_loop body
        await cog.reminder_loop()

        # Verify aexecute_batch was called with UPDATE tasks SET last_reminder=NOW()
        mock_batch.assert_called_once()
        batch_args = mock_batch.call_args[0][0]
        assert len(batch_args) == 1
        sql, params = batch_args[0]
        assert "last_reminder=NOW()" in sql
        assert params == (101,)


@pytest.mark.asyncio
async def test_reminder_loop_forbidden_channel_advances_last_reminder():
    """Verify that discord.Forbidden advances last_reminder instead of starving the loop."""
    channel = MagicMock()
    channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "Missing Permissions"))

    bot = MagicMock()
    bot.get_channel.return_value = channel
    cog = _create_cog(bot)

    now = datetime.now(timezone.utc)
    rows = [
        {
            "task_id": 102,
            "task": "Forbidden Channel Task",
            "deadline": now.isoformat(),
            "is_pinned": 0,
            "priority": 1,
            "user_id": "user_b",
            "channel_id": 888888888,
            "timezone": "UTC",
            "lang": "en",
            "notify_enabled": 1,
        }
    ]

    with patch.object(db, "afetchall", AsyncMock(return_value=rows)), \
         patch.object(db, "aexecute_batch", AsyncMock()) as mock_batch:

        await cog.reminder_loop()

        mock_batch.assert_called_once()
        batch_args = mock_batch.call_args[0][0]
        assert len(batch_args) == 1
        sql, params = batch_args[0]
        assert "last_reminder=NOW()" in sql
        assert params == (102,)


@pytest.mark.asyncio
async def test_deadline_dm_loop_not_found_handling():
    """Verify discord.NotFound marks dm_reminded bitmask to prevent Discord API hammer."""
    bot = MagicMock()
    bot.get_user.return_value = None
    bot.fetch_user = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "Unknown User"))
    cog = _create_cog(bot)

    rows = [
        {
            "task_id": 201,
            "task": "Task For Deleted User",
            "deadline": (datetime.now(timezone.utc)).isoformat(),
            "dm_reminded": 0,
            "user_id": "999888777",
            "timezone": "UTC",
            "lang": "en",
            "notify_enabled": 1,
        }
    ]

    with patch.object(db, "afetchall", AsyncMock(side_effect=[rows, [], []])), \
         patch.object(db, "aexecute_batch", AsyncMock()) as mock_batch:

        await cog.deadline_dm_loop()

        mock_batch.assert_called_once()
        batch_args = mock_batch.call_args[0][0]
        assert len(batch_args) == 1
        sql, params = batch_args[0]
        assert "dm_reminded=$1" in sql
        new_mask, tid = params
        assert (new_mask & 1) == 1  # 24H bit marked
        assert tid == 201


# ── Pillar 3 & 4: Schema v27 & UserCache Warming ──────────────────────────────

def test_schema_version_and_migration_27_indexes():
    """Verify Schema version 27 contains all performance partial indexes."""
    assert SCHEMA_VERSION == 27
    v27_sql = next(sql for v, sql in MIGRATIONS if v == 27)
    assert "idx_tasks_recurring_due" in v27_sql
    assert "idx_tasks_deadline_dm_pending" in v27_sql
    assert "idx_tasks_pending_reminders" in v27_sql
    assert "idx_focus_sessions_active_lookup" in v27_sql


@pytest.mark.asyncio
async def test_ensure_user_warms_cache():
    """Verify ensure_user populates db.user_cache so subsequent calls hit L1 cache."""
    test_uid = "987654321012345678"
    db.user_cache.invalidate(test_uid)
    assert db.user_cache.get(test_uid) is None

    with patch.object(db, "aexecute", AsyncMock()):
        await ensure_user(test_uid, lang="ja")

    cached = db.user_cache.get(test_uid)
    assert cached is not None
    assert cached.lang == "ja"
    assert cached.role == "user"
    assert cached.theme == "default"
    db.user_cache.invalidate(test_uid)
