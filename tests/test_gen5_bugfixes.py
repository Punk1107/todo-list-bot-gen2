"""
tests/test_gen5_bugfixes.py — Regression tests for the 5 bug categories fixed during Gen 5.0 hardening:
  1. ensure_user validation (blocks username-as-lang CheckViolationError & cache poisoning + keeps fast path)
  2. IDOR / Cross-guild security checks in StorageCog (/attach, /attachments) & AutomationCog (/sla, /automation)
  3. Soft-delete (is_deleted = FALSE) enforcement across Bulk, Dedup, Automation, Visualization, TaskFeatures, BooleanParser
  4. Double-emoji & prefix deduplication in embed titles/labels
  5. Avoiding duplicate DM echoes when interacting inside DMs + naive/aware datetime normalization
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from core.config import config
from core.database import db
from utils.helpers import (
    build_stats_embed,
    build_task_list_embed,
    ensure_user,
)


class TestEnsureUserValidationAndCache:
    @pytest.mark.asyncio
    async def test_ensure_user_ignores_invalid_lang_like_username(self) -> None:
        uid = "777000111222333"
        db.user_cache.invalidate(uid)
        with patch.object(db, "aexecute", new=AsyncMock()) as mock_exec:
            await ensure_user(uid, "SleeplessUserName")

        mock_exec.assert_awaited_once()
        sql_args = mock_exec.call_args.args[1]
        assert sql_args[2] == config.bot.default_lang
        cached = db.user_cache.get(uid)
        assert cached is not None
        assert cached.lang == config.bot.default_lang
        db.user_cache.invalidate(uid)

    @pytest.mark.asyncio
    async def test_ensure_user_uses_cache_fast_path_even_when_lang_passed(self) -> None:
        uid = "777000111222444"
        db.user_cache.set(uid, lang="th", timezone="Asia/Bangkok", channel_id=None, role="user")
        with patch.object(db, "aexecute", new=AsyncMock()) as mock_exec:
            await ensure_user(uid, "th")

        mock_exec.assert_not_awaited()
        db.user_cache.invalidate(uid)


class TestStorageSecurityAndSoftDelete:
    @pytest.mark.asyncio
    async def test_attachments_rejects_deleted_and_unauthorized_personal_tasks(self) -> None:
        from storage.cog import StorageCog

        cog = StorageCog(MagicMock())
        inter = MagicMock(spec=discord.Interaction)
        inter.user = MagicMock(spec=discord.User, id=999)
        inter.guild = None
        inter.response = MagicMock()
        inter.response.defer = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        with (
            patch("storage.cog.get_user_lang", new=AsyncMock(return_value="en")),
            patch(
                "core.database.db.fetchone",
                new=AsyncMock(
                    return_value={
                        "task_id": 10,
                        "task": "Deleted task",
                        "project_id": None,
                        "guild_id": None,
                        "owner_id": "999",
                        "is_deleted": True,
                    }
                ),
            ),
        ):
            await cog.attachments_list.callback(cog, inter, task_id=10)
            assert "10" in inter.followup.send.call_args.args[0]

        inter.followup.send.reset_mock()
        with (
            patch("storage.cog.get_user_lang", new=AsyncMock(return_value="en")),
            patch(
                "core.database.db.fetchone",
                new=AsyncMock(
                    return_value={
                        "task_id": 11,
                        "task": "Private secret task",
                        "project_id": None,
                        "guild_id": None,
                        "owner_id": "111",
                        "is_deleted": False,
                    }
                ),
            ),
            patch("assignments.service.is_user_assigned_to_task", new=AsyncMock(return_value=False)),
        ):
            await cog.attachments_list.callback(cog, inter, task_id=11)
            assert "permission" in inter.followup.send.call_args.args[0].lower()

    @pytest.mark.asyncio
    async def test_soft_delete_filters_present_in_bulk_dedup_automation_viz_and_features(self) -> None:
        from automation import engine as auto_engine
        from discord_native.bulk_cog import BulkActionsCog
        from heuristics.dedup import find_potential_duplicate
        from search_recommendation.boolean_parser import compile_boolean_query
        from task_features import service as tf_service
        from visualization import service as viz_service

        # 1. Boolean parser has:subtasks filters deleted subtasks
        sql, _ = compile_boolean_query("has:subtasks")
        assert "is_deleted = FALSE" in sql

        # 2. TaskFeatures raises TaskNotFound if deleted
        with patch.object(tf_service.db, "afetchone", new=AsyncMock(return_value=None)) as mock_tf:
            with pytest.raises(tf_service.TaskNotFound):
                await tf_service.get_accessible_task(42, "u1")
            assert "is_deleted=FALSE" in mock_tf.call_args.args[0]

        # 3. Dedup excludes soft-deleted tasks
        with patch.object(db, "fetchall", new=AsyncMock(return_value=[])) as mock_dd:
            await find_potential_duplicate("Launch API", "u1")
            assert "is_deleted = FALSE" in mock_dd.call_args.args[0]

        # 4. Automation escalation & SLA exclude soft-deleted tasks
        with patch.object(auto_engine.db, "fetchall", new=AsyncMock(return_value=[])) as mock_ae:
            await auto_engine.get_escalation_status("g1")
            assert "is_deleted = FALSE" in mock_ae.call_args.args[0]

        # 5. Visualization excludes soft-deleted tasks
        with (
            patch.object(viz_service.db, "fetchone", new=AsyncMock(return_value={"sprint_id": 1, "name": "S1", "total_points": 10})),
            patch.object(viz_service.db, "fetchall", new=AsyncMock(return_value=[])) as mock_viz,
        ):
            await viz_service.get_sprint_burndown_data(1)
            assert "is_deleted = FALSE" in mock_viz.call_args.args[0]

        # 6. Bulk picker excludes soft-deleted tasks
        cog = BulkActionsCog(MagicMock())
        inter = MagicMock()
        inter.user.id = 123
        inter.response.defer = AsyncMock()
        inter.followup.send = AsyncMock()
        with (
            patch("discord_native.bulk_cog.get_user_lang", new=AsyncMock(return_value="en")),
            patch("discord_native.bulk_cog.ensure_user", new=AsyncMock()),
            patch.object(db, "afetchall", new=AsyncMock(return_value=[])) as mock_bulk,
        ):
            await cog._open_picker(inter, "done")
            assert "is_deleted = FALSE" in mock_bulk.call_args.args[0]


class TestDoubleEmojiAndDMFixes:
    @pytest.mark.asyncio
    async def test_no_double_emoji_prefixes_in_embeds(self) -> None:
        from handlers.task_views import _build_overdue_embed_and_view, _build_today_embed_and_view

        list_embed = build_task_list_embed([], 1, 1, "th", "UTC", "รอดำเนินการ")
        assert list_embed.title is not None
        assert "📋 📋" not in list_embed.title

        stats_embed = build_stats_embed({"total": 0, "done": 0, "pending": 0, "overdue": 0, "high_done": 0}, "en", "User")
        assert stats_embed.title is not None
        assert "📊 📊" not in stats_embed.title

        with (
            patch("utils.helpers.get_user_display_mode", new=AsyncMock(return_value="standard")),
            patch.object(db, "afetchall", new=AsyncMock(return_value=[])),
            patch.object(db, "afetchone", new=AsyncMock(return_value={"c": 0})),
        ):
            today_embed, _ = await _build_today_embed_and_view("u1", "th", "Asia/Bangkok")
            assert "📅 📅" not in (today_embed.title or "")

            overdue_embed, _ = await _build_overdue_embed_and_view("u1", "th", "Asia/Bangkok")
            assert "🚨 🚨" not in (overdue_embed.title or "")

    @pytest.mark.asyncio
    async def test_no_duplicate_dm_echo_when_already_in_dm(self) -> None:
        from handlers.task_views import AddTaskModal

        modal = AddTaskModal("en", priority=1)
        modal.task_name._value = "Study Linear Algebra"
        modal.deadline._value = "+2d"
        modal.description._value = ""
        modal.tags._value = ""

        dm_inter = MagicMock(spec=discord.Interaction)
        dm_inter.guild = None
        dm_inter.message = None
        dm_inter.user = MagicMock(id=555)
        dm_inter.response = MagicMock()
        dm_inter.response.send_message = AsyncMock()

        created_row = {
            "task_id": 88,
            "task": "Study Linear Algebra",
            "deadline": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "priority": 1,
            "status": "Pending",
            "owner_id": "555",
            "is_pinned": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        with (
            patch("handlers.task_views.get_user_lang", new=AsyncMock(return_value="en")),
            patch("handlers.task_views.get_user_timezone", new=AsyncMock(return_value="UTC")),
            patch("handlers.task_views.ensure_user", new=AsyncMock()),
            patch("handlers.task_views.check_duplicate_task", new=AsyncMock(return_value=None)),
            patch("handlers.task_views._send_dm", new=AsyncMock()) as mock_send_dm,
            patch.object(db, "afetchone", new=AsyncMock(side_effect=[{"task_id": 88}, created_row])),
            patch.object(db, "alog_action", new=AsyncMock()),
            patch.object(db, "invalidate_stats"),
        ):
            await modal.on_submit(dm_inter)

        mock_send_dm.assert_not_awaited()
