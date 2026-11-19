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



# ─────────────────────────────────────────────────────────────────────────────
# Round 2 Bugfix Regression Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRound2ViewAndDatetimeFixes:
    @pytest.mark.asyncio
    async def test_retro_dot_vote_select_stores_lang(self) -> None:
        from agile.models import RetroCard
        from agile.views import RetroDotVoteSelect

        card = RetroCard(retro_id=1, sprint_id=2, column_type="well", content="Great sprint", votes=0)
        sel = RetroDotVoteSelect(2, [card], lang="en")
        assert sel.lang == "en"

    @pytest.mark.asyncio
    async def test_quick_done_no_nameerror_for_pending_signoff(self) -> None:
        from assignments.models import SignoffResult
        from handlers.task_views import _QuickActionButtons

        view = _QuickActionButtons(task_id=55, uid="u1", lang="en", tz_name="UTC", row_data={"task": "Shared Task"})
        inter = MagicMock(spec=discord.Interaction)
        inter.user = MagicMock(id=999, roles=[])
        inter.guild = None
        inter.response = MagicMock()
        inter.response.defer = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        with (
            patch("assignments.service.is_user_assigned_to_task", new=AsyncMock(return_value=True)),
            patch.object(db, "afetchone", new=AsyncMock(return_value={"task": "Shared Task", "status": "Pending", "is_deleted": False})),
            patch("routine_workflows.service.get_pending_checklists", new=AsyncMock(return_value=[])),
            patch("assignments.service.get_assignment_summary", new=AsyncMock(return_value=MagicMock(role_ids=[]))),
            patch(
                "assignments.service.handle_task_completion_attempt",
                new=AsyncMock(return_value=SignoffResult(task_id=55, completed=False, mode="all_signoff", signed_users=["999"], pending_users=["100"])),
            ),
        ):
            await view.quick_done.callback(inter)

        inter.followup.send.assert_awaited_once()
        sent = inter.followup.send.call_args.args[0]
        assert "100" in sent

    @pytest.mark.asyncio
    async def test_agile_cog_poker_start_awaits_service_and_checks_guild(self) -> None:
        from agile import service as agile_service
        from agile.cog import AgileCog
        from collaboration.service import ProjectNotFound

        bot = MagicMock()
        cog = AgileCog(bot)
        inter = MagicMock(spec=discord.Interaction)
        inter.guild = MagicMock(id=777)
        inter.user = MagicMock(id=123)
        inter.response = MagicMock()
        inter.response.defer = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        with (
            patch("agile.cog.get_user_lang", new=AsyncMock(return_value="en")),
            patch("agile.cog.ensure_user", new=AsyncMock()),
            patch.object(db, "fetchone", new=AsyncMock(return_value={"task_id": 12, "task": "Poker Task", "owner_id": "123", "project_id": None, "guild_id": "777"})),
            patch.object(agile_service, "start_poker", new=AsyncMock(return_value=MagicMock(task_id=12, task_title="Poker Task", votes={}, is_revealed=False, voter_count=0, host_id="123"))) as mock_poker,
        ):
            await cog.poker_start.callback(cog, inter, task_id=12)
            mock_poker.assert_awaited_once_with(12, "123", guild_id="777", title="Poker Task")

        # Cross-guild sprint_view blocked
        inter.followup.send.reset_mock()
        with (
            patch("agile.cog.get_user_lang", new=AsyncMock(return_value="en")),
            patch.object(agile_service, "get_sprint", new=AsyncMock(return_value=MagicMock(sprint_id=9, project_id=99))),
            patch("agile.cog.collab_service.get_project", new=AsyncMock(side_effect=ProjectNotFound(99))),
        ):
            await cog.sprint_view.callback(cog, inter, sprint_id=9)
            inter.followup.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_text_deadline_parsed_in_cpm_events_forum_and_roadmap(self) -> None:
        from cpm_roadmap import cpm_engine, roadmap_service
        from collaboration import events_service, forum_service

        past_iso = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        created_naive = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=5)

        # 1. CPM handles TEXT ISO deadlines & naive created_at
        with patch.object(
            db,
            "afetchone",
            new=AsyncMock(return_value={"project_id": 1, "name": "Proj", "created_at": created_naive}),
        ), patch.object(
            db,
            "afetchall",
            new=AsyncMock(
                side_effect=[
                    [{"task_id": 1, "task": "Task A", "status": "Pending", "estimated_hours": None, "deadline": past_iso, "created_at": created_naive}],
                    [],
                ]
            ),
        ):
            res = await cpm_engine.calculate_project_cpm(1)
            assert res.is_at_risk is True
            assert res.critical_path == [1]

        # 2. Roadmap predict_milestone_health fallback uses timedelta instead of int subtraction
        ms_row = {
            "milestone_id": 9,
            "project_id": 1,
            "title": "Alpha",
            "target_date": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=10),
            "status": "active",
            "total_tasks": 2,
            "completed_tasks": 1,
            "total_points": 5,
            "completed_points": 2,
        }
        with (
            patch.object(db, "afetchone", new=AsyncMock(side_effect=[ms_row, None])),
            patch.object(db, "afetchall", new=AsyncMock(return_value=[])),
        ):
            health = await roadmap_service.predict_milestone_health(9)
            assert health.milestone_id == 9

        # 3. Events sync parses TEXT ISO deadlines on P6/P7 tasks without AttributeError
        fake_guild = MagicMock(spec=discord.Guild)
        fake_guild.id = 123
        fake_guild.scheduled_events = []
        fake_guild.create_scheduled_event = AsyncMock(return_value=MagicMock(id=999))
        future_iso = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        with (
            patch.object(db, "fetchone", new=AsyncMock(return_value={"project_id": 1, "name": "Proj", "emoji": "🚀"})),
            patch.object(
                db,
                "fetchall",
                new=AsyncMock(
                    side_effect=[
                        [],
                        [],
                        [{"task_id": 7, "task": "Critical Task", "priority": 7, "deadline": future_iso}],
                    ]
                ),
            ),
            patch.object(db, "execute", new=AsyncMock()),
        ):
            sync_res = await events_service.sync_project_events(1, fake_guild)
            assert sync_res["created"] == 1

        # 4. Forum sync parses TEXT ISO deadlines & includes is_deleted = FALSE
        fake_forum = MagicMock(spec=discord.ForumChannel)
        fake_forum.id = 888
        fake_forum.available_tags = []
        fake_forum.create_tag = AsyncMock(return_value=MagicMock(name="tag"))
        fake_forum.create_thread = AsyncMock(return_value=MagicMock(id=777, jump_url="https://discord.com/t/777"))
        fake_bot = MagicMock()
        fake_bot.get_channel = MagicMock(return_value=fake_forum)
        with (
            patch.object(
                db,
                "fetchone",
                new=AsyncMock(
                    side_effect=[
                        {"project_id": 1, "forum_channel_id": "888", "is_active": True},
                        {"task_id": 1, "task": "Forum Task", "status": "Pending", "priority": 2, "description": "desc", "deadline": future_iso},
                        None,
                    ]
                ),
            ) as mock_forum_fetch,
            patch.object(db, "execute", new=AsyncMock()),
        ):
            url = await forum_service.sync_task_to_forum(1, 1, fake_bot)
            assert url == "https://discord.com/t/777"
            task_sql = mock_forum_fetch.call_args_list[1].args[0]
            assert "is_deleted = FALSE" in task_sql


class TestRound2PermissionsSignoffAndI18n:
    @pytest.mark.asyncio
    async def test_complete_personal_task_allows_assignees(self) -> None:
        from gamification import service as gam_service

        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(
            return_value={
                "task_id": 10,
                "task": "Assigned work",
                "priority": 1,
                "deadline": None,
                "project_id": None,
                "guild_id": None,
                "completed_at": datetime.now(timezone.utc),
                "owner_id": "owner_1",
            }
        )
        mock_conn.execute = AsyncMock()
        mock_conn.transaction = MagicMock(return_value=AsyncMock())
        mock_conn.transaction.return_value.__aenter__ = AsyncMock()
        mock_conn.transaction.return_value.__aexit__ = AsyncMock()

        mock_acquire = MagicMock()
        mock_acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire.return_value.__aexit__ = AsyncMock()

        with (
            patch("gamification.service.db.acquire", mock_acquire),
            patch("gamification.service._record_completion", new=AsyncMock(return_value=[])),
            patch("gamification.service.db.invalidate_stats") as mock_inv,
        ):
            res = await gam_service.complete_personal_task(10, "assignee_2", allow_assigned=True)
            assert res == []
            assert mock_inv.call_count == 2

    @pytest.mark.asyncio
    async def test_cross_guild_admin_escalation_blocked(self) -> None:
        from assignments import service as assign_service
        from collaboration.service import ProjectNotFound
        from routine_workflows import service as routine_service

        # Guild admin in guild B trying to manage someone else's personal task
        with pytest.raises(assign_service.AssignmentPermissionError):
            await assign_service._require_manage_permission(
                {"task_id": 1, "owner_id": "victim", "project_id": None, "guild_id": None},
                actor_id="attacker_admin",
                guild_id="guild_B",
                is_guild_admin=True,
            )

        # Guild admin in guild B trying to apply DoD template to guild A's project task
        with (
            patch.object(db, "afetchone", new=AsyncMock(return_value={"task_id": 2, "owner_id": "victim", "project_id": 99, "guild_id": "guild_A"})),
            patch("collaboration.service.get_project", new=AsyncMock(side_effect=ProjectNotFound(99))),
        ):
            with pytest.raises(PermissionError):
                await routine_service.apply_checklist_template(
                    2, "Code Review DoD", "attacker_admin", guild_id="guild_B", is_guild_admin=True
                )

    @pytest.mark.asyncio
    async def test_kudos_ignores_foreign_guild_task_and_estimation_filters_guild(self) -> None:
        from kudos import service as kudos_service
        from time_tracking import service as tt_service

        now = datetime.now(timezone.utc)
        inserted = {
            "kudos_id": 5,
            "guild_id": "G1",
            "from_user_id": "U1",
            "to_user_id": "U2",
            "task_id": None,
            "reason": "Thanks",
            "points": 30,
            "created_at": now,
        }
        with (
            patch.object(
                db,
                "fetchone",
                side_effect=[
                    {"count": 0},
                    {"task": "Secret Foreign Task", "owner_id": "U999", "guild_id": "G_OTHER"},
                    inserted,
                ],
            ),
            patch("kudos.service.award_exp", new=AsyncMock()),
        ):
            k = await kudos_service.send_kudos("G1", "U1", "U2", "Thanks", task_id=999)
            assert k.task_title is None

        with patch.object(db, "fetchall", new=AsyncMock(return_value=[])) as mock_tt:
            await tt_service.calculate_estimation_accuracy(guild_id="G1")
            assert "t.guild_id" in mock_tt.call_args.args[0]

    @pytest.mark.asyncio
    async def test_automation_and_focus_voice_require_manage_permissions(self) -> None:
        from automation.cog import AutomationCog
        from focus.cog import FocusCog

        bot = MagicMock()
        bot.loop = MagicMock()
        auto_cog = AutomationCog.__new__(AutomationCog)
        auto_cog.bot = bot

        non_admin_member = MagicMock(spec=discord.Member)
        non_admin_member.id = 123
        non_admin_member.guild_permissions = discord.Permissions.none()

        inter = MagicMock(spec=discord.Interaction)
        inter.user = non_admin_member
        inter.guild_id = 111
        inter.guild = MagicMock(id=111)
        inter.response = MagicMock()
        inter.response.send_message = AsyncMock()

        with (
            patch("automation.cog.ensure_user", new=AsyncMock()),
            patch("automation.cog.get_user_lang", new=AsyncMock(return_value="en")),
            patch("automation.cog.engine.create_rule", new=AsyncMock()) as mock_create,
        ):
            choice = MagicMock(value="task_created")
            await auto_cog.auto_create.callback(auto_cog, inter, "Test Rule", choice)
            mock_create.assert_not_awaited()
            inter.response.send_message.assert_awaited_once()

        focus_cog = FocusCog.__new__(FocusCog)
        focus_cog.bot = bot
        inter.response.send_message.reset_mock()
        with (
            patch("focus.cog.ensure_user", new=AsyncMock()),
            patch("focus.cog.get_user_lang", new=AsyncMock(return_value="en")),
            patch("focus.cog.voice_service.bind_voice_room", new=AsyncMock()) as mock_bind,
        ):
            await focus_cog.voice_bind.callback(focus_cog, inter, MagicMock(spec=discord.VoiceChannel, id=55))
            mock_bind.assert_not_awaited()
            inter.response.send_message.assert_awaited_once()

    def test_i18n_placeholders_render_cleanly(self) -> None:
        from locales.i18n import t

        for lang in ("th", "en"):
            ev_msg = t("proj_events_synced", lang, count=3, project_id=1, created=2, updated=1)
            assert "{count}" not in ev_msg
            fm_msg = t("proj_forum_mode_enabled", lang, forum="<#123>", project_id=1, tag_count=4)
            assert "{forum}" not in fm_msg
            err_msg = t("err_input_invalid", lang, detail="0-100")
            assert "{detail}" not in err_msg
