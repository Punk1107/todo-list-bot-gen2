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


# ─────────────────────────────────────────────────────────────────────────────
# Round 3 Bugfix Regression Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRound3SchemaEmbedAndSecurityFixes:
    @pytest.mark.asyncio
    async def test_sprints_table_and_completed_points_aggregation_in_viz_and_routine(self) -> None:
        from visualization import service as viz_service

        now_utc = datetime.now(timezone.utc)
        # Real DB sprint row has no total_points or completed_points column
        sprint_row = {
            "sprint_id": 7,
            "name": "Sprint 7",
            "start_date": now_utc - timedelta(days=2),
            "end_date": now_utc + timedelta(days=5),
            "status": "active",
        }
        tasks = [
            {"task_id": 1, "status": "Completed", "story_points": 8},
            {"task_id": 2, "status": "Pending", "story_points": 12},
        ]
        with (
            patch.object(viz_service.db, "fetchone", new=AsyncMock(return_value=sprint_row)) as mock_one,
            patch.object(viz_service.db, "fetchall", new=AsyncMock(return_value=tasks)),
        ):
            data = await viz_service.get_sprint_burndown_data(7)
            assert data is not None
            assert "FROM sprints" in mock_one.call_args.args[0]
            assert "project_sprints" not in mock_one.call_args.args[0]
            assert data["total_points"] == 20.0
            # Remaining points on latest day should reflect 20 - 8 = 12
            assert data["actual_burn"][-1] == 12.0

            cfd = await viz_service.get_sprint_cfd_data(7)
            assert cfd is not None
            assert "FROM sprints" in mock_one.call_args.args[0]

        with (
            patch.object(viz_service.db, "fetchone", new=AsyncMock(return_value={"name": "P1"})),
            patch.object(viz_service.db, "fetchall", new=AsyncMock(return_value=[])) as mock_vel,
        ):
            await viz_service.get_project_velocity_history(1)
            sql_vel = mock_vel.call_args.args[0]
            assert "FROM sprints" in sql_vel
            assert "project_sprints" not in sql_vel
            assert "story_points" in sql_vel

    @pytest.mark.asyncio
    async def test_privacy_delete_my_data_uses_saved_filters_owner_id(self) -> None:
        from privacy import service as privacy_service

        executed_sqls: list[str] = []

        async def _capture_exec(sql: str, params=()):
            executed_sqls.append(sql)
            return "DELETE 1"

        with (
            patch.object(privacy_service.db, "afetchall", new=AsyncMock(return_value=[])),
            patch.object(privacy_service.db, "afetchone", new=AsyncMock(return_value={"user_id": "u1"})),
            patch.object(privacy_service.db, "aexecute", side_effect=_capture_exec),
            patch.object(privacy_service.db, "alog_action", new=AsyncMock()),
            patch.object(privacy_service.db, "invalidate_stats"),
            patch.object(privacy_service.db.user_cache, "invalidate"),
            patch.object(privacy_service.db.query_cache, "invalidate_all"),
        ):
            await privacy_service.execute_gdpr_deletion("u1")

        saved_filter_deletes = [s for s in executed_sqls if "saved_filters" in s]
        assert saved_filter_deletes == ["DELETE FROM saved_filters WHERE owner_id=$1"]

    def test_build_search_embed_non_empty_field_name_and_chunks_over_1024_chars(self) -> None:
        from search_recommendation.models import SearchResult, SearchResultPage, SortBy
        from search_recommendation.views import build_search_embed

        items = [
            SearchResult(
                task_id=i,
                task="A" * 55,
                deadline="2099-12-31T23:59:00+00:00",
                priority=5,
                status="Pending",
                tags=None,
                description=None,
                note=None,
                owner_id="u1",
                guild_id=None,
                project_id=None,
                is_pinned=1,
                created_at=None,
                updated_at=None,
                completed_at=None,
                rank_score=0.95,
                snippet="B" * 70,
            )
            for i in range(1, 20)
        ]
        page = SearchResultPage(
            items=items,
            total=19,
            page=1,
            page_size=20,
            total_pages=1,
            query_text="test",
            sort_by=SortBy.RELEVANCE,
        )
        embed = build_search_embed(page, "en", "UTC")
        assert len(embed.fields) >= 2
        for f in embed.fields:
            assert len(f.name) >= 1
            assert len(f.value) <= 1024

    def test_query_builder_filters_private_tasks_in_guild_scope(self) -> None:
        from search_recommendation.models import SearchFilter, SortBy
        from search_recommendation.query_builder import SqlQueryBuilder

        qb = SqlQueryBuilder()
        sql_search, _ = qb.build_filter_query(
            search_filter=SearchFilter(guild_id="g1"),
            sort_by=SortBy.RELEVANCE,
            page=1,
            page_size=10,
        )
        assert "COALESCE(t.is_private, FALSE) = FALSE" in sql_search

        sql_rec, params_rec = qb.build_recommendation_candidates_query("u1", "g1", limit=25)
        assert "COALESCE(t.is_private, FALSE) = FALSE" in sql_rec
        assert "u1" in params_rec

    @pytest.mark.asyncio
    async def test_task_action_view_blocks_unauthorized_files_checklist_and_fields(self) -> None:
        from handlers.task_views import TaskActionView

        view = TaskActionView(task_id=99, uid="owner_1", lang="en")
        inter = MagicMock(spec=discord.Interaction)
        inter.user = MagicMock(id=22222)
        inter.guild = None
        inter.response = MagicMock()
        inter.response.defer = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        personal_row = {
            "task_id": 99,
            "task": "Owner Task",
            "owner_id": "owner_1",
            "project_id": None,
            "guild_id": None,
            "is_deleted": False,
        }
        with (
            patch("handlers.task_views.get_user_lang", new=AsyncMock(return_value="en")),
            patch.object(db, "afetchone", new=AsyncMock(return_value=personal_row)),
            patch("assignments.service.is_user_assigned_to_task", new=AsyncMock(return_value=False)),
        ):
            await view.view_checklist.callback(inter)
            assert inter.followup.send.await_count == 1
            inter.followup.send.reset_mock()

            await view.view_files.callback(inter)
            assert inter.followup.send.await_count == 1

    @pytest.mark.asyncio
    async def test_reaction_quick_complete_restricts_to_owner_or_assignee(self) -> None:
        from discord_native.reaction_cog import ReactionCog

        bot = MagicMock()
        bot.user = MagicMock(id=111)
        cog = ReactionCog(bot)

        msg = MagicMock()
        msg.author.id = 111
        embed = discord.Embed(title="Task #42", description="Do work")
        msg.embeds = [embed]
        msg.add_reaction = AsyncMock()

        ch = MagicMock()
        ch.fetch_message = AsyncMock(return_value=msg)
        bot.get_channel.return_value = ch

        payload = MagicMock()
        payload.channel_id = 10
        payload.message_id = 20

        with patch.object(db, "execute", new=AsyncMock(return_value="UPDATE 0")) as mock_exec:
            await cog._handle_quick_complete(payload, "intruder_99")
            sql_called = mock_exec.call_args.args[0]
            assert "OR is_private = FALSE" not in sql_called
            assert "is_deleted = FALSE" in sql_called
            assert "owner_id = $2" in sql_called

    @pytest.mark.asyncio
    async def test_agile_convert_action_items_populates_guild_id_and_uses_sql_now(self) -> None:
        from agile import service as agile_service

        with (
            patch.object(
                agile_service.db,
                "afetchall",
                new=AsyncMock(return_value=[{"content": "Fix flaky CI"}]),
            ),
            patch.object(
                agile_service.db,
                "afetchone",
                new=AsyncMock(return_value={"guild_id": "guild_777"}),
            ),
            patch.object(agile_service.db, "aexecute", new=AsyncMock()) as mock_exec,
            patch.object(agile_service.db, "invalidate_stats"),
            patch.object(agile_service.db.query_cache, "invalidate_table"),
        ):
            count = await agile_service.convert_action_items_to_tasks(1, 10, "u1")
            assert count == 1
            sql_insert, params = mock_exec.call_args.args
            assert "guild_id" in sql_insert
            assert "NOW()" in sql_insert
            assert params == ("Fix flaky CI", 10, "guild_777", "u1")

    @pytest.mark.asyncio
    async def test_recovery_blocks_cross_guild_admin_and_other_users_personal_tasks(self) -> None:
        from recovery import service as recovery_service

        personal_deleted = {
            "task_id": 50,
            "task": "Secret DM Task",
            "owner_id": "victim_1",
            "project_id": None,
            "guild_id": None,
            "parent_task_id": None,
            "is_deleted": True,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
        }
        with patch.object(recovery_service.db, "afetchone", new=AsyncMock(return_value=personal_deleted)):
            ok, key, _ = await recovery_service.restore_task(
                50, "attacker_admin", is_guild_admin=True, guild_id="attacker_guild"
            )
            assert ok is False
            assert key == "permission_denied"

            purged = await recovery_service.hard_delete_trash(
                50, "attacker_admin", is_guild_admin=True, guild_id="attacker_guild"
            )
            assert purged is False


# ─────────────────────────────────────────────────────────────────────────────
# Round 4 (/done Self-Deadlock, Timeout Retry Cap & QuickAction Ownership) Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCommandDoneDeadlockAndResilienceFixes:
    @pytest.mark.asyncio
    async def test_complete_personal_task_awards_exp_only_after_transaction_commits(self) -> None:
        from contextlib import asynccontextmanager
        from gamification import service as gam_service

        in_transaction = False
        exp_called_outside_tx = False

        class _TxTrackedConn:
            @asynccontextmanager
            async def transaction(self):
                nonlocal in_transaction
                in_transaction = True
                try:
                    yield
                finally:
                    in_transaction = False

            async def fetchrow(self, query: str, *params):
                if "UPDATE tasks" in query:
                    return {
                        "task_id": 28,
                        "task": "SPD445 - Business plan report",
                        "priority": 5,
                        "deadline": "2026-12-01T12:00:00+00:00",
                        "project_id": None,
                        "guild_id": "g1",
                        "completed_at": datetime.now(timezone.utc),
                        "owner_id": "u1",
                    }
                if "FROM users WHERE user_id=$1 FOR UPDATE" in query:
                    return {
                        "timezone": "Asia/Bangkok",
                        "streak_days": 3,
                        "streak_last_completion": None,
                        "streak_freeze_tokens": 0,
                        "vacation_until": None,
                    }
                if "INSERT INTO user_achievements" in query:
                    return None
                return None

            async def execute(self, query: str, *params):
                return "UPDATE 1"

            async def fetchval(self, query: str, *params):
                return True

        @asynccontextmanager
        async def _fake_acquire():
            yield _TxTrackedConn()

        async def _check_award_exp(uid: str, exp: int, reason: str = ""):
            nonlocal exp_called_outside_tx
            assert in_transaction is False, "award_exp must NOT run while conn.transaction() holds FOR UPDATE lock!"
            exp_called_outside_tx = True
            return {"exp_awarded": exp, "did_level_up": False}

        async def _check_quest_contrib(gid: str, uid: str):
            assert in_transaction is False, "record_task_contribution must NOT run inside conn.transaction()!"
            return None

        with (
            patch.object(gam_service.db, "acquire", side_effect=_fake_acquire),
            patch.object(gam_service, "award_exp", side_effect=_check_award_exp),
            patch("quests.service.record_task_contribution", side_effect=_check_quest_contrib),
            patch.object(gam_service.db, "invalidate_stats"),
            patch.object(gam_service.db.query_cache, "invalidate_tables"),
        ):
            res = await gam_service.complete_personal_task(28, "u1", allow_assigned=True)
            assert res == []
            assert exp_called_outside_tx is True

    @pytest.mark.asyncio
    async def test_db_execute_caps_timeout_error_retries_and_formats_blank_exc_name(self) -> None:
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(side_effect=TimeoutError())

        class _PoolAcquireCtx:
            async def __aenter__(self):
                return mock_conn

            async def __aexit__(self, exc_type, exc, tb):
                return False

        mock_pool.acquire = MagicMock(return_value=_PoolAcquireCtx())

        assert db._format_exc(TimeoutError()) == "TimeoutError"
        assert db._max_attempts_for_error(TimeoutError()) == 2

        with (
            patch.object(db, "_pool", mock_pool),
            patch.object(db, "_retry_delay", return_value=0.001),
        ):
            with pytest.raises(TimeoutError):
                await db.execute("INSERT INTO users (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING", "u1")

        # Must stop after 2 attempts (1 retry) instead of hanging for 5 attempts (150s)
        assert mock_conn.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_done_command_in_dm_does_not_send_duplicate_dm_and_reuses_summary(self) -> None:
        from assignments.models import AssignmentSummary
        from handlers.tasks_cog import TasksCog

        cog = TasksCog(MagicMock())
        dm_inter = MagicMock(spec=discord.Interaction)
        dm_inter.user = MagicMock(id=777, roles=[])
        dm_inter.guild = None
        dm_inter.response = MagicMock()
        dm_inter.response.defer = AsyncMock()
        dm_inter.followup = MagicMock()
        dm_inter.followup.send = AsyncMock()

        task_row = {
            "task": "SPD445 - Public Health Policy",
            "status": "Pending",
            "owner_id": "777",
            "is_deleted": False,
        }
        fake_summary = AssignmentSummary(task_id=34, assignment_mode="first_wins")

        with (
            patch("handlers.tasks_cog.get_user_lang", new=AsyncMock(return_value="th")),
            patch.object(db, "afetchone", new=AsyncMock(return_value=task_row)),
            patch("routine_workflows.service.get_pending_checklists", new=AsyncMock(return_value=[])),
            patch("assignments.service.get_assignment_summary", new=AsyncMock(return_value=fake_summary)) as mock_sum,
            patch.object(gamification_service := __import__("gamification.service", fromlist=["complete_personal_task"]), "complete_personal_task", new=AsyncMock(return_value=[])),
            patch.object(db, "alog_action", new=AsyncMock()),
            patch("handlers.tasks_cog._send_dm", new=AsyncMock()) as mock_send_dm,
        ):
            await cog.done.callback(cog, dm_inter, task_id=34, force=False)

        # get_assignment_summary called only once (reused by handle_task_completion_attempt)
        assert mock_sum.await_count == 1
        dm_inter.followup.send.assert_awaited_once()
        mock_send_dm.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_quick_action_buttons_prevent_assignee_from_pinning_or_snoozing_owners_task(self) -> None:
        from handlers.task_views import _QuickActionButtons

        view = _QuickActionButtons(
            task_id=88,
            uid="assignee_2",
            lang="en",
            tz_name="UTC",
            row_data={"task": "Shared Task", "owner_id": "owner_1"},
        )
        inter = MagicMock(spec=discord.Interaction)
        inter.user = MagicMock(id="assignee_2")
        inter.response = MagicMock()
        inter.response.defer = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        with (
            patch.object(
                db,
                "afetchone",
                new=AsyncMock(return_value={"owner_id": "owner_1", "is_pinned": 0, "deadline": "2026-12-01T00:00:00+00:00", "is_deleted": False}),
            ),
            patch.object(db, "aexecute", new=AsyncMock()) as mock_exec,
        ):
            await view.quick_pin.callback(inter)
            mock_exec.assert_not_awaited()

            await view.quick_snooze.callback(inter)
            mock_exec.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────────────
# Round 4 System-Wide Audit Bugfix Tests (7 Categories)
# ─────────────────────────────────────────────────────────────────────────────

class TestRound4SystemWideBugfixes:
    @pytest.mark.asyncio
    async def test_janitor_archive_completed_tasks_excludes_generated_search_vector(self) -> None:
        from recovery import janitor

        async def _fake_fetchall(sql: str, params=()):
            if "SELECT task_id FROM tasks" in sql:
                return [{"task_id": 101}]
            if "information_schema.columns" in sql:
                assert "is_generated" in sql
                assert "tasks_archive" in sql
                return [
                    {"column_name": "task_id"},
                    {"column_name": "task"},
                    {"column_name": "search_vector"},
                    {"column_name": "archived_at"},
                ]
            if "DELETE FROM tasks" in sql:
                return [{"task_id": 101}]
            return []

        with (
            patch.object(janitor.db, "afetchall", side_effect=_fake_fetchall),
            patch.object(janitor.db, "aexecute", new=AsyncMock()) as mock_exec,
            patch.object(janitor.db.query_cache, "invalidate_tables"),
        ):
            count = await janitor.archive_completed_tasks(days=90)
            assert count == 1
            insert_sql = mock_exec.call_args_list[0].args[0]
            assert "INSERT INTO tasks_archive (task_id, task, archived_at)" in insert_sql
            assert "search_vector" not in insert_sql

    @pytest.mark.asyncio
    async def test_assign_task_handles_none_wip_limit_without_type_error(self) -> None:
        from collaboration import service as collab_service

        fake_task = MagicMock(
            task_id=55,
            task="Implement OAuth",
            status="Pending",
            project_id=10,
            guild_id="g1",
        )

        with (
            patch.object(collab_service, "get_project", new=AsyncMock(return_value=MagicMock(owner_id="u1"))),
            patch.object(collab_service, "require_role", new=AsyncMock()),
            patch.object(collab_service, "get_project_task", new=AsyncMock(return_value=fake_task)),
            patch.object(collab_service, "_get_incomplete_task_blockers", new=AsyncMock(return_value=[])),
            patch("utils.helpers.ensure_user", new=AsyncMock()),
            patch.object(collab_service, "get_project_wip_limit", new=AsyncMock(return_value=None)),
            patch.object(collab_service.db, "execute", new=AsyncMock()),
            patch.object(collab_service.db, "fetchone", new=AsyncMock(return_value={"estimated_hours": 0})),
            patch.object(collab_service.db.query_cache, "invalidate_tables"),
            patch.object(collab_service, "log_activity", new=AsyncMock()),
            patch("time_tracking.service.check_burnout_shield", new=AsyncMock(return_value={"exceeded": False})),
        ):
            res_task = await collab_service.assign_task(55, 10, "g1", "u2", "u1")
            assert res_task.task_id == 55

    @pytest.mark.asyncio
    async def test_import_tasks_converts_is_pinned_to_int_and_fills_none_deadline(self) -> None:
        from discord import app_commands
        from task_import.cog import TaskImportCog
        from task_import.service import ImportedTask

        cog = TaskImportCog()
        inter = MagicMock(spec=discord.Interaction)
        inter.user = MagicMock(id=12345)
        inter.response = MagicMock()
        inter.response.defer = AsyncMock()
        inter.followup = MagicMock()
        inter.followup.send = AsyncMock()

        attachment = MagicMock(spec=discord.Attachment)
        attachment.size = 120
        attachment.filename = "tasks.csv"
        attachment.read = AsyncMock(return_value=b"task\nSample")

        choice = app_commands.Choice(name="Leave deadline empty", value="no_deadline")
        parsed = [
            ImportedTask(
                task="Sample Task",
                deadline=None,
                priority=3,
                status="Pending",
                recurring="none",
                tags="work",
                description="desc",
                is_pinned=True,
            )
        ]

        with (
            patch("task_import.cog.get_user_lang", new=AsyncMock(return_value="en")),
            patch("task_import.cog.get_user_timezone", new=AsyncMock(return_value="UTC")),
            patch("task_import.cog.parse_import_file", return_value=parsed),
            patch("task_import.cog.ensure_user", new=AsyncMock()),
            patch.object(db, "aexecute_batch", new=AsyncMock()) as mock_batch,
            patch.object(db, "invalidate_stats"),
            patch.object(db, "alog_action", new=AsyncMock()),
        ):
            await cog.import_tasks.callback(cog, inter, attachment, choice)
            mock_batch.assert_awaited_once()
            statements = mock_batch.call_args.args[0]
            _, params = statements[0]
            # params[1] is deadline (must not be None), params[7] is is_pinned (must be int 1, not bool)
            assert isinstance(params[1], str) and len(params[1]) > 0
            assert params[7] == 1 and type(params[7]) is int

    @pytest.mark.asyncio
    async def test_stats_estimation_and_timesheet_enforce_tenant_and_privacy_isolation(self) -> None:
        from handlers.tasks_cog import TasksCog
        from time_tracking import service as tt_service

        cog = TasksCog(MagicMock())
        inter = MagicMock(spec=discord.Interaction)
        inter.user = MagicMock(id=111)
        inter.guild_id = 999
        inter.guild = MagicMock(name="Guild 999")
        inter.response = MagicMock()
        inter.response.send_message = AsyncMock()

        with (
            patch("handlers.tasks_cog.get_user_lang", new=AsyncMock(return_value="en")),
            patch("collaboration.service.get_project", new=AsyncMock()) as mock_get_proj,
            patch("time_tracking.service.calculate_estimation_accuracy", new=AsyncMock(return_value={"total_analyzed": 0})) as mock_calc,
            patch("time_tracking.views.build_estimation_analytics_embed", return_value=discord.Embed(title="Est")),
        ):
            await cog.stats_estimation.callback(cog, inter, project_id=7, member=None)
            mock_get_proj.assert_awaited_once_with(7, "999")
            mock_calc.assert_awaited_once_with(project_id=7, user_id=None, guild_id="999")

        with patch.object(tt_service.db, "fetchall", new=AsyncMock(return_value=[])) as mock_fetchall:
            await tt_service.get_user_timesheet("target_u", period="week", guild_id="999", viewer_id="caller_u")
            sql_called, params_called = mock_fetchall.call_args.args
            assert "t.is_deleted = FALSE" in sql_called
            assert "t.guild_id = $3" in sql_called
            assert "COALESCE(t.is_private, FALSE) = FALSE" in sql_called
            assert params_called[0] == "target_u"
            assert params_called[2] == "999"

    @pytest.mark.asyncio
    async def test_soft_delete_stops_active_time_timers_and_admin_stats_excludes_deleted(self) -> None:
        from recovery import service as recovery_service

        row = {
            "task_id": 44,
            "task": "Timer Task",
            "owner_id": "u1",
            "project_id": None,
            "guild_id": None,
            "is_deleted": False,
        }
        with (
            patch.object(recovery_service.db, "afetchone", new=AsyncMock(return_value=row)),
            patch.object(recovery_service.db, "aexecute", new=AsyncMock()) as mock_exec,
            patch.object(recovery_service.db, "invalidate_stats"),
            patch.object(recovery_service.db.query_cache, "invalidate_tables") as mock_inv,
            patch.object(recovery_service.db, "alog_action", new=AsyncMock()),
        ):
            ok = await recovery_service.soft_delete_task(44, "u1")
            assert ok is True
            executed_sqls = [c.args[0] for c in mock_exec.call_args_list]
            assert any("DELETE FROM active_time_timers" in s for s in executed_sqls)
            mock_inv.assert_called_with(["tasks", "focus_sessions", "active_time_timers"])

    @pytest.mark.asyncio
    async def test_voice_room_loop_normalizes_naive_ends_at_and_standup_uses_utc_date(self) -> None:
        from focus.cog import FocusCog
        from standup import service as standup_service

        bot = MagicMock()
        cog_dummy = MagicMock(bot=bot)

        member = MagicMock(bot=False)
        channel = MagicMock(spec=discord.VoiceChannel)
        channel.members = [member]
        bot.get_channel.return_value = channel

        naive_past = datetime(2020, 1, 1, 0, 0, 0)  # naive datetime
        room_row = {
            "channel_id": "555",
            "current_phase": "work",
            "phase_ends_at": naive_past,
            "break_minutes": 5,
            "work_minutes": 25,
            "current_round": 1,
            "chime_enabled": False,
        }
        with (
            patch("focus.voice_service.get_all_active_voice_rooms", new=AsyncMock(return_value=[room_row])),
            patch("focus.voice_service.update_room_phase", new=AsyncMock()) as mock_update_phase,
            patch("focus.voice_service.update_voice_channel_status", new=AsyncMock()),
        ):
            await FocusCog.voice_room_loop.coro(cog_dummy)
            mock_update_phase.assert_awaited_once()

        with patch.object(standup_service.db, "fetchall", new=AsyncMock(return_value=[])) as mock_fetchall:
            await standup_service.get_daily_standups("g1")
            _, params = mock_fetchall.call_args.args
            assert params[1] == datetime.now(timezone.utc).date()

    @pytest.mark.asyncio
    async def test_retro_convert_disables_button_and_saved_filter_hides_private_tasks(self) -> None:
        from agile.views import RetroBoardView
        from organization import service as org_service
        from organization.models import SavedFilter, SavedFilterCriteria

        view = RetroBoardView(sprint_id=1, project_id=2, lang="en")
        inter = MagicMock(spec=discord.Interaction)
        inter.user = MagicMock(id=101)
        inter.message = MagicMock()
        inter.message.edit = AsyncMock()
        inter.response = MagicMock()
        inter.response.send_message = AsyncMock()

        with patch("agile.service.convert_action_items_to_tasks", new=AsyncMock(return_value=2)):
            await view.btn_convert_actions.callback(inter)
            assert view.btn_convert_actions.disabled is True
            inter.message.edit.assert_awaited_once_with(view=view)

        sf = MagicMock(spec=SavedFilter)
        sf.criteria = SavedFilterCriteria(project_id=10)
        with patch.object(org_service.db, "afetchall", new=AsyncMock(return_value=[])) as mock_fetch:
            await org_service.execute_saved_filter(sf, user_id="u1", guild_id="g1")
            sql_called, params = mock_fetch.call_args.args
            assert "t.guild_id = $2" in sql_called
            assert "COALESCE(t.is_private, FALSE) = FALSE OR t.owner_id = $3" in sql_called
            assert params[:3] == (10, "g1", "u1")


# ─────────────────────────────────────────────────────────────────────────────
# Round 5 System-Wide Audit Bugfix Tests (7 Categories)
# ─────────────────────────────────────────────────────────────────────────────

class TestRound5SystemWideBugfixes:
    @pytest.mark.asyncio
    async def test_reaction_task_capture_sets_non_null_deadline(self) -> None:
        from discord_native.reaction_cog import ReactionCog

        bot = MagicMock()
        bot.user = MagicMock(id=111)
        user_mock = MagicMock()
        user_mock.send = AsyncMock()
        bot.get_user.return_value = user_mock

        msg = MagicMock()
        msg.clean_content = "Fix production webhook timeout"
        msg.attachments = []
        msg.jump_url = "https://discord.com/channels/1/2/3"

        ch = MagicMock(spec=discord.TextChannel)
        ch.fetch_message = AsyncMock(return_value=msg)
        bot.get_channel.return_value = ch

        payload = MagicMock()
        payload.channel_id = 2
        payload.message_id = 3

        cog = ReactionCog(bot)
        with (
            patch("discord_native.reaction_cog.get_user_lang", new=AsyncMock(return_value="en")),
            patch("discord_native.reaction_cog.ensure_user", new=AsyncMock()),
            patch.object(db, "fetchone", new=AsyncMock(return_value={"task_id": 701})) as mock_fetch,
            patch.object(db, "invalidate_stats"),
            patch.object(db.query_cache, "invalidate_table"),
        ):
            await cog._handle_task_capture(payload, "999")
            mock_fetch.assert_awaited_once()
            sql_called, params = mock_fetch.call_args.args
            assert "deadline" in sql_called
            assert isinstance(params[2], str) and len(params[2]) >= 10

    @pytest.mark.asyncio
    async def test_history_blocks_cross_guild_admin_and_hides_private_in_autocomplete(self) -> None:
        from history_reporting import service as history_service
        from history_reporting.cog import _history_task_autocomplete

        personal_row = {
            "task_id": 88,
            "task": "Personal DM Secret",
            "owner_id": "victim_1",
            "status": "Pending",
            "priority": 3,
            "deadline": None,
            "description": "Secret description",
            "is_deleted": False,
            "created_at": datetime.now(timezone.utc),
            "project_id": None,
            "guild_id": None,
            "category_name": "Personal",
        }
        other_guild_row = {
            **personal_row,
            "task_id": 89,
            "guild_id": "guild_victim",
            "project_id": 5,
        }

        with patch.object(history_service.db, "afetchone", new=AsyncMock(return_value=personal_row)):
            assert await history_service.get_task_audit_history(
                88, "attacker_admin", is_guild_admin=True, guild_id="guild_attacker"
            ) is None
            ok, key = await history_service.rollback_task_description(
                88, 1, "attacker_admin", is_guild_admin=True, guild_id="guild_attacker"
            )
            assert ok is False and key == "history_not_found_or_denied"

        with patch.object(history_service.db, "afetchone", new=AsyncMock(return_value=other_guild_row)):
            assert await history_service.get_revision_diff(
                89, "attacker_admin", is_guild_admin=True, guild_id="guild_attacker"
            ) is None

        inter = MagicMock(spec=discord.Interaction)
        inter.user = MagicMock(id=555)
        inter.guild = MagicMock(id=999)
        with patch.object(db, "afetchall", new=AsyncMock(return_value=[])) as mock_ac:
            await _history_task_autocomplete(inter, "")
            sql_called = mock_ac.call_args.args[0]
            assert "COALESCE(is_private, FALSE) = FALSE" in sql_called

    @pytest.mark.asyncio
    async def test_monitoring_setup_rejects_foreign_guild_channel(self) -> None:
        from handlers.monitoring_cog import MonitoringSetupModal

        modal = MonitoringSetupModal()
        modal.log_channel._value = "999888777"
        modal.health_interval._value = ""
        modal.alert_cooldown._value = ""
        modal.monitoring_enabled._value = ""

        foreign_ch = MagicMock(spec=discord.TextChannel)
        foreign_ch.id = 999888777
        foreign_ch.guild = MagicMock(id=222222)  # different guild

        inter = MagicMock(spec=discord.Interaction)
        inter.user = MagicMock(id=101)
        inter.guild_id = 111111
        inter.guild = MagicMock(id=111111)
        inter.guild.get_channel.return_value = None
        inter.client = MagicMock()
        inter.client.fetch_channel = AsyncMock(return_value=foreign_ch)
        inter.response = MagicMock()
        inter.response.send_message = AsyncMock()

        with (
            patch("handlers.monitoring_cog.get_user_lang", new=AsyncMock(return_value="en")),
            patch.object(db, "set_guild_setting", new=AsyncMock()) as mock_set,
        ):
            await modal.on_submit(inter)
            mock_set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dedup_excludes_other_users_private_tasks_and_cancelled_tasks(self) -> None:
        from heuristics.dedup import find_potential_duplicate

        with patch("heuristics.dedup.db.fetchall", new=AsyncMock(return_value=[])) as mock_fetch:
            await find_potential_duplicate("Fix billing", owner_id="u1", guild_id="g1")
            sql_called = mock_fetch.call_args.args[0]
            assert "COALESCE(is_private, FALSE) = FALSE" in sql_called
            assert "Cancelled" in sql_called

    @pytest.mark.asyncio
    async def test_checklist_prevents_exp_farming_and_enforces_user_check(self) -> None:
        from routine_workflows import service as rw_service
        from routine_workflows.models import ChecklistItem
        from routine_workflows.views import TaskChecklistView

        # 1. Toggling an already-awarded checklist item back to done must NOT award EXP again
        toggle_curr = {"task_id": 50, "is_done": False, "already_awarded": True}
        toggle_row = {
            "checklist_id": 9,
            "task_id": 50,
            "title": "Code review",
            "is_done": True,
            "position": 0,
            "created_at": datetime.now(timezone.utc),
            "completed_at": datetime.now(timezone.utc),
        }
        with (
            patch.object(rw_service.db, "afetchone", new=AsyncMock(side_effect=[toggle_curr, toggle_row])),
            patch.object(rw_service, "get_pending_checklist_count", new=AsyncMock(return_value=0)),
            patch.object(rw_service.db, "alog_action", new=AsyncMock()),
            patch("gamification.rpg.award_exp", new=AsyncMock()) as mock_exp,
        ):
            res = await rw_service.toggle_checklist_item(9, "u1")
            assert res is not None
            mock_exp.assert_not_awaited()

        # 2. Stranger cannot toggle checklist items in TaskChecklistView
        items = [ChecklistItem(checklist_id=9, task_id=50, title="Code review", is_done=False, position=0)]
        view = TaskChecklistView(task_id=50, task_name="Task", user_id="owner_1", lang="en", items=items)
        select = next(c for c in view.children if isinstance(c, discord.ui.Select))
        select._values = ["9"]
        inter = MagicMock(spec=discord.Interaction)
        inter.user = MagicMock(id=999999)
        inter.response = MagicMock()
        inter.response.send_message = AsyncMock()
        with patch("routine_workflows.service.toggle_checklist_item", new=AsyncMock()) as mock_toggle:
            await select.callback(inter)
            mock_toggle.assert_not_awaited()
            inter.response.send_message.assert_awaited_once()

    def test_snooze_next_monday_preserves_user_local_time(self) -> None:
        import pytz
        from handlers.task_views import _SnoozePresetSelect

        # 18:30 Asia/Bangkok = 11:30 UTC
        bkk = pytz.timezone("Asia/Bangkok")
        dl_utc = bkk.localize(datetime(2099, 11, 27, 18, 30)).astimezone(pytz.utc)
        sel = _SnoozePresetSelect(1, "u1", "th", dl_utc.isoformat(), "Asia/Bangkok")
        mon_utc = sel._presets["mon"]
        mon_local = mon_utc.astimezone(bkk)
        assert mon_local.weekday() == 0
        assert (mon_local.hour, mon_local.minute) == (18, 30)

    @pytest.mark.asyncio
    async def test_vacation_expired_does_not_shield_forever_and_skips_active_vacation_reminder(self) -> None:
        from datetime import date
        from gamification.vacation import evaluate_streak_update
        from gamification.cog import GamificationCog

        # Expired vacation from Jan 1-3 must NOT shield a completion on July 1
        streak, freeze_used, vac_used, tokens = evaluate_streak_update(
            current_streak=20,
            last_day=date(2026, 1, 1),
            completion_day=date(2026, 7, 1),
            vacation_until=date(2026, 1, 3),
            freeze_tokens=0,
        )
        assert streak == 1
        assert vac_used is False

        # Active vacation should still be skipped by streak_reminder_loop
        now_20 = datetime(2026, 11, 27, 20, 0, tzinfo=timezone.utc)
        row = {
            "user_id": "12345",
            "timezone": "UTC",
            "streak_days": 10,
            "streak_last_completion": date(2026, 11, 26),
            "vacation_until": date(2026, 12, 5),
        }
        bot = MagicMock()
        dummy_cog = MagicMock(bot=bot)
        with (
            patch("gamification.cog.db.afetchall", new=AsyncMock(return_value=[row])),
            patch("gamification.cog.datetime") as mock_dt,
            patch("gamification.cog.service.claim_streak_reminder", new=AsyncMock(return_value=True)) as mock_claim,
        ):
            mock_dt.now.return_value = now_20
            await GamificationCog.streak_reminder_loop.coro(dummy_cog)
            mock_claim.assert_not_awaited()




