"""
tests/test_weekly_retrospective.py — Unit tests for Category 10: Weekly Retrospective Self-Digest
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import discord

from history_reporting import service as history_service
from history_reporting.models import WeeklyRetrospectiveData
from history_reporting.views import WeeklyRetrospectiveView
from history_reporting.cog import HistoryReportingCog


# ─────────────────────────────────────────────────────────────────────────────
# 1. Retrospective Calculation & Coaching Tip Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_weekly_retrospective_calculation_and_tips():
    # Freeze reference time to Sunday evening 2026-10-25 20:00:00 UTC
    ref_time = datetime(2026, 10, 25, 20, 0, 0, tzinfo=timezone.utc)

    # 1. Test High Completion Rate (>= 80%)
    comp_events = [
        {"task_id": 1, "task_title": "T1", "priority": 1, "completed_at": ref_time},
        {"task_id": 2, "task_title": "T2", "priority": 2, "completed_at": ref_time},
        {"task_id": 3, "task_title": "T3", "priority": 3, "completed_at": ref_time},
        {"task_id": 4, "task_title": "T4", "priority": 4, "completed_at": ref_time},
    ]
    user_tasks = [
        {"task_id": 5, "task": "Pending T5", "status": "Pending", "priority": 1, "deadline": None, "created_at": ref_time, "category_name": "Work"},
    ]
    # Total = 4 completed + 1 pending = 5. Rate = 80.0%

    with patch("history_reporting.service.get_user_timezone", new=AsyncMock(return_value="UTC")), \
         patch("history_reporting.service.get_user_lang", new=AsyncMock(return_value="en")), \
         patch.object(history_service.db, "afetchall", new=AsyncMock(side_effect=[
             comp_events,  # task_completion_events
             user_tasks,   # user_tasks
             [],           # snooze_rows
         ])):

        data = await history_service.get_weekly_retrospective_data("user_1", ref_time=ref_time)
        assert data.completed_tasks == 4
        assert data.total_tasks == 5
        assert data.completion_rate == 80.0
        assert "Outstanding work!" in data.coaching_tip

    # 2. Test Snooze Bottleneck Analysis
    snooze_rows = [
        {"target_id": "10", "snooze_cnt": 5},
        {"target_id": "11", "snooze_cnt": 3},
    ]
    tasks_with_snoozes = [
        {"task_id": 10, "task": "Write Thesis Chapter", "status": "Pending", "priority": 4, "deadline": None, "category_name": "Study"},
        {"task_id": 11, "task": "File Taxes", "status": "Pending", "priority": 3, "deadline": None, "category_name": "Finance"},
    ]

    with patch("history_reporting.service.get_user_timezone", new=AsyncMock(return_value="UTC")), \
         patch("history_reporting.service.get_user_lang", new=AsyncMock(return_value="en")), \
         patch.object(history_service.db, "afetchall", new=AsyncMock(side_effect=[
             [],                  # comp_events
             [],                  # audit_comps fallback
             tasks_with_snoozes,  # user_tasks
             snooze_rows,         # snooze_rows
         ])):

        data_snooze = await history_service.get_weekly_retrospective_data("user_2", ref_time=ref_time)
        assert data_snooze.snooze_count_total == 8
        assert len(data_snooze.top_snoozed_tasks) == 2
        assert data_snooze.top_snoozed_tasks[0]["name"] == "Write Thesis Chapter"
        assert data_snooze.top_snoozed_tasks[0]["snooze_count"] == 5
        assert "Several tasks were snoozed" in data_snooze.coaching_tip


# ─────────────────────────────────────────────────────────────────────────────
# 2. Send DM & Idempotency Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_weekly_retrospective_dm_idempotency_and_settings():
    bot = MagicMock()
    user_obj = MagicMock()
    user_obj.send = AsyncMock()
    bot.fetch_user = AsyncMock(return_value=user_obj)

    # 1. Skipped when user has weekly_retrospective = 0
    with patch.object(history_service.db, "afetchone", new=AsyncMock(return_value={"weekly_retrospective": 0})):
        res = await history_service.send_weekly_retrospective_dm(bot, "user_disabled")
        assert res is False
        assert not user_obj.send.called

    # 2. Skipped when already sent for this week
    retro_data = WeeklyRetrospectiveData(
        user_id="user_sent",
        start_date=datetime(2026, 10, 19, tzinfo=timezone.utc),
        end_date=datetime(2026, 10, 25, tzinfo=timezone.utc),
        week_str="2026-W42",
        total_tasks=10,
        completed_tasks=8,
        completion_rate=80.0,
        snooze_count_total=1,
    )
    with patch.object(history_service.db, "afetchone", new=AsyncMock(return_value={
        "weekly_retrospective": 1,
        "last_retrospective_date": "2026-W42",
        "lang": "en",
    })):
        res_already = await history_service.send_weekly_retrospective_dm(bot, "user_sent", retro_data=retro_data)
        assert res_already is False
        assert not user_obj.send.called

    # 3. Successful send and DB update
    with patch.object(history_service.db, "afetchone", new=AsyncMock(return_value={
        "weekly_retrospective": 1,
        "last_retrospective_date": "2026-W41",  # previous week
        "lang": "en",
    })), patch.object(history_service.db, "aexecute", new=AsyncMock()) as mock_exec:

        res_ok = await history_service.send_weekly_retrospective_dm(bot, "user_ok", retro_data=retro_data)
        assert res_ok is True
        assert user_obj.send.called
        # Check DB update
        mock_exec.assert_awaited_once_with(
            "UPDATE users SET last_retrospective_date = $1 WHERE user_id = $2",
            ("2026-W42", "user_ok"),
        )


@pytest.mark.asyncio
async def test_send_weekly_retrospective_handles_forbidden_dms():
    bot = MagicMock()
    user_obj = MagicMock()
    user_obj.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "DMs closed"))
    bot.fetch_user = AsyncMock(return_value=user_obj)

    retro_data = WeeklyRetrospectiveData(
        user_id="user_blocked",
        start_date=datetime(2026, 10, 19, tzinfo=timezone.utc),
        end_date=datetime(2026, 10, 25, tzinfo=timezone.utc),
        week_str="2026-W42",
        total_tasks=5,
        completed_tasks=3,
        completion_rate=60.0,
        snooze_count_total=0,
    )
    with patch.object(history_service.db, "afetchone", new=AsyncMock(return_value={
        "weekly_retrospective": 1,
        "last_retrospective_date": None,
        "lang": "en",
    })):
        res = await history_service.send_weekly_retrospective_dm(bot, "user_blocked", retro_data=retro_data)
        assert res is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. View & Cog Slash Command Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_weekly_retrospective_view_toggle_settings():
    view = WeeklyRetrospectiveView(user_id="123", lang="en")
    interaction = MagicMock()
    interaction.user.id = 123
    interaction.response.send_message = AsyncMock()

    with patch.object(history_service.db, "afetchone", new=AsyncMock(return_value={"weekly_retrospective": 1})), \
         patch.object(history_service.db, "aexecute", new=AsyncMock()) as mock_exec, \
         patch.object(history_service.db.user_cache, "invalidate"):

        await view.toggle_settings.callback(interaction)

        # Toggled from 1 to 0
        mock_exec.assert_awaited_once_with(
            "UPDATE users SET weekly_retrospective=$1 WHERE user_id=$2",
            (0, "123"),
        )
        assert interaction.response.send_message.called


@pytest.mark.asyncio
async def test_retrospective_slash_command():
    bot = MagicMock()
    cog = HistoryReportingCog(bot)

    interaction = MagicMock()
    interaction.user.id = 555
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    fake_data = WeeklyRetrospectiveData(
        user_id="555",
        start_date=datetime(2026, 10, 19, tzinfo=timezone.utc),
        end_date=datetime(2026, 10, 25, tzinfo=timezone.utc),
        week_str="2026-W42",
        total_tasks=8,
        completed_tasks=6,
        completion_rate=75.0,
        snooze_count_total=2,
        coaching_tip="Great job!",
    )

    with patch("history_reporting.cog.get_user_lang", new=AsyncMock(return_value="en")), \
         patch("history_reporting.cog.ensure_user", new=AsyncMock()), \
         patch("history_reporting.cog.history_service.get_weekly_retrospective_data", new=AsyncMock(return_value=fake_data)):

        await cog.retrospective_cmd.callback(cog, interaction)

        assert interaction.followup.send.called
        embed = interaction.followup.send.call_args[1]["embed"]
        assert "Weekly Retrospective Digest" in embed.title
        assert "75.0%" in embed.fields[0].value
