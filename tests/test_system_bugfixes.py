"""
tests/test_system_bugfixes.py — Automated Regression Tests for System-Wide Bugfixes
Validates all 10 bugfix areas:
1. Reminder Loop soft-delete isolation
2. Recurring Loop soft-delete isolation
3. Daily Digest soft-delete isolation
4. Autocomplete & Delete Command soft-delete handling
5. Today & Overdue views soft-delete isolation
6. Project Dependencies soft-deleted blocker exclusion
7. External Calendar Feed soft-delete isolation
8. Focus Session soft-delete validation
9. Gamification Inbox Zero & Complete Task soft-delete isolation
10. Routine Workflow template subtask soft-delete isolation
11. BulkWriter cancellation resilience & queue preservation
12. StatsCache analytics key invalidation sync
13. Webserver /ready probe NoneType DB pool graceful handling
14. Date parser Feb 29 leap-day rollover safety
15. Eisenhower Matrix personal DM scope (project_id IS NULL)
"""
from __future__ import annotations

import asyncio
from typing import Any
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from aiohttp.test_utils import make_mocked_request
import pytz

from handlers.reminders_cog import RemindersCog, _build_digest_embed
from handlers.tasks_cog import TasksCog, task_autocomplete
from handlers.task_views import _build_today_embed_and_view, _build_overdue_embed_and_view
from collaboration import service as collab_service
from calendar_feed import service as cal_service
from focus.cog import FocusCog
from gamification import service as gamification_service
from routine_workflows import service as routine_service
from organization import service as org_service
from utils.helpers import parse_deadline
from utils.webserver import _ready
from core.database import BulkWriter, db


# ─────────────────────────────────────────────────────────────────────────────
# 1. Reminders & Recurring Loops Soft-Delete Isolation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reminder_loop_ignores_soft_deleted_tasks():
    """Verify that reminder_loop query requires t.is_deleted = FALSE."""
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()

    with patch("discord.ext.tasks.Loop.start"):
        cog = RemindersCog(bot)

    mock_afetchall = AsyncMock(return_value=[])
    with patch("handlers.reminders_cog.db.afetchall", mock_afetchall):
        await cog.reminder_loop()

    assert mock_afetchall.called
    sql = mock_afetchall.call_args[0][0]
    assert "t.is_deleted = FALSE" in sql, "reminder_loop query must filter out soft-deleted tasks"


@pytest.mark.asyncio
async def test_recurring_loop_does_not_resurrect_deleted_task():
    """Verify that recurring_loop query requires is_deleted = FALSE."""
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()

    with patch("discord.ext.tasks.Loop.start"):
        cog = RemindersCog(bot)

    mock_conn = MagicMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.transaction = MagicMock(return_value=AsyncMock())
    mock_conn.transaction.return_value.__aenter__ = AsyncMock()
    mock_conn.transaction.return_value.__aexit__ = AsyncMock()

    mock_acquire = MagicMock()
    mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire.return_value.__aexit__ = AsyncMock()

    with patch("handlers.reminders_cog.db.acquire", mock_acquire):
        await cog.recurring_loop()

    assert mock_conn.fetch.called
    sql = mock_conn.fetch.call_args[0][0]
    assert "is_deleted = FALSE" in sql, "recurring_loop query must filter out soft-deleted tasks"


@pytest.mark.asyncio
async def test_daily_digest_excludes_soft_deleted_tasks():
    """Verify that _build_digest_embed filters out soft-deleted tasks across all queries."""
    mock_afetchall = AsyncMock(return_value=[])
    mock_afetchone = AsyncMock(return_value={"c": 0})
    now_utc = datetime.now(timezone.utc)
    local_now = datetime.now(pytz.utc)

    with patch("handlers.reminders_cog.db.afetchall", mock_afetchall), \
         patch("handlers.reminders_cog.db.afetchone", mock_afetchone):
        await _build_digest_embed("user_123", "en", "UTC", local_now, now_utc)

    # Check that each query made had is_deleted=FALSE
    for call in mock_afetchall.call_args_list:
        sql = call[0][0]
        assert "is_deleted=FALSE" in sql or "is_deleted = FALSE" in sql

    for call in mock_afetchone.call_args_list:
        sql = call[0][0]
        assert "is_deleted=FALSE" in sql or "is_deleted = FALSE" in sql


# ─────────────────────────────────────────────────────────────────────────────
# 2. Autocomplete & Delete Command Soft-Delete Handling
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_task_autocomplete_excludes_soft_deleted_tasks():
    """Verify that task_autocomplete filters is_deleted = FALSE in both branches."""
    mock_afetchall = AsyncMock(return_value=[])

    with patch("handlers.tasks_cog.db.afetchall", mock_afetchall):
        # 1. Search text provided
        interaction = MagicMock()
        interaction.user.id = 123456
        res1 = await task_autocomplete(interaction, "meeting")
        assert mock_afetchall.called
        sql1 = mock_afetchall.call_args[0][0]
        assert "is_deleted = FALSE" in sql1

        # 2. Search text empty
        mock_afetchall.reset_mock()
        res2 = await task_autocomplete(interaction, "")
        assert mock_afetchall.called
        sql2 = mock_afetchall.call_args[0][0]
        assert "is_deleted = FALSE" in sql2


@pytest.mark.asyncio
async def test_delete_command_handles_already_deleted_task():
    """Verify that /delete on an already soft-deleted task informs user without re-prompting."""
    bot = MagicMock()
    cog = TasksCog(bot)

    interaction = MagicMock()
    interaction.user.id = 123456
    interaction.response.send_message = AsyncMock()

    # Task exists but is_deleted = TRUE
    row = {"task": "Old Task", "owner_id": "123456", "is_deleted": True}
    with patch("handlers.tasks_cog.db.afetchone", AsyncMock(return_value=row)), \
         patch("handlers.tasks_cog.get_user_lang", AsyncMock(return_value="en")):
        delete_cmd: Any = cog.delete
        await delete_cmd.callback(cog, interaction, task_id=42)

    assert interaction.response.send_message.called
    kwargs = interaction.response.send_message.call_args[1]
    args = interaction.response.send_message.call_args[0]
    msg = args[0] if args else kwargs.get("content", "")
    assert "already in the Recycle Bin" in msg or "trash" in msg.lower()
    assert kwargs.get("ephemeral") is True


# ─────────────────────────────────────────────────────────────────────────────
# 3. Today & Overdue Views Soft-Delete Isolation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_today_and_overdue_views_exclude_soft_deleted_tasks():
    """Verify that _build_today_embed_and_view and _build_overdue_embed_and_view query is_deleted=FALSE."""
    mock_afetchall = AsyncMock(return_value=[])
    mock_afetchone = AsyncMock(return_value={"c": 0})

    with patch("handlers.task_views.db.afetchall", mock_afetchall), \
         patch("handlers.task_views.db.afetchone", mock_afetchone):
        await _build_today_embed_and_view("user_123", "en", "UTC")
        assert mock_afetchall.called
        assert "is_deleted=FALSE" in mock_afetchall.call_args[0][0]
        assert "is_deleted=FALSE" in mock_afetchone.call_args[0][0]

        mock_afetchall.reset_mock()
        await _build_overdue_embed_and_view("user_123", "en", "UTC")
        assert mock_afetchall.called
        assert "is_deleted=FALSE" in mock_afetchall.call_args[0][0]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Collaboration Dependencies Soft-Deleted Blocker Exclusion
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_project_dependency_ignores_deleted_blocker():
    """Verify that _get_incomplete_task_blockers ignores soft-deleted blockers."""
    mock_fetchall = AsyncMock(return_value=[])
    with patch("collaboration.service.db.fetchall", mock_fetchall):
        await collab_service._get_incomplete_task_blockers(10, 1, "guild_1")

    assert mock_fetchall.called
    sql = mock_fetchall.call_args[0][0]
    assert "blocker.is_deleted = FALSE" in sql


# ─────────────────────────────────────────────────────────────────────────────
# 5. External Calendar Feed Soft-Delete Isolation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_calendar_feed_excludes_soft_deleted_tasks():
    """Verify that build_calendar_feed filters out soft-deleted tasks."""
    mock_afetchone = AsyncMock(return_value={"user_id": "u1"})
    mock_afetchall = AsyncMock(return_value=[])
    valid_token = cal_service.create_feed_token()

    with patch("calendar_feed.service.db.afetchone", mock_afetchone), \
         patch("calendar_feed.service.db.afetchall", mock_afetchall):
        await cal_service.build_calendar_feed(valid_token)

    assert mock_afetchall.called
    sql = mock_afetchall.call_args[0][0]
    assert "is_deleted = FALSE" in sql


# ─────────────────────────────────────────────────────────────────────────────
# 6. Focus Session Soft-Delete Validation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_focus_mode_rejects_soft_deleted_task():
    """Verify that starting pomodoro ignores soft-deleted tasks."""
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    with patch("discord.ext.tasks.Loop.start"):
        cog = FocusCog(bot)

    mock_conn = MagicMock()
    # Task row fetch returns None because is_deleted=FALSE filter matched nothing
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=AsyncMock())
    mock_conn.transaction.return_value.__aenter__ = AsyncMock()
    mock_conn.transaction.return_value.__aexit__ = AsyncMock()

    mock_acquire = MagicMock()
    mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire.return_value.__aexit__ = AsyncMock()

    interaction = MagicMock()
    interaction.user.id = 12345
    interaction.response.send_message = AsyncMock()

    with patch("focus.cog.db.acquire", mock_acquire), \
         patch("focus.cog.get_user_lang", AsyncMock(return_value="en")), \
         patch("focus.cog.ensure_user", AsyncMock()):
        start_cmd: Any = cog.start
        await start_cmd.callback(cog, interaction, task_id=99)

    assert mock_conn.fetchrow.called
    sql = mock_conn.fetchrow.call_args[0][0]
    assert "is_deleted=FALSE" in sql or "is_deleted = FALSE" in sql
    assert interaction.response.send_message.called


# ─────────────────────────────────────────────────────────────────────────────
# 7. Gamification Soft-Delete Isolation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gamification_inbox_zero_with_deleted_tasks():
    """Verify that inbox_zero badge query checks is_deleted=FALSE."""
    mock_conn = MagicMock()
    mock_conn.fetchrow = AsyncMock(return_value={
        "timezone": "UTC",
        "streak_days": 1,
        "streak_last_completion": datetime.now(timezone.utc).date()
    })
    mock_conn.fetchval = AsyncMock(return_value=False)  # No remaining active pending tasks
    mock_conn.execute = AsyncMock()

    task_mock = {
        "task_id": 1,
        "task": "Test Task",
        "priority": 1,
        "deadline": None,
        "guild_id": None,
        "project_id": None,
    }

    with patch("gamification.service._award", AsyncMock(return_value=True)):
        awarded = await gamification_service._record_completion(
            mock_conn, task_mock, "u1", datetime.now(timezone.utc)
        )

    assert mock_conn.fetchval.called
    sql = mock_conn.fetchval.call_args[0][0]
    assert "is_deleted=FALSE" in sql or "is_deleted = FALSE" in sql
    assert "inbox_zero" in awarded


@pytest.mark.asyncio
async def test_gamification_complete_personal_task_ignores_deleted():
    """Verify that complete_personal_task UPDATE query checks is_deleted = FALSE."""
    mock_conn = MagicMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=AsyncMock())
    mock_conn.transaction.return_value.__aenter__ = AsyncMock()
    mock_conn.transaction.return_value.__aexit__ = AsyncMock()

    mock_acquire = MagicMock()
    mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire.return_value.__aexit__ = AsyncMock()

    with patch("gamification.service.db.acquire", mock_acquire):
        res = await gamification_service.complete_personal_task(101, "u1")

    assert mock_conn.fetchrow.called
    sql = mock_conn.fetchrow.call_args[0][0]
    assert "is_deleted = FALSE" in sql
    assert res is None


# ─────────────────────────────────────────────────────────────────────────────
# 8. Routine Workflows Subtask Soft-Delete Isolation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_routine_create_template_ignores_soft_deleted_subtasks():
    """Verify that create_template_from_task filters is_deleted = FALSE for parent and subtasks."""
    mock_afetchone = AsyncMock(return_value={"task_id": 1, "task": "Parent", "created_at": None, "deadline": None})
    mock_afetchall = AsyncMock(return_value=[])

    with patch("routine_workflows.service.db.afetchone", mock_afetchone), \
         patch("routine_workflows.service.db.afetchall", mock_afetchall), \
         patch("routine_workflows.service.get_checklists", AsyncMock(return_value=[])), \
         patch("routine_workflows.service.create_custom_template", AsyncMock(return_value=MagicMock())):
        await routine_service.create_template_from_task(1, "tpl_1", "u1")

    assert mock_afetchone.called
    assert "is_deleted = FALSE" in mock_afetchone.call_args[0][0]

    assert mock_afetchall.called
    assert "is_deleted = FALSE" in mock_afetchall.call_args[0][0]


# ─────────────────────────────────────────────────────────────────────────────
# 9. Concurrency & BulkWriter Cancellation Resilience
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bulkwriter_flush_on_task_cancellation_preserves_queue():
    """Verify that when BulkWriter.flush() encounters CancelledError, unflushed items are restored."""
    writer = BulkWriter(pool_getter=lambda: MagicMock(), interval_ms=100)
    writer.enqueue("INSERT INTO audit_log VALUES (1)", ())
    writer.enqueue("INSERT INTO audit_log VALUES (2)", ())

    assert len(writer._queue) == 2

    # Mock pool acquire to raise CancelledError mid-flush
    mock_pool = MagicMock()
    mock_pool.acquire.side_effect = asyncio.CancelledError()
    writer._pool_getter = lambda: mock_pool

    with pytest.raises(asyncio.CancelledError):
        await writer.flush()

    # The 2 items MUST be requeued back into writer._queue
    assert len(writer._queue) == 2, "Items must be preserved on CancelledError"


# ─────────────────────────────────────────────────────────────────────────────
# 10. Cache Synchronization (invalidate_stats & analytics)
# ─────────────────────────────────────────────────────────────────────────────

def test_stats_cache_invalidates_analytics_key():
    """Verify that invalidate_stats busts both stats:{uid} and analytics:{uid}."""
    uid = "user_test_999"
    with patch.object(db.stats_cache, "invalidate") as mock_inval, \
         patch.object(db.query_cache, "invalidate_table") as mock_table:
        db.invalidate_stats(uid)

    inval_calls = [c[0][0] for c in mock_inval.call_args_list]
    assert uid in inval_calls, f"Expected {uid} in invalidate calls"
    assert f"analytics:{uid}" in inval_calls, f"Expected analytics:{uid} in invalidate calls"
    assert mock_table.called


# ─────────────────────────────────────────────────────────────────────────────
# 11. Webserver /ready Probe Graceful Handling
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webserver_ready_probe_handles_none_pool_gracefully():
    """Verify that /ready probe returns 503 instead of crashing when db._pool is None."""
    req = make_mocked_request("GET", "/ready")
    with patch("core.database.db._pool", None):
        resp = await _ready(req)

    assert resp.status == 503
    assert resp.content_type == "application/json"
    import json
    data = json.loads(resp.text)
    assert data["ready"] is False
    assert "Database pool not initialized" in data["error"]


# ─────────────────────────────────────────────────────────────────────────────
# 12. Date Parser Leap Year Rollover
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_deadline_leap_year_rollover():
    """Verify that parse_datetime on Feb 29 rolls over without crashing if next year is non-leap."""
    # When now is March 1, 2028 (leap year), parsing "29/02 14:00" is in past,
    # so it rolls over to 2029 (non-leap year). It should fallback to 28/02/2029 without ValueError.
    past_leap_now = datetime(2028, 3, 1, 12, 0, tzinfo=pytz.utc)
    res = parse_deadline("29/02 14:00", tz_name="Asia/Bangkok", now=past_leap_now)
    assert res is not None
    assert isinstance(res, datetime)
    assert res.year == 2029
    assert res.month == 2
    assert res.day == 28


# ─────────────────────────────────────────────────────────────────────────────
# 13. Eisenhower Matrix Personal DM Scoping
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_eisenhower_matrix_personal_scope_includes_guild_context_personal_tasks():
    """Verify that get_eisenhower_matrix personal mode queries project_id IS NULL."""
    mock_afetchall = AsyncMock(return_value=[])

    with patch("organization.service.db.afetchall", mock_afetchall):
        await org_service.get_eisenhower_matrix(user_id="user_1", guild_id=None, project_id=None)

    assert mock_afetchall.called
    sql = mock_afetchall.call_args[0][0]
    assert "project_id IS NULL" in sql, "Personal matrix must query project_id IS NULL, not guild_id IS NULL"
    assert "is_deleted = FALSE" in sql
