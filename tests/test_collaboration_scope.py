"""
tests/test_collaboration_scope.py — Unit tests for the Shared Projects collaboration system.

Covers:
  1. Data Scope Isolation: Guild A data cannot leak to Guild B
  2. Personal vs Shared Scope: personal tasks are not returned in project queries
  3. Task Claiming / Assignment logic (via mocked DB)
  4. Permission model (ProjectPermissionError raised correctly)
  5. Locale integrity: all collaboration keys present in all supported languages
"""
from __future__ import annotations

import asyncio
import discord
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from collaboration.models import (
    Project, ProjectMember, ProjectTask, ProjectActivity, BoardData,
    ProjectStatus, ProjectRole, SharedTaskStatus,
)
from collaboration import service
from datetime import datetime, timezone


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mock_project(project_id=1, guild_id="guild_A", owner_id="owner_1", status="active") -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "project_id": project_id, "guild_id": guild_id, "name": "Test Project",
        "description": "A test project", "owner_id": owner_id, "status": status,
        "color": "#5865F2", "emoji": "📁", "channel_id": None, "role_id": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }[k]
    row.keys = lambda: ["project_id", "guild_id", "name", "description", "owner_id",
                         "status", "color", "emoji", "channel_id", "role_id",
                         "created_at", "updated_at"]
    return row


def _make_project(project_id=1, guild_id="guild_A", owner_id="owner_1", status="active", name="Test Project") -> Project:
    return Project(
        project_id  = project_id,
        guild_id    = guild_id,
        name        = name,
        description = "A test project",
        owner_id    = owner_id,
        status      = status,
        color       = "#5865F2",
        emoji       = "📁",
        channel_id  = None,
        role_id     = None,
        created_at  = datetime.now(timezone.utc),
        updated_at  = datetime.now(timezone.utc),
    )


def _make_task(task_id=10, project_id=1, guild_id="guild_A", owner_id="owner_1",
               status="Pending", assignees=None) -> ProjectTask:
    return ProjectTask(
        task_id     = task_id,
        project_id  = project_id,
        guild_id    = guild_id,
        task        = "Write tests",
        status      = status,
        priority    = 3,
        deadline    = "2099-12-31T23:59:00+00:00",
        owner_id    = owner_id,
        description = None,
        tags        = None,
        created_at  = datetime.now(timezone.utc),
        updated_at  = datetime.now(timezone.utc),
        assignees   = assignees or [],
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Data Scope Isolation
# ─────────────────────────────────────────────────────────────────────────────

class TestScopeIsolation:
    """Ensure that guild_id is always included in queries (service-level isolation)."""

    @pytest.mark.asyncio
    async def test_get_project_raises_for_wrong_guild(self):
        """get_project with wrong guild_id must raise ProjectNotFound."""
        with patch("collaboration.service.db") as mock_db:
            mock_db.fetchone = AsyncMock(return_value=None)  # DB returns nothing for wrong guild
            with pytest.raises(service.ProjectNotFound):
                await service.get_project(project_id=1, guild_id="guild_B")

    @pytest.mark.asyncio
    async def test_get_project_task_wrong_guild_raises(self):
        """get_project_task must not return tasks from another guild."""
        with patch("collaboration.service.db") as mock_db:
            # DB returns None when guild_id doesn't match
            mock_db.fetchone = AsyncMock(return_value=None)
            with pytest.raises(service.TaskNotFound):
                await service.get_project_task(task_id=10, project_id=1, guild_id="guild_B")

    @pytest.mark.asyncio
    async def test_get_guild_projects_only_own_guild(self):
        """get_guild_projects must return an empty list when guild has no projects."""
        with patch("collaboration.service.db") as mock_db:
            mock_db.fetchall = AsyncMock(return_value=[])
            result = await service.get_guild_projects(guild_id="guild_with_no_projects")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_project_board_wrong_guild_raises(self):
        """get_project_board with wrong guild raises ProjectNotFound (project validation)."""
        with patch("collaboration.service.db") as mock_db:
            mock_db.fetchone = AsyncMock(return_value=None)
            with pytest.raises(service.ProjectNotFound):
                await service.get_project_board(project_id=1, guild_id="guild_B")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Permission Model
# ─────────────────────────────────────────────────────────────────────────────

class TestPermissionModel:
    """Test that require_role raises correctly based on member role."""

    @pytest.mark.asyncio
    async def test_owner_always_passes(self):
        """Project owner always has permission regardless of member role."""
        project = _make_project(owner_id="owner_1")
        # Should not raise — owner passes immediately
        await service.require_role(project, "owner_1", "lead", is_guild_admin=False)

    @pytest.mark.asyncio
    async def test_guild_admin_always_passes(self):
        """Guild admin bypasses all permission checks."""
        project = _make_project(owner_id="owner_1")
        with patch("collaboration.service.get_member_role", AsyncMock(return_value=None)):
            await service.require_role(project, "random_user", "lead", is_guild_admin=True)

    @pytest.mark.asyncio
    async def test_viewer_cannot_perform_member_actions(self):
        """A viewer role should not pass a require_role('member') check."""
        project = _make_project(owner_id="owner_1")
        with patch("collaboration.service.get_member_role", AsyncMock(return_value="viewer")):
            with pytest.raises(service.ProjectPermissionError):
                await service.require_role(project, "viewer_user", "member", is_guild_admin=False)

    @pytest.mark.asyncio
    async def test_member_can_perform_member_actions(self):
        """A member role should pass require_role('member')."""
        project = _make_project(owner_id="owner_1")
        with patch("collaboration.service.get_member_role", AsyncMock(return_value="member")):
            # Should not raise
            await service.require_role(project, "member_user", "member", is_guild_admin=False)

    @pytest.mark.asyncio
    async def test_member_cannot_perform_lead_actions(self):
        """A member role should fail require_role('lead')."""
        project = _make_project(owner_id="owner_1")
        with patch("collaboration.service.get_member_role", AsyncMock(return_value="member")):
            with pytest.raises(service.ProjectPermissionError):
                await service.require_role(project, "member_user", "lead", is_guild_admin=False)

    @pytest.mark.asyncio
    async def test_non_member_fails_all_checks(self):
        """A non-member (None role) should fail all permission checks."""
        project = _make_project(owner_id="owner_1")
        with patch("collaboration.service.get_member_role", AsyncMock(return_value=None)):
            with pytest.raises(service.ProjectPermissionError):
                await service.require_role(project, "outsider", "viewer", is_guild_admin=False)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Claim Logic
# ─────────────────────────────────────────────────────────────────────────────

class TestClaimTask:
    """Test Task Claiming business logic."""

    @pytest.mark.asyncio
    async def test_claim_completed_task_raises(self):
        """Cannot claim a task that is already Completed."""
        completed_task = _make_task(status="Completed")
        project = _make_project()
        with patch("collaboration.service.get_project", AsyncMock(return_value=project)):
            with patch("collaboration.service.get_project_task", AsyncMock(return_value=completed_task)):
                with pytest.raises(ValueError, match="completed or cancelled"):
                    await service.claim_task(10, 1, "guild_A", "user_99")

    @pytest.mark.asyncio
    async def test_claim_cancelled_task_raises(self):
        """Cannot claim a task that is already Cancelled."""
        cancelled_task = _make_task(status="Cancelled")
        project = _make_project()
        with patch("collaboration.service.get_project", AsyncMock(return_value=project)):
            with patch("collaboration.service.get_project_task", AsyncMock(return_value=cancelled_task)):
                with pytest.raises(ValueError, match="completed or cancelled"):
                    await service.claim_task(10, 1, "guild_A", "user_99")

    @pytest.mark.asyncio
    async def test_claim_pending_task_succeeds(self):
        """Claiming a pending task should succeed and return an updated task."""
        pending_task = _make_task(status="Pending")
        claimed_task = _make_task(status="In_Progress", assignees=["claimer_id"])
        project = _make_project()
        with patch("collaboration.service.get_project", AsyncMock(return_value=project)), \
             patch("collaboration.service.get_project_task", AsyncMock(side_effect=[pending_task, claimed_task])), \
             patch("collaboration.service.get_member_role", AsyncMock(return_value="member")), \
             patch("collaboration.service.db") as mock_db, \
             patch("collaboration.service.log_activity", AsyncMock()):
            mock_db.execute     = AsyncMock()
            mock_db.query_cache = MagicMock()
            result = await service.claim_task(10, 1, "guild_A", "claimer_id")
        assert result.status == "In_Progress"
        assert "claimer_id" in result.assignees


# ─────────────────────────────────────────────────────────────────────────────
# 4. Board Data
# ─────────────────────────────────────────────────────────────────────────────

class TestBoardData:
    """Test BoardData model properties."""

    def test_progress_calculation(self):
        project = _make_project()
        board = BoardData(
            project     = project,
            pending     = [_make_task(task_id=1), _make_task(task_id=2)],  # 2 pending
            in_progress = [_make_task(task_id=3)],                         # 1 in progress
            completed   = [_make_task(task_id=4)],                         # 1 done
            cancelled   = [],
        )
        # non-cancelled = 4, done = 1 → 25%
        assert board.total        == 4
        assert board.done_count   == 1
        assert board.progress_pct == 25.0

    def test_progress_ignores_cancelled(self):
        project = _make_project()
        board = BoardData(
            project     = project,
            pending     = [],
            in_progress = [],
            completed   = [_make_task(task_id=1), _make_task(task_id=2)],  # 2 done
            cancelled   = [_make_task(task_id=3)],                          # 1 cancelled
        )
        # non-cancelled = 2, done = 2 → 100%
        assert board.progress_pct == 100.0

    def test_empty_board_zero_progress(self):
        project = _make_project()
        board = BoardData(project=project, pending=[], in_progress=[], completed=[], cancelled=[])
        assert board.total        == 0
        assert board.progress_pct == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 5. Models
# ─────────────────────────────────────────────────────────────────────────────

class TestModels:
    """Unit tests for model helper properties."""

    def test_project_status_emoji(self):
        assert _make_project(status="active").status_emoji    == "🟢"
        assert _make_project(status="archived").status_emoji  == "📦"
        assert _make_project(status="completed").status_emoji == "✅"

    def test_task_status_emoji(self):
        assert _make_task(status="Pending").status_emoji     == "📋"
        assert _make_task(status="In_Progress").status_emoji == "⚡"
        assert _make_task(status="Completed").status_emoji   == "✅"
        assert _make_task(status="Cancelled").status_emoji   == "❌"

    def test_member_role_emoji(self):
        m = ProjectMember(project_id=1, user_id="u", role="lead",
                          joined_at=datetime.now(timezone.utc))
        assert m.role_emoji == "👑"

    def test_activity_action_emoji(self):
        a = ProjectActivity(activity_id=1, project_id=1, guild_id="g", user_id="u",
                            action="task_claimed", detail=None,
                            created_at=datetime.now(timezone.utc))
        assert a.action_emoji == "🙋"


# ─────────────────────────────────────────────────────────────────────────────
# 5b. SQL Regression: get_user_assigned_tasks alias fix
# ─────────────────────────────────────────────────────────────────────────────

class TestGetUserAssignedTasksSQL:
    """Regression tests for get_user_assigned_tasks (SQL alias bug fix).

    Previously the query used `pm.project_id` but the projects table was aliased as `p`,
    which caused a DB error. Fixed to `p.project_id AS _proj_id`.
    """

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_rows(self):
        """When the DB returns no rows, get_user_assigned_tasks must return []."""
        mock_db = AsyncMock()
        mock_db.fetchall = AsyncMock(return_value=[])

        with patch("collaboration.service.db", mock_db):
            result = await service.get_user_assigned_tasks("guild_A", "user_1")

        assert result == []

    @pytest.mark.asyncio
    async def test_sql_contains_correct_alias(self):
        """The SQL in get_user_assigned_tasks must use 'p.project_id', not 'pm.project_id'."""
        import inspect, re
        source = inspect.getsource(service.get_user_assigned_tasks)
        # Must contain the corrected alias 'p.project_id AS _proj_id'
        assert "p.project_id AS _proj_id" in source, (
            "SQL alias regression: expected 'p.project_id AS _proj_id' but got something else"
        )
        # Must NOT contain the buggy 'pm.project_id'
        assert "pm.project_id" not in source, (
            "SQL alias regression: 'pm.project_id' still present — alias not fixed"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Add Member, DM Notification & Close Task (Collaboration Features)
# ─────────────────────────────────────────────────────────────────────────────

class TestAddMemberAndCompleteTask:
    """Tests for adding project members, invite DM sending, and task completion permissions."""

    @pytest.mark.asyncio
    async def test_add_member_returns_project(self):
        """add_member must insert into project_members and return the Project object."""
        project = _make_project(project_id=1, owner_id="lead_1")
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        with patch("collaboration.service.get_project", AsyncMock(return_value=project)), \
             patch("collaboration.service.require_role", AsyncMock()), \
             patch("utils.helpers.ensure_user", AsyncMock()), \
             patch("collaboration.service.db", mock_db), \
             patch("collaboration.service.log_activity", AsyncMock()):
            result = await service.add_member(
                project_id=1, guild_id="guild_A",
                target_user_id="user_2", role="member",
                actor_id="lead_1", is_guild_admin=False,
            )
        assert result == project
        mock_db.execute.assert_called_once()
        assert "INSERT INTO project_members" in mock_db.execute.call_args[0][0]

    @pytest.mark.asyncio
    async def test_add_member_requires_lead_or_admin(self):
        """Regular members cannot add other members."""
        project = _make_project(project_id=1, owner_id="owner_1")
        with patch("collaboration.service.get_project", AsyncMock(return_value=project)), \
             patch("collaboration.service.get_member_role", AsyncMock(return_value="member")):
            with pytest.raises(service.ProjectPermissionError):
                await service.add_member(
                    project_id=1, guild_id="guild_A",
                    target_user_id="user_2", role="member",
                    actor_id="member_1", is_guild_admin=False,
                )

    @pytest.mark.asyncio
    async def test_send_project_invite_dm_success(self):
        """send_project_invite_dm sends embed to target user and returns True."""
        project = _make_project(project_id=1, name="Alpha Project")
        target_user = MagicMock()
        target_user.id = 123456
        target_user.send = AsyncMock()
        actor = MagicMock()
        actor.mention = "<@999>"

        with patch("utils.helpers.get_user_lang", AsyncMock(return_value="th")):
            sent = await service.send_project_invite_dm(
                target_user=target_user,
                project=project,
                guild_name="Test Guild",
                actor=actor,
                role="member",
            )
        assert sent is True
        target_user.send.assert_called_once()
        sent_embed = target_user.send.call_args[1]["embed"]
        assert "Alpha Project" in sent_embed.description
        assert "Test Guild" in sent_embed.description

    @pytest.mark.asyncio
    async def test_send_project_invite_dm_forbidden(self):
        """When user has DMs disabled (discord.Forbidden), gracefully return False."""
        project = _make_project(project_id=1, name="Alpha Project")
        target_user = MagicMock()
        target_user.id = 123456
        mock_response = MagicMock()
        mock_response.status = 403
        mock_response.reason = "Forbidden"
        target_user.send = AsyncMock(side_effect=discord.Forbidden(mock_response, "Cannot send messages to this user"))
        actor = MagicMock()
        actor.mention = "<@999>"

        with patch("utils.helpers.get_user_lang", AsyncMock(return_value="en")):
            sent = await service.send_project_invite_dm(
                target_user=target_user,
                project=project,
                guild_name="Test Guild",
                actor=actor,
                role="member",
            )
        assert sent is False

    @pytest.mark.asyncio
    async def test_update_task_status_completed_by_any_project_member(self):
        """Any user with membership in the project can mark tasks as Completed."""
        project = _make_project(project_id=1, owner_id="owner_1")
        pending_task = _make_task(task_id=10, project_id=1, owner_id="owner_1", status="Pending", assignees=[])
        completed_task = _make_task(task_id=10, project_id=1, owner_id="owner_1", status="Completed", assignees=[])

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.invalidate_stats = MagicMock()
        mock_db.query_cache = MagicMock()

        with patch("collaboration.service.get_project", AsyncMock(return_value=project)), \
             patch("collaboration.service.get_project_task", AsyncMock(side_effect=[pending_task, completed_task])), \
             patch("collaboration.service.get_member_role", AsyncMock(return_value="member")), \
             patch("collaboration.service.db", mock_db), \
             patch("collaboration.service.log_activity", AsyncMock()):
            # member_user is not creator, not assignee, not lead, but is a member
            res = await service.update_task_status(
                task_id=10, project_id=1, guild_id="guild_A",
                new_status="Completed", actor_id="member_user", is_guild_admin=False,
            )
        assert res.status == "Completed"
        mock_db.execute.assert_called_once()
        assert "completed_at=NOW()" in mock_db.execute.call_args[0][0]

    @pytest.mark.asyncio
    async def test_update_task_status_completed_by_non_member_fails(self):
        """Users outside the project (not a member, assignee, creator, or admin) cannot complete tasks."""
        project = _make_project(project_id=1, owner_id="owner_1")
        pending_task = _make_task(task_id=10, project_id=1, owner_id="owner_1", status="Pending", assignees=[])

        with patch("collaboration.service.get_project", AsyncMock(return_value=project)), \
             patch("collaboration.service.get_project_task", AsyncMock(return_value=pending_task)), \
             patch("collaboration.service.get_member_role", AsyncMock(return_value=None)):
            with pytest.raises(service.ProjectPermissionError):
                await service.update_task_status(
                    task_id=10, project_id=1, guild_id="guild_A",
                    new_status="Completed", actor_id="outsider", is_guild_admin=False,
                )

    @pytest.mark.asyncio
    async def test_update_task_status_other_status_requires_specific_roles(self):
        """Transitions other than 'Completed' (e.g. Cancelled) still require assignee, creator, lead, or admin."""
        project = _make_project(project_id=1, owner_id="owner_1")
        pending_task = _make_task(task_id=10, project_id=1, owner_id="owner_1", status="Pending", assignees=["assignee_1"])

        with patch("collaboration.service.get_project", AsyncMock(return_value=project)), \
             patch("collaboration.service.get_project_task", AsyncMock(return_value=pending_task)), \
             patch("collaboration.service.get_member_role", AsyncMock(return_value="member")):
            # random member who is not assignee, not creator, not lead cannot cancel task
            with pytest.raises(service.ProjectPermissionError):
                await service.update_task_status(
                    task_id=10, project_id=1, guild_id="guild_A",
                    new_status="Cancelled", actor_id="member_other", is_guild_admin=False,
                )


# ─────────────────────────────────────────────────────────────────────────────
# 7. Locale Key Integrity — all proj_* keys must exist in all 9 languages
# ─────────────────────────────────────────────────────────────────────────────

class TestLocaleCollaborationKeys:
    """Ensure all new collaboration keys are present in every locale."""

    COLLAB_KEYS = [
        "proj_guild_only", "proj_not_found", "proj_no_permission", "proj_not_active",
        "proj_list_title", "proj_list_empty", "proj_footer",
        "proj_create_modal_title", "proj_name_label", "proj_name_placeholder",
        "proj_desc_label", "proj_desc_placeholder", "proj_color_label", "proj_emoji_label",
        "proj_created_success", "proj_progress", "proj_pending", "proj_in_progress",
        "proj_completed", "proj_cancelled", "proj_overdue", "proj_members",
        "proj_status_label", "proj_leaderboard", "proj_lb_tasks", "proj_footer_id",
        "proj_tasks_done", "proj_board_select_col", "proj_board_empty_col", "proj_board_more",
        "proj_no_claimable", "proj_claim_select_title", "proj_claim_select_desc",
        "proj_claim_select_placeholder", "proj_claimed_title", "proj_claimed_desc",
        "proj_claimed_footer", "proj_task_not_found", "proj_add_task_modal_title",
        "proj_task_added", "proj_members_title", "proj_members_empty", "proj_members_count",
        "proj_activity_title", "proj_activity_empty",
        "proj_my_tasks_title", "proj_my_tasks_empty", "proj_my_tasks_footer",
        "proj_archived_success", "proj_completed_success",
        # Added keys for add-members, DM, and complete-task
        "proj_btn_add_member", "proj_btn_complete_task",
        "proj_add_member_ui_title", "proj_add_member_ui_desc",
        "proj_add_member_select_placeholder", "proj_member_added_title",
        "proj_member_added_desc", "proj_member_dm_title",
        "proj_member_dm_body", "proj_dm_desc_field", "proj_dm_hint_title",
        "proj_member_dm_hint", "proj_member_dm_sent", "proj_member_dm_failed",
        "proj_member_bot_error", "proj_role_lead", "proj_role_member",
        "proj_role_viewer", "proj_complete_select_title",
        "proj_complete_select_desc", "proj_complete_select_placeholder",
        "proj_no_completable", "proj_task_completed_title",
        "proj_task_completed_desc", "proj_task_completed_footer",
        # Added keys for priority and progress controls
        "proj_priority_label", "proj_btn_advance_progress", "proj_btn_complete_project",
        "proj_btn_change_priority", "proj_advance_select_title", "proj_advance_select_desc",
        "proj_advance_select_placeholder", "proj_advance_success", "proj_complete_confirm_title",
        "proj_complete_confirm_desc", "proj_complete_all_btn", "proj_complete_status_only_btn",
        "proj_already_completed", "proj_priority_select_title", "proj_priority_select_desc",
        "proj_priority_select_placeholder", "proj_priority_updated", "proj_manual_progress_desc",
        "proj_manual_progress_modal_title", "proj_manual_progress_input_label",
        "proj_manual_progress_updated",
    ]

    def test_all_collab_keys_present_in_all_locales(self):
        """Every proj_* key must exist in all 9 supported locale files."""
        import importlib
        from locales.i18n import SUPPORTED_LANGS
        failures = []
        for lang in SUPPORTED_LANGS:
            module = importlib.import_module(f"locales.{lang}")
            strings = module.STRINGS
            for key in self.COLLAB_KEYS:
                if key not in strings:
                    failures.append(f"[{lang}] Missing key: '{key}'")
        assert not failures, "Missing collaboration locale keys:\n" + "\n".join(failures)

    def test_placeholder_variables_consistent_with_en(self):
        """Placeholder variables in collaboration keys must match English in all locales."""
        import importlib
        import re
        from locales.i18n import SUPPORTED_LANGS
        placeholder_re = re.compile(r"\{([a-zA-Z0-9_]+)(?::[^}]*)?\}")
        en_strings = importlib.import_module("locales.en").STRINGS

        failures = []
        for lang in SUPPORTED_LANGS:
            if lang == "en":
                continue
            module = importlib.import_module(f"locales.{lang}")
            strings = module.STRINGS
            for key in self.COLLAB_KEYS:
                en_val   = en_strings.get(key, "")
                lang_val = strings.get(key, "")
                en_vars   = set(placeholder_re.findall(en_val))
                lang_vars = set(placeholder_re.findall(lang_val))
                if en_vars != lang_vars:
                    failures.append(
                        f"[{lang}] Key '{key}': EN={en_vars} vs {lang.upper()}={lang_vars}"
                    )
        assert not failures, "Placeholder mismatch in collaboration keys:\n" + "\n".join(failures)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Project Priority & Progress Controls
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectPriorityAndProgressControls:
    """Unit tests for the new Priority and Progress features."""

    def test_project_priority_emojis(self):
        emojis = ["⬜", "🟦", "🟩", "🟨", "🟧", "🟥", "🔴", "🆘"]
        for p_val, expected_emoji in enumerate(emojis):
            p = _make_project(project_id=1, guild_id="g1", owner_id="u1")
            p.priority = p_val
            assert p.priority_emoji == expected_emoji

        # Fallback for out of range
        p = _make_project(project_id=1, guild_id="g1", owner_id="u1")
        p.priority = 99
        assert p.priority_emoji == "⬜"

    @pytest.mark.asyncio
    async def test_create_project_with_priority(self):
        mock_row = {
            "project_id": 42, "guild_id": "g1", "name": "Priority Proj",
            "description": "Desc", "owner_id": "u1", "status": "active",
            "color": "#5865F2", "emoji": "📁", "channel_id": None, "role_id": None,
            "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
            "priority": 4, "manual_progress": None,
        }
        with patch("core.database.db.fetchone", AsyncMock(return_value=mock_row)) as mock_fetchone, \
             patch("core.database.db.execute", AsyncMock()), \
             patch("collaboration.service.log_activity", AsyncMock()):
            proj = await service.create_project("g1", "Priority Proj", "u1", priority=4)
            assert proj.priority == 4
            assert proj.priority_emoji == "🟧"
            # Verify priority passed to SQL INSERT
            args = mock_fetchone.call_args[0][1]
            assert 4 in args

    @pytest.mark.asyncio
    async def test_update_project_priority_lead_permission(self):
        proj = _make_project(project_id=10, guild_id="g1", owner_id="lead_user")
        proj_updated = _make_project(project_id=10, guild_id="g1", owner_id="lead_user")
        proj_updated.priority = 6

        with patch("collaboration.service.get_project", AsyncMock(side_effect=[proj, proj_updated])), \
             patch("collaboration.service.require_role", AsyncMock()) as mock_req, \
             patch("core.database.db.execute", AsyncMock()), \
             patch("collaboration.service.log_activity", AsyncMock()):
            res = await service.update_project_priority(10, "g1", 6, "lead_user")
            mock_req.assert_awaited_once_with(proj, "lead_user", "lead", False)
            assert res.priority == 6
            assert res.priority_emoji == "🔴"

    @pytest.mark.asyncio
    async def test_update_project_manual_progress(self):
        proj = _make_project(project_id=10, guild_id="g1", owner_id="lead_user")
        with patch("collaboration.service.get_project", AsyncMock(return_value=proj)), \
             patch("collaboration.service.get_member_role", AsyncMock(return_value="member")), \
             patch("core.database.db.execute", AsyncMock()), \
             patch("collaboration.service.log_activity", AsyncMock()):
            res = await service.update_project_manual_progress(10, "g1", 75, "user_1")
            assert res is not None

    @pytest.mark.asyncio
    async def test_complete_project_with_tasks(self):
        proj = _make_project(project_id=10, guild_id="g1", owner_id="lead_user")
        proj_done = _make_project(project_id=10, guild_id="g1", owner_id="lead_user", status="completed")

        with patch("collaboration.service.get_project", AsyncMock(side_effect=[proj, proj_done])), \
             patch("collaboration.service.require_role", AsyncMock()), \
             patch("core.database.db.execute", AsyncMock()) as mock_exec, \
             patch("collaboration.service.log_activity", AsyncMock()):
            res = await service.complete_project_with_tasks(10, "g1", "lead_user", complete_all_tasks=True)
            assert res.status == "completed"
            assert mock_exec.await_count >= 2

    def test_dashboard_view_components(self):
        from collaboration.views import ProjectDashboardView
        view = ProjectDashboardView(1, "g1", "en", None)
        custom_ids = [getattr(c, "custom_id", None) for c in view.children]
        assert "proj_dash_advance" in custom_ids
        assert "proj_dash_complete" in custom_ids
        assert "proj_dash_priority" in custom_ids
        assert "proj_dash_add_task" in custom_ids
        assert "proj_dash_dashboard" in custom_ids
        assert "proj_dash_board" in custom_ids

    @pytest.mark.asyncio
    async def test_project_list_empty_projects_does_not_pass_none_view(self):
        """Ensure /project list does not pass view=None to followup.send when no projects exist."""
        from collaboration.cog import CollaborationCog
        cog = CollaborationCog(bot=MagicMock())
        interaction = AsyncMock()
        interaction.user.id = 12345
        interaction.guild = MagicMock()
        interaction.guild.id = 99999
        interaction.guild.name = "Test Guild"

        with patch("collaboration.cog.get_user_lang", AsyncMock(return_value="en")), \
             patch("collaboration.service.get_guild_projects", AsyncMock(return_value=[])):
            await cog.project_list.callback(cog, interaction, status="active")

        interaction.followup.send.assert_awaited_once()
        kwargs = interaction.followup.send.await_args.kwargs
        assert "embed" in kwargs
        assert "view" not in kwargs

    @pytest.mark.asyncio
    async def test_project_list_with_projects_attaches_view(self):
        """Ensure /project list attaches ProjectListView when projects exist."""
        from collaboration.cog import CollaborationCog
        from collaboration.views import ProjectListView
        cog = CollaborationCog(bot=MagicMock())
        interaction = AsyncMock()
        interaction.user.id = 12345
        interaction.guild = MagicMock()
        interaction.guild.id = 99999
        interaction.guild.name = "Test Guild"

        proj = _make_project(project_id=1, guild_id="99999", owner_id="12345")

        with patch("collaboration.cog.get_user_lang", AsyncMock(return_value="en")), \
             patch("collaboration.service.get_guild_projects", AsyncMock(return_value=[proj])):
            await cog.project_list.callback(cog, interaction, status="active")

        interaction.followup.send.assert_awaited_once()
        kwargs = interaction.followup.send.await_args.kwargs
        assert "embed" in kwargs
        assert "view" in kwargs
        assert isinstance(kwargs["view"], ProjectListView)


# ─────────────────────────────────────────────────────────────────────────────
# 11. Project Completion Notifications (Channel Broadcast & Member DMs)
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectCompletionNotification:
    """Test public channel broadcast and stakeholder DMs upon project completion."""

    @pytest.mark.asyncio
    async def test_get_project_stakeholder_ids(self):
        """Ensure all stakeholders (owner, members, assignees, task creators) are aggregated."""
        with patch("collaboration.service.db") as mock_db:
            mock_db.fetchone = AsyncMock(return_value={"owner_id": "owner_1"})
            mock_db.fetchall = AsyncMock(side_effect=[
                [{"user_id": "member_2"}],
                [{"user_id": "assignee_3"}],
                [{"owner_id": "creator_4"}, {"owner_id": "owner_1"}],
            ])

            stakeholders = await service.get_project_stakeholder_ids(project_id=1, guild_id="guild_A")
            assert stakeholders == {"owner_1", "member_2", "assignee_3", "creator_4"}

    @pytest.mark.asyncio
    async def test_notify_project_completed_broadcasts_and_dms(self):
        """Ensure notify_project_completed broadcasts to channel and DMs all members."""
        bot = MagicMock()
        bot.user.id = 9999
        guild = MagicMock()
        guild.name = "Test Guild"

        actor = MagicMock(spec=discord.Member)
        actor.id = 101
        actor.mention = "<@101>"

        member_user = AsyncMock(spec=discord.Member)
        member_user.id = 102
        member_user.bot = False
        guild.get_member.side_effect = lambda uid: member_user if uid == 102 else actor

        trigger_channel = AsyncMock(spec=discord.TextChannel)
        trigger_channel.id = 8888

        proj = _make_project(project_id=2, guild_id="guild_A", owner_id="101", name="NTU Activity")

        with patch("collaboration.service.get_project_stakeholder_ids", AsyncMock(return_value={"101", "102"})), \
             patch("collaboration.service.get_user_lang", AsyncMock(return_value="th")), \
             patch("collaboration.service.db.fetchone", AsyncMock(return_value=None)):

            await service.notify_project_completed(
                bot=bot,
                project=proj,
                actor=actor,
                guild=guild,
                trigger_channel=trigger_channel,
                complete_all_tasks=True,
            )

        # 1. Trigger channel received the celebratory broadcast
        trigger_channel.send.assert_awaited_once()
        sent_embed = trigger_channel.send.await_args.kwargs["embed"]
        assert "โปรเจกต์เสร็จสิ้นแล้ว" in sent_embed.title or "Project Completed" in sent_embed.title

        # 2. Member DMs attempted
        assert member_user.send.await_count == 1
        dm_embed = member_user.send.await_args.kwargs["embed"]
        assert "NTU Activity" in dm_embed.title

    @pytest.mark.asyncio
    async def test_notify_project_completed_forbidden_dm_handled(self):
        """Ensure discord.Forbidden on DMs does not stop notification to other members or raise."""
        bot = MagicMock()
        bot.user.id = 9999
        guild = MagicMock()
        guild.name = "Test Guild"

        actor = MagicMock(spec=discord.Member)
        actor.id = 101
        actor.mention = "<@101>"

        blocked_user = AsyncMock(spec=discord.Member)
        blocked_user.id = 102
        blocked_user.bot = False
        blocked_user.send.side_effect = discord.Forbidden(MagicMock(), "Cannot send messages to this user")

        ok_user = AsyncMock(spec=discord.Member)
        ok_user.id = 103
        ok_user.bot = False

        def get_mem(uid):
            if uid == 102:
                return blocked_user
            if uid == 103:
                return ok_user
            return actor

        guild.get_member.side_effect = get_mem
        trigger_channel = AsyncMock()
        trigger_channel.id = 8888

        proj = _make_project(project_id=2, guild_id="guild_A", owner_id="101", name="NTU Activity")

        with patch("collaboration.service.get_project_stakeholder_ids", AsyncMock(return_value={"102", "103"})), \
             patch("collaboration.service.get_user_lang", AsyncMock(return_value="en")), \
             patch("collaboration.service.db.fetchone", AsyncMock(return_value=None)):

            # Must not raise
            await service.notify_project_completed(
                bot=bot,
                project=proj,
                actor=actor,
                guild=guild,
                trigger_channel=trigger_channel,
                complete_all_tasks=False,
            )

        assert blocked_user.send.await_count == 1
        assert ok_user.send.await_count == 1

    @pytest.mark.asyncio
    async def test_view_triggers_notify_project_completed(self):
        """Ensure ProjectCompleteConfirmView spawns notify_project_completed."""
        from collaboration.views import ProjectCompleteConfirmView

        proj = _make_project(project_id=2, guild_id="guild_A", owner_id="101", name="NTU Activity")
        view = ProjectCompleteConfirmView(project_id=2, guild_id="guild_A", lang="th", project=proj)

        interaction = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.id = 101
        interaction.guild = MagicMock()
        interaction.channel = MagicMock()
        interaction.channel.id = 8888

        with patch("collaboration.service.complete_project_with_tasks", AsyncMock()), \
             patch("collaboration.service.notify_project_completed", AsyncMock()) as mock_notify:

            await view.btn_complete_all.callback(interaction)

            mock_notify.assert_called_once()
            _, kwargs = mock_notify.call_args
            assert kwargs["complete_all_tasks"] is True
            assert kwargs["project"] == proj

    @pytest.mark.asyncio
    async def test_view_complete_only_triggers_notify(self):
        """Ensure ProjectCompleteConfirmView btn_complete_only triggers notify with complete_all_tasks=False."""
        from collaboration.views import ProjectCompleteConfirmView

        proj = _make_project(project_id=2, guild_id="guild_A", owner_id="101", name="NTU Activity")
        view = ProjectCompleteConfirmView(project_id=2, guild_id="guild_A", lang="th", project=proj)

        interaction = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.id = 101
        interaction.guild = MagicMock()
        interaction.channel = MagicMock()
        interaction.channel.id = 8888

        with patch("collaboration.service.complete_project_with_tasks", AsyncMock()), \
             patch("collaboration.service.notify_project_completed", AsyncMock()) as mock_notify:

            await view.btn_complete_only.callback(interaction)

            mock_notify.assert_called_once()
            _, kwargs = mock_notify.call_args
            assert kwargs["complete_all_tasks"] is False
            assert kwargs["project"] == proj

    @pytest.mark.asyncio
    async def test_project_archive_completed_triggers_notify(self):
        """Ensure /project archive action:completed dispatches notify_project_completed."""
        from collaboration.cog import CollaborationCog

        cog = CollaborationCog(bot=MagicMock())
        proj = _make_project(project_id=2, guild_id="guild_A", owner_id="101", name="NTU Activity")

        interaction = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.id = 101
        interaction.guild = MagicMock()
        interaction.guild.id = 9999
        interaction.channel = MagicMock()

        with patch("collaboration.cog._guild_only", AsyncMock(return_value=True)), \
             patch("collaboration.cog.get_user_lang", AsyncMock(return_value="th")), \
             patch("collaboration.service.update_project_status", AsyncMock(return_value=proj)), \
             patch("collaboration.service.notify_project_completed", AsyncMock()) as mock_notify:

            await cog.project_archive.callback(cog, interaction, project_id=2, action="completed")

            mock_notify.assert_called_once()
            _, kwargs = mock_notify.call_args
            assert kwargs["complete_all_tasks"] is False
            assert kwargs["project"] == proj



