"""
tests/test_system_bugfixes_2.py — Automated Regression Tests for Batch 2 System-Wide Bugfixes

Validates the following bugfixes and enhancements:
1. TodoBot.close() idempotency and re-entrancy guard
2. bot.tree.on_error assignment and CommandInvokeError unwrapping in on_app_command_error
3. /recurring query fetches owner_id and deadline with is_deleted=FALSE (no KeyError)
4. /delete checks ownership before checking is_deleted
5. _async_build_task_embed excludes soft-deleted subtasks
6. get_member_role supports Record mapping objects
7. claim_task and update_task_status deny viewer role
8. get_project_board excludes soft-deleted blocker dependencies
9. get_weekly_retrospective_data handles naive vs aware timestamp safely with audit_log
10. generate_interactive_html handles priority 0 correctly
11. recurring_loop advances overdue recurring deadlines until nxt > now
12. _build_digest_embed caps field value length to avoid Discord 400
13. EditTaskModal preserves unchanged overdue deadlines without validation error
14. _QuickActionButtons handles missing tasks gracefully and handles NULL deadlines safely
15. suggest_unique_task_name filters is_deleted=FALSE and escapes wildcards
16. calculate_next_deadline clamps month-end rollovers correctly
17. build_csv_export sanitizes CSV formula injection
18. get_user_weekly_retrospective preserves 0 as disabled
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytz

from main import TodoBot, on_app_command_error, bot as global_bot
from handlers.tasks_cog import TasksCog, _async_build_task_embed
from handlers.reminders_cog import RemindersCog, _build_digest_embed
from handlers.task_views import EditTaskModal, _QuickActionButtons
from collaboration import service as collab_service
from collaboration.models import Project, ProjectTask
from history_reporting import service as retro_service
from utils import helpers
from utils.conflict_resolver import suggest_unique_task_name


# ─────────────────────────────────────────────────────────────────────────────
# 1. TodoBot.close() Re-entrancy Guard
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bot_close_idempotent():
    """Verify TodoBot.close() is protected against concurrent/re-entrant calls."""
    bot_inst = TodoBot.__new__(TodoBot)
    bot_inst._is_closing = False
    bot_inst._alert_dispatcher = None
    bot_inst._webserver_runner = None

    with patch("discord.ext.commands.Bot.close", new_callable=AsyncMock) as mock_super_close, \
         patch("core.database.db.close", new_callable=AsyncMock) as mock_db_close:

        await asyncio.gather(bot_inst.close(), bot_inst.close())

        assert mock_super_close.call_count == 1
        assert mock_db_close.call_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# 2. Command Tree Error Handling & Unwrapping
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_on_app_command_error_unwraps_invoke_error():
    """Verify on_app_command_error unwraps CommandInvokeError and bot.tree.on_error is wired."""
    import discord
    from discord import app_commands

    assert global_bot.tree.on_error is on_app_command_error

    interaction = MagicMock(spec=discord.Interaction)
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    interaction.command.name = "test_cmd"
    interaction.user.id = 123456
    interaction.guild_id = None

    underlying = ValueError("Underlying logic error")
    wrapper = app_commands.CommandInvokeError(interaction.command, underlying)

    with patch("monitoring.error_tracker.error_tracker.record") as mock_record, \
         patch("utils.helpers.get_user_lang", AsyncMock(return_value="en")):
        await on_app_command_error(interaction, wrapper)
        assert mock_record.called
        assert mock_record.call_args[0][0] == underlying


# ─────────────────────────────────────────────────────────────────────────────
# 3. TasksCog: /recurring, /delete, and Subtasks Soft-Delete
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recurring_command_fetches_deadline_and_soft_delete():
    """Verify /recurring command query includes owner_id, deadline and is_deleted=FALSE."""
    bot = MagicMock()
    cog = TasksCog(bot)
    interaction = MagicMock()
    interaction.user.id = 999
    interaction.response.send_message = AsyncMock()

    mock_row = {"owner_id": "999", "deadline": "2026-12-31T12:00:00"}
    with patch("handlers.tasks_cog.db.afetchone", AsyncMock(return_value=mock_row)) as mock_fetch, \
         patch("handlers.tasks_cog.db.aexecute", AsyncMock()), \
         patch("handlers.tasks_cog.db.alog_action", AsyncMock()), \
         patch("handlers.tasks_cog.get_user_lang", AsyncMock(return_value="en")):

        await cog.recurring.callback(cog, interaction, task_id=42, interval="daily")
        assert mock_fetch.called
        sql = mock_fetch.call_args[0][0]
        assert "deadline" in sql
        assert "owner_id" in sql
        assert "is_deleted=FALSE" in sql or "is_deleted = FALSE" in sql
        assert interaction.response.send_message.called


@pytest.mark.asyncio
async def test_delete_command_checks_owner_before_is_deleted():
    """Verify /delete command checks task ownership before reporting already deleted."""
    bot = MagicMock()
    cog = TasksCog(bot)
    interaction = MagicMock()
    interaction.user.id = 888  # Different user
    interaction.response.send_message = AsyncMock()

    # Task belongs to user 999, but is already is_deleted=1
    mock_row = {"task": "Secret Task", "owner_id": "999", "is_deleted": 1}
    with patch("handlers.tasks_cog.db.afetchone", AsyncMock(return_value=mock_row)), \
         patch("handlers.tasks_cog.get_user_lang", AsyncMock(return_value="en")):

        await cog.delete.callback(cog, interaction, task_id=10)
        assert interaction.response.send_message.called
        sent_msg = interaction.response.send_message.call_args[0][0]
        assert "not own" in sent_msg.lower() or "not_owned" in sent_msg.lower() or "❌" in sent_msg


@pytest.mark.asyncio
async def test_async_build_task_embed_filters_deleted_subtasks():
    """Verify _async_build_task_embed subtask query filters is_deleted = FALSE."""
    mock_row = {
        "task_id": 1,
        "task": "Parent Task",
        "owner_id": "123",
        "status": "Pending",
        "priority": 1,
        "deadline": None,
        "created_at": "2026-01-01T00:00:00",
        "is_deleted": False,
        "category_id": None,
        "description": None,
        "tags": None,
        "is_pinned": 0,
    }
    with patch("handlers.tasks_cog.db.afetchall", AsyncMock(return_value=[])) as mock_fetch:
        await _async_build_task_embed(mock_row, "en", "UTC")
        assert mock_fetch.called
        sql = mock_fetch.call_args[0][0]
        assert "is_deleted = FALSE" in sql or "is_deleted=FALSE" in sql


# ─────────────────────────────────────────────────────────────────────────────
# 4. Collaboration Service Permissions & Blockers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_project_permission_supports_record_mapping():
    """Verify get_member_role works with asyncpg Record mock (non-dict mapping)."""
    class FakeRecord:
        def __init__(self, data):
            self._data = data
        def __getitem__(self, item):
            return self._data[item]
        def get(self, item, default=None):
            return self._data.get(item, default)

    fake_member = FakeRecord({"role": "lead"})

    with patch("collaboration.service.db.fetchone", AsyncMock(return_value=fake_member)):
        role = await collab_service.get_member_role(1, "123")
        assert role == "lead"


@pytest.mark.asyncio
async def test_claim_task_and_update_status_reject_viewer():
    """Verify viewers cannot claim tasks or update task status."""
    project = MagicMock(spec=Project)
    project.project_id = 1
    project.guild_id = "g1"
    project.owner_id = "owner_1"

    task = MagicMock(spec=ProjectTask)
    task.task_id = 10
    task.project_id = 1
    task.guild_id = "g1"
    task.status = "Pending"
    task.owner_id = "creator_1"
    task.assignees = []
    task.task = "Task 1"

    with patch("collaboration.service.get_project", AsyncMock(return_value=project)), \
         patch("collaboration.service.get_project_task", AsyncMock(return_value=task)), \
         patch("collaboration.service.get_member_role", AsyncMock(return_value="viewer")), \
         patch("collaboration.service._get_incomplete_task_blockers", AsyncMock(return_value=[])):

        # Claim as viewer must raise ProjectPermissionError
        with pytest.raises(collab_service.ProjectPermissionError):
            await collab_service.claim_task(task_id=10, project_id=1, guild_id="g1", claimer_id="viewer_1")

        # Update status as viewer must raise ProjectPermissionError
        with pytest.raises(collab_service.ProjectPermissionError):
            await collab_service.update_task_status(task_id=10, project_id=1, guild_id="g1", new_status="Completed", actor_id="viewer_1")


@pytest.mark.asyncio
async def test_get_project_board_excludes_deleted_blockers():
    """Verify get_project_board excludes soft-deleted blocker tasks."""
    project = MagicMock(spec=Project)
    project.project_id = 1
    project.guild_id = "g1"
    project.owner_id = "owner_1"

    tasks_mock = [{
        "task_id": 10, "task": "Task A", "status": "Todo", "priority": 1,
        "deadline": None, "project_id": 1, "guild_id": "g1", "is_deleted": False,
        "is_private": False, "owner_id": "1", "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }]

    with patch("collaboration.service.get_project", AsyncMock(return_value=project)), \
         patch("collaboration.service.db.fetchall", AsyncMock(side_effect=[
             tasks_mock,  # tasks
             [],          # assignees
             [],          # roles
             [],          # blockers
         ])) as mock_fetch:

        await collab_service.get_project_board(1, "g1")
        # 4th query is the blocker dependency query
        blocker_sql = mock_fetch.call_args_list[3][0][0]
        assert "blocker.is_deleted = FALSE" in blocker_sql or "blocker.is_deleted=FALSE" in blocker_sql


# ─────────────────────────────────────────────────────────────────────────────
# 5. History Reporting Naive Timestamp & HTML formatting
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_weekly_retrospective_data_naive_timestamps():
    """Verify get_weekly_retrospective_data uses naive UTC for audit_log query."""
    with patch("history_reporting.service.get_user_timezone", AsyncMock(return_value="UTC")), \
         patch("history_reporting.service.get_user_lang", AsyncMock(return_value="en")), \
         patch("history_reporting.service.db.afetchall", AsyncMock(return_value=[])) as mock_fetch:

        await retro_service.get_weekly_retrospective_data("123")
        assert mock_fetch.call_count >= 2
        # Check audit_log query args (2nd call when comp_events is empty)
        audit_call_args = mock_fetch.call_args_list[1][0]
        params = audit_call_args[1]
        start_arg = params[1]
        end_arg = params[2]
        assert isinstance(start_arg, datetime)
        assert start_arg.tzinfo is None, "audit_log start time must be naive UTC"
        assert end_arg.tzinfo is None, "audit_log end time must be naive UTC"


def test_generate_interactive_html_priority_zero():
    """Verify generate_interactive_html handles priority 0 without defaulting to 1."""
    tasks = [
        {"task_id": 1, "task": "Zero Priority Task", "priority": 0, "status": "Pending", "created_at": "2026-01-01", "deadline": None, "category_id": None},
    ]
    html = retro_service.generate_interactive_html(tasks, [], user_id="123", tz_name="UTC", lang="en")
    assert "Zero Priority Task" in html
    assert ">P0</span>" in html


# ─────────────────────────────────────────────────────────────────────────────
# 6. Reminders Loop: Recurring Cascade Prevention & Embed Truncation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recurring_loop_advances_multiple_intervals():
    """Verify recurring_loop advances deadlines multiple intervals until nxt > now."""
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()

    with patch("discord.ext.tasks.Loop.start"):
        cog = RemindersCog(bot)

    now_utc = datetime.now(timezone.utc)
    old_deadline = (now_utc - timedelta(days=5)).isoformat()
    mock_task = {
        "task_id": 100,
        "owner_id": "user_1",
        "task": "Daily overdue recurring",
        "deadline": old_deadline,
        "recurring": "daily",
        "recurrence_rule": None,
        "priority": 1,
        "category_id": None,
        "tags": None,
        "description": None,
    }

    mock_conn = MagicMock()
    mock_conn.fetch = AsyncMock(return_value=[mock_task])
    mock_conn.execute = AsyncMock()
    mock_conn.transaction = MagicMock(return_value=AsyncMock())
    mock_conn.transaction.return_value.__aenter__ = AsyncMock()
    mock_conn.transaction.return_value.__aexit__ = AsyncMock()

    mock_acquire = MagicMock()
    mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire.return_value.__aexit__ = AsyncMock()

    with patch("handlers.reminders_cog.db.acquire", mock_acquire):
        await cog.recurring_loop()

    assert mock_conn.execute.called
    exec_args = mock_conn.execute.call_args_list[1][0]
    new_deadline_str = exec_args[2]
    new_deadline = datetime.fromisoformat(new_deadline_str)
    if new_deadline.tzinfo is None:
        new_deadline = new_deadline.replace(tzinfo=timezone.utc)
    assert new_deadline > now_utc, "recurring task must advance until future to avoid cascade"


@pytest.mark.asyncio
async def test_build_digest_embed_caps_field_length():
    """Verify _build_digest_embed caps tasks in fields to avoid Discord 1024 char field limit."""
    tasks = [
        {"task_id": i, "task": f"Super long task description with lots of padding {i} " * 6, "deadline": "2026-12-31T23:59:59", "priority": 1}
        for i in range(25)
    ]
    with patch("handlers.reminders_cog.db.afetchall", AsyncMock(side_effect=[tasks, []])), \
         patch("handlers.reminders_cog.db.afetchone", AsyncMock(side_effect=[{"c": 0}, {"c": 25}])):

        embed = await _build_digest_embed(
            uid="123",
            lang="en",
            tz_name="UTC",
            local_now=datetime.now(pytz.utc),
            utc_now=datetime.now(timezone.utc),
        )
        for field in embed.fields:
            assert len(field.value) <= 1024, f"Field value exceeded Discord limit: {len(field.value)}"
        assert "... " in embed.fields[0].value


# ─────────────────────────────────────────────────────────────────────────────
# 7. EditTaskModal Deadline Preservation & Quick Action Fallbacks
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_edit_task_modal_preserves_overdue_deadline():
    """Verify EditTaskModal doesn't fail when leaving an overdue deadline unchanged."""
    task_row = {
        "task_id": 5, "owner_id": "123", "task": "My Task", "status": "Pending",
        "deadline": "2020-01-01T12:00:00", "priority": 1,
        "description": "", "tags": "", "recurring": None, "recurrence_rule": None,
    }
    modal = EditTaskModal(task_row, lang="en", tz_name="UTC")
    modal.task_name._value = "Updated Name"
    modal.deadline._value = modal._initial_deadline_str

    interaction = MagicMock()
    interaction.user.id = 123
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    with patch("handlers.task_views.get_user_timezone", AsyncMock(return_value="UTC")), \
         patch("handlers.task_views.check_duplicate_task", AsyncMock(return_value=None)), \
         patch("handlers.task_views.db.afetchone", AsyncMock(return_value=task_row)), \
         patch("handlers.task_views.db.aexecute", AsyncMock()) as mock_exec, \
         patch("handlers.task_views.db.alog_action", AsyncMock()), \
         patch("handlers.task_views.db.invalidate_stats", MagicMock()):

        await modal.on_submit(interaction)
        assert mock_exec.called


@pytest.mark.asyncio
async def test_quick_action_snooze_none_deadline():
    """Verify _QuickActionButtons.quick_snooze works when task deadline is NULL."""
    view = _QuickActionButtons(task_id=10, uid="123", lang="en", tz_name="UTC", row_data=None)
    interaction = MagicMock()
    interaction.user.id = 123
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    mock_row = {"deadline": None, "task": "No deadline task"}
    with patch("handlers.task_views.db.afetchone", AsyncMock(return_value=mock_row)), \
         patch("handlers.task_views.db.aexecute", AsyncMock()) as mock_exec, \
         patch("handlers.task_views.db.alog_action", AsyncMock()), \
         patch("handlers.task_views.db.invalidate_stats", MagicMock()):

        await view.quick_snooze.callback(interaction)
        assert mock_exec.called
        new_dl = mock_exec.call_args[0][1][0]
        assert new_dl is not None, "quick_snooze on NULL deadline should produce a valid tomorrow deadline"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Date Parsing, Helpers & Security
# ─────────────────────────────────────────────────────────────────────────────

def test_calculate_next_deadline_month_end_clamping():
    """Verify calculate_next_deadline clamps to last day of month on rollover."""
    jan31 = "2026-01-31T12:00:00"
    nxt = helpers.calculate_next_deadline(jan31, "monthly")
    assert nxt is not None
    dt = datetime.fromisoformat(nxt)
    assert dt.month == 2
    assert dt.day == 28  # 2026 is non-leap year


def test_build_csv_export_formula_injection_sanitization():
    """Verify build_csv_export prefixes formula characters with single quote."""
    dangerous_tasks = [
        {"task_id": 1, "task": "=cmd|' /C calc'!A0", "status": "Pending", "priority": 1, "deadline": None, "created_at": "2026-01-01"},
        {"task_id": 2, "task": "+12345", "status": "Pending", "priority": 1, "deadline": None, "created_at": "2026-01-01"},
        {"task_id": 3, "task": "-dangerous", "status": "Pending", "priority": 1, "deadline": None, "created_at": "2026-01-01"},
        {"task_id": 4, "task": "@dangerous", "status": "Pending", "priority": 1, "deadline": None, "created_at": "2026-01-01"},
    ]
    csv_bytes = helpers.build_csv_export(dangerous_tasks, "UTC")
    csv_str = csv_bytes.getvalue().decode("utf-8-sig")

    assert "'=cmd|" in csv_str
    assert "'+12345" in csv_str
    assert "'-dangerous" in csv_str
    assert "'@dangerous" in csv_str


@pytest.mark.asyncio
async def test_suggest_unique_task_name_escapes_wildcards():
    """Verify suggest_unique_task_name filters is_deleted=FALSE and escapes wildcards."""
    with patch("core.database.db.afetchall", AsyncMock(return_value=[])) as mock_fetch:
        await suggest_unique_task_name("123", "Task 100% finished_today")
        assert mock_fetch.called
        sql = mock_fetch.call_args[0][0]
        params = mock_fetch.call_args[0][1]
        assert "is_deleted=FALSE" in sql or "is_deleted = FALSE" in sql
        assert "ESCAPE '\\\\'" in sql or "ESCAPE '\\'" in sql
        assert "100\\%" in params[1]
        assert "finished\\_today" in params[1]


@pytest.mark.asyncio
async def test_get_user_weekly_retrospective_preserves_zero():
    """Verify get_user_weekly_retrospective returns 0 when disabled, not defaulting to 1."""
    with patch("utils.helpers._load_user_from_db_async", AsyncMock(return_value={"weekly_retrospective": 0})):
        val = await helpers.get_user_weekly_retrospective("123")
        assert val == 0
