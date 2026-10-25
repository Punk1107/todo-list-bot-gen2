"""
tests/test_system_bugfixes_3.py
Automated regression tests for System Bugfix Round 3.
Verifies all 10 bug areas across the codebase.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest
import discord

from core.database import db
import handlers.reminders_cog as reminders_cog
from search_recommendation.query_builder import SqlQueryBuilder
from search_recommendation.views import TaskSelectFromSearch, TaskQuickActionFromRecommend
import handlers.task_views as task_views
import recovery.service as recovery_service
import gamification.service as gamification_service
import history_reporting.service as history_service
from organization.service import execute_saved_filter
from organization.models import SavedFilter, SavedFilterCriteria
import collaboration.service as collab_service
import routine_workflows.service as routine_service


# ─────────────────────────────────────────────────────────────────────────────
# 1. Recurring Renewal Preserves Metadata & Scope
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recurring_renewal_preserves_project_and_scope():
    """Verify recurring renewal query inserts project_id, guild_id, is_pinned, and is_private."""
    bot_mock = MagicMock()
    bot_mock.wait_until_ready = AsyncMock()
    cog = reminders_cog.RemindersCog(bot_mock)

    fake_task = {
        "task_id": 99,
        "task": "Daily Sync",
        "deadline": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        "priority": 2,
        "recurring": "daily",
        "recurrence_rule": None,
        "category_id": 3,
        "tags": "work,sync",
        "description": "Daily standup meeting",
        "owner_id": "user-42",
        "project_id": 10,
        "guild_id": "guild-88",
        "is_pinned": 1,
        "is_private": 1,
    }

    conn_mock = MagicMock()
    conn_mock.fetch = AsyncMock(return_value=[fake_task])
    conn_mock.execute = AsyncMock()

    trans_mock = MagicMock()
    trans_mock.__aenter__ = AsyncMock(return_value=None)
    trans_mock.__aexit__ = AsyncMock(return_value=None)
    conn_mock.transaction = MagicMock(return_value=trans_mock)

    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn_mock)
    acquire_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch.object(db, "acquire", return_value=acquire_ctx), \
         patch.object(db, "invalidate_stats", new=MagicMock()) as mock_inv:

        # Invoke recurring_loop underlying coroutine
        await cog.recurring_loop.coro(cog)

        insert_calls = [c for c in conn_mock.execute.call_args_list if "INSERT INTO tasks" in c[0][0]]
        assert len(insert_calls) == 1
        sql = insert_calls[0][0][0]
        params = insert_calls[0][0][1:]
        assert "project_id" in sql
        assert "guild_id" in sql
        assert "is_pinned" in sql
        assert "is_private" in sql
        assert params[9] == 10           # project_id ($10)
        assert params[10] == "guild-88"  # guild_id ($11)
        assert params[11] == 1           # is_pinned ($12)
        assert params[12] is True or params[12] == 1 # is_private ($13)
        mock_inv.assert_called_with("user-42")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Cleanup Loop Purges Expired Trash
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cleanup_loop_purges_expired_trash():
    """Verify cleanup loop calls purge_expired_trash(days=30)."""
    bot_mock = MagicMock()
    bot_mock.wait_until_ready = AsyncMock()
    cog = reminders_cog.RemindersCog(bot_mock)

    with patch.object(recovery_service, "purge_expired_trash", new=AsyncMock(return_value=5)) as mock_purge, \
         patch.object(db, "purge_all_caches", return_value={}):
        await cog.cleanup_loop.coro(cog)
        mock_purge.assert_called_once_with(days=30)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Recommendation Query & Views Exclude Soft-Deleted Tasks
# ─────────────────────────────────────────────────────────────────────────────

def test_recommendation_candidates_excludes_soft_deleted():
    """Verify SqlQueryBuilder().build_recommendation_candidates_query has t.is_deleted = FALSE."""
    builder = SqlQueryBuilder()
    sql, params = builder.build_recommendation_candidates_query("u123", guild_id=None, limit=10)
    assert "t.is_deleted = FALSE" in sql


@pytest.mark.asyncio
async def test_search_views_exclude_soft_deleted():
    """Verify search and recommendation views enforce is_deleted=FALSE."""
    import inspect
    import search_recommendation.views as sr_views
    source = inspect.getsource(sr_views)
    assert "SELECT * FROM tasks WHERE task_id=$1 AND is_deleted=FALSE" in source


# ─────────────────────────────────────────────────────────────────────────────
# 4. Task Views Guard Against Soft-Deleted Tasks
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_edit_task_modal_rejects_soft_deleted():
    """Verify EditTaskModal fails gracefully if task was soft-deleted."""
    task_row = {
        "task_id": 99,
        "owner_id": "100",
        "priority": 0,
        "recurring": None,
        "recurrence_rule": None,
        "deadline": None,
        "task": "Test Task",
        "description": "",
        "tags": "",
    }
    modal = task_views.EditTaskModal(task_row, lang="en")
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user.id = 100
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    with patch.object(db, "afetchone", new=AsyncMock(return_value=None)), \
         patch.object(db, "aexecute", new=AsyncMock()), \
         patch.object(db, "alog_action", new=AsyncMock()), \
         patch.object(db, "invalidate_stats", new=MagicMock()), \
         patch.object(db.query_cache, "invalidate_tables", new=MagicMock()):
        await modal.on_submit(interaction)
        assert interaction.response.send_message.called or interaction.followup.send.called
        msg = (interaction.response.send_message.call_args or interaction.followup.send.call_args)[0][0]
        assert "not found" in msg.lower()


@pytest.mark.asyncio
async def test_quick_action_buttons_reject_soft_deleted():
    """Verify _QuickActionButtons buttons reject soft-deleted tasks."""
    buttons = task_views._QuickActionButtons(
        task_id=99, uid="100", lang="en", tz_name="UTC", row_data={"is_pinned": 0}
    )
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user.id = 100
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    # Case 1: task really does not exist
    with patch.object(db, "afetchone", new=AsyncMock(return_value=None)):
        await buttons.quick_done.callback(interaction)
        assert interaction.response.send_message.called or interaction.followup.send.called
        msg = (interaction.response.send_message.call_args or interaction.followup.send.call_args)[0][0]
        assert "not found" in msg.lower()

    # Case 2: task is soft-deleted in Trash
    interaction.followup.send.reset_mock()
    interaction.response.send_message.reset_mock()
    with patch.object(db, "afetchone", new=AsyncMock(return_value={"task": "T", "status": "Pending", "is_deleted": True})):
        await buttons.quick_done.callback(interaction)
        assert interaction.response.send_message.called or interaction.followup.send.called
        msg = (interaction.response.send_message.call_args or interaction.followup.send.call_args)[0][0]
        assert "trash" in msg.lower()


@pytest.mark.asyncio
async def test_persistent_views_registration_excludes_soft_deleted():
    """Verify register_all_persistent_views filters out soft deleted tasks."""
    bot = MagicMock()
    bot.add_view = MagicMock()

    with patch.object(db, "afetchall", new=AsyncMock(return_value=[])) as mock_fetch:
        await task_views.register_all_persistent_views(bot)
        assert mock_fetch.call_count >= 1
        sql = mock_fetch.call_args_list[0][0][0]
        assert "AND t.is_deleted = FALSE" in sql


# ─────────────────────────────────────────────────────────────────────────────
# 5. Soft-Delete and Task Completion Stop Active Focus Sessions
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_soft_delete_stops_active_focus_sessions():
    """Verify soft_delete_task automatically stops active focus sessions."""
    fake_row = {
        "task_id": 50,
        "task": "Focus Task",
        "owner_id": "u1",
        "project_id": None,
        "guild_id": None,
        "is_deleted": False,
    }
    with patch.object(recovery_service.db, "afetchone", new=AsyncMock(return_value=fake_row)), \
         patch.object(recovery_service.db, "aexecute", new=AsyncMock()) as mock_exec, \
         patch.object(recovery_service.db, "alog_action", new=AsyncMock()):

        ok = await recovery_service.soft_delete_task(task_id=50, user_id="u1")
        assert ok is True
        assert mock_exec.call_count == 2
        focus_call = mock_exec.call_args_list[1][0][0]
        assert "UPDATE focus_sessions" in focus_call
        assert "status='stopped'" in focus_call


@pytest.mark.asyncio
async def test_complete_personal_task_stops_active_focus_sessions():
    """Verify complete_personal_task automatically stops active focus sessions."""
    fake_task = {
        "task_id": 77,
        "task": "Complete me",
        "priority": 1,
        "deadline": None,
        "completed_at": datetime.now(timezone.utc),
    }
    conn_mock = MagicMock()
    conn_mock.fetchrow = AsyncMock(return_value=fake_task)
    conn_mock.execute = AsyncMock()

    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn_mock)
    acquire_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch.object(gamification_service.db, "acquire", return_value=acquire_ctx), \
         patch.object(gamification_service, "_record_completion", new=AsyncMock(return_value=10)), \
         patch.object(gamification_service.db, "invalidate_stats", new=MagicMock()), \
         patch.object(gamification_service.db.query_cache, "invalidate_tables", new=MagicMock()):

        res = await gamification_service.complete_personal_task(77, "u1")
        assert res == 10
        # Check conn_mock.execute stopped focus sessions
        exec_calls = [c for c in conn_mock.execute.call_args_list if "UPDATE focus_sessions" in c[0][0]]
        assert len(exec_calls) == 1
        assert "status='stopped'" in exec_calls[0][0][0]


# ─────────────────────────────────────────────────────────────────────────────
# 6. Weekly Retrospective Excludes Cancelled Tasks
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_weekly_retrospective_excludes_cancelled_tasks():
    """Verify get_weekly_retrospective_data only carries over pending/in_progress tasks."""
    ref_time = datetime(2026, 10, 25, 20, 0, 0, tzinfo=timezone.utc)
    comp_events = [
        {"task_id": 1, "task_title": "T1", "priority": 1, "completed_at": ref_time},
    ]
    user_tasks = [
        {"task_id": 2, "task": "Active T2", "status": "Pending", "priority": 1, "deadline": None, "created_at": ref_time, "category_name": "Work"},
        {"task_id": 3, "task": "Cancelled T3", "status": "Cancelled", "priority": 1, "deadline": None, "created_at": ref_time, "category_name": "Work"},
    ]

    with patch("history_reporting.service.get_user_timezone", new=AsyncMock(return_value="UTC")), \
         patch("history_reporting.service.get_user_lang", new=AsyncMock(return_value="en")), \
         patch.object(history_service.db, "afetchall", new=AsyncMock(side_effect=[
             comp_events,  # task_completion_events
             user_tasks,   # user_tasks
             [],           # snooze_rows
         ])):

        data = await history_service.get_weekly_retrospective_data("user_1", ref_time=ref_time)
        # 1 completed, 1 pending. Cancelled task 3 must be excluded from total and completion rate!
        assert data.completed_tasks == 1
        assert data.total_tasks == 2
        assert data.completion_rate == 50.0


# ─────────────────────────────────────────────────────────────────────────────
# 7. Saved Filters Typed Date Comparison
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_saved_filter_due_within_days_typed_comparison():
    """Verify execute_saved_filter uses typed interval comparison instead of text string comparison."""
    crit = SavedFilterCriteria(due_within_days=7)
    saved_filter = SavedFilter(
        filter_id=1,
        owner_id="u1",
        guild_id=None,
        name="Due Soon",
        criteria=crit,
    )

    with patch.object(db, "afetchall", new=AsyncMock(return_value=[])) as mock_afetchall:
        await execute_saved_filter(
            saved_filter=saved_filter,
            user_id="u1",
            guild_id=None,
            limit=10,
        )
        sql = mock_afetchall.call_args[0][0]
        assert "t.deadline ~ '^\\d{4}-\\d{2}-\\d{2}'" in sql
        assert "t.deadline::timestamptz <= (NOW() + INTERVAL '7 days')" in sql


# ─────────────────────────────────────────────────────────────────────────────
# 8. Tasks Cog: Pin/Unpin/Recurring Invalidate Stats Cache
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pin_and_recurring_invalidate_stats():
    """Verify pin/unpin commands invalidate stats cache."""
    from handlers.tasks_cog import TasksCog
    bot = MagicMock()
    cog = TasksCog(bot)

    interaction = MagicMock(spec=discord.Interaction)
    interaction.user.id = 12345
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    # Test pin
    with patch.object(db, "afetchone", new=AsyncMock(return_value={"owner_id": "12345", "is_pinned": 0})), \
         patch.object(db, "aexecute", new=AsyncMock()), \
         patch.object(db, "invalidate_stats", new=MagicMock()) as mock_inv, \
         patch.object(db.query_cache, "invalidate_tables", new=MagicMock()), \
         patch.object(db, "alog_action", new=AsyncMock()), \
         patch("handlers.tasks_cog.get_user_lang", return_value="en"):

        await cog.pin.callback(cog, interaction, task_id=1)
        mock_inv.assert_called_with("12345")

    # Test unpin
    with patch.object(db, "afetchone", new=AsyncMock(return_value={"owner_id": "12345", "is_pinned": 1})), \
         patch.object(db, "aexecute", new=AsyncMock()), \
         patch.object(db, "invalidate_stats", new=MagicMock()) as mock_inv, \
         patch.object(db.query_cache, "invalidate_tables", new=MagicMock()), \
         patch.object(db, "alog_action", new=AsyncMock()), \
         patch("handlers.tasks_cog.get_user_lang", return_value="en"):

        await cog.unpin.callback(cog, interaction, task_id=1)
        mock_inv.assert_called_with("12345")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Category Remove Admin Override & Cache Invalidation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_category_remove_admin_owner_id_and_cache():
    """Verify category_remove resolves cat_owner and invalidates stats and caches."""
    from handlers.settings_cog import SettingsCog
    bot = MagicMock()
    cog = SettingsCog(bot)

    interaction = MagicMock(spec=discord.Interaction)
    interaction.user.id = 999  # Bot owner / admin
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    target_cat_row = {"category_id": 5, "name": "Work", "owner_id": "user-original"}

    with patch("handlers.settings_cog._is_owner", return_value=True), \
         patch.object(db, "afetchone", new=AsyncMock(return_value=target_cat_row)), \
         patch.object(db, "aexecute", new=AsyncMock()), \
         patch.object(db, "invalidate_stats", new=MagicMock()) as mock_inv, \
         patch.object(db.query_cache, "invalidate_tables", new=MagicMock()) as mock_inv_tables, \
         patch.object(db, "alog_action", new=AsyncMock()), \
         patch("handlers.settings_cog.get_user_lang", return_value="en"):

        await cog.category_remove.callback(cog, interaction, category_id=5)
        mock_inv.assert_any_call("user-original")
        mock_inv_tables.assert_called_with(["categories", "tasks"])


# ─────────────────────────────────────────────────────────────────────────────
# 10. Collaboration Reopen Shared Task Clears completed_at
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reopen_shared_task_clears_completed_at():
    """Verify update_task_status clears completed_at and invalidates stats when reopening."""
    from collaboration.models import Project, ProjectTask

    now = datetime.now(timezone.utc)
    fake_project = Project(
        project_id=1, guild_id="g1", name="Proj", description="",
        owner_id="u1", status="active", color="#5865F2", emoji="📁",
        channel_id=None, role_id=None, created_at=now, updated_at=now,
    )
    fake_task = ProjectTask(
        task_id=10, project_id=1, guild_id="g1", task="Task 10",
        deadline=None, priority=0, status="Completed", tags="",
        description="", owner_id="u1",
        created_at=now, updated_at=now,
        assignees=["u2"],
    )

    with patch("collaboration.service.get_project", new=AsyncMock(return_value=fake_project)), \
         patch("collaboration.service.get_project_task", new=AsyncMock(return_value=fake_task)), \
         patch("collaboration.service.get_member_role", new=AsyncMock(return_value="lead")), \
         patch.object(db, "execute", new=AsyncMock()) as mock_exec, \
         patch.object(db, "invalidate_stats", new=MagicMock()) as mock_inv, \
         patch.object(db.query_cache, "invalidate_tables", new=MagicMock()), \
         patch("collaboration.service.log_activity", new=AsyncMock()):

        await collab_service.update_task_status(
            task_id=10, project_id=1, guild_id="g1",
            new_status="Pending", actor_id="u1"
        )

        update_call = mock_exec.call_args[0][0]
        assert "completed_at=NULL" in update_call
        assert mock_inv.call_count >= 2  # assignee u2 and owner u1


# ─────────────────────────────────────────────────────────────────────────────
# 11. Routine Workflows Instantiation Uses Standard ISO Formatting
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_instantiate_template_iso_formatting():
    """Verify apply_template writes ISO format timestamps without ::timestamp."""
    from routine_workflows.models import TaskTemplate

    tmpl = TaskTemplate(
        template_id=1,
        name="Bug Template",
        category="Dev",
        description="Fix all bugs",
        priority=3,
        items={
            "task": "Parent Bugfix",
            "priority": 3,
            "relative_days": 2,
            "checklists": ["Check unit tests"],
            "subtasks": [{"task": "Subtask A", "relative_days": 1}],
        },
        owner_id="u1",
        guild_id="g1",
    )

    conn_mock = MagicMock()
    conn_mock.fetchrow = AsyncMock(side_effect=[{"task_id": 100}, {"task_id": 101}])
    conn_mock.execute = AsyncMock()

    trans_mock = MagicMock()
    trans_mock.__aenter__ = AsyncMock(return_value=None)
    trans_mock.__aexit__ = AsyncMock(return_value=None)
    conn_mock.transaction = MagicMock(return_value=trans_mock)

    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn_mock)
    acquire_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("routine_workflows.service.get_template", new=AsyncMock(return_value=tmpl)), \
         patch.object(routine_service.db, "acquire", return_value=acquire_ctx), \
         patch.object(routine_service.db, "invalidate_stats", new=MagicMock()), \
         patch.object(routine_service.db.query_cache, "invalidate_tables", new=MagicMock()), \
         patch.object(routine_service.db, "alog_action", new=AsyncMock()):

        res = await routine_service.apply_template(
            template_name="Bug Template",
            user_id="u1",
            guild_id="g1",
        )

        assert res["parent_task_id"] == 100
        assert res["subtask_count"] == 1
        assert res["checklist_count"] == 1

        # Check ISO 'T' in parent deadline
        assert "T" in res["deadline_iso"]

        # Check fetchrow calls for parent and subtask
        for call_args in conn_mock.fetchrow.call_args_list:
            sql = call_args[0][0]
            deadline_val = call_args[0][2]
            assert "::timestamp" not in sql
            assert "T" in deadline_val
