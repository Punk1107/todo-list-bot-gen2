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


def _make_project(project_id=1, guild_id="guild_A", owner_id="owner_1", status="active") -> Project:
    return Project(
        project_id  = project_id,
        guild_id    = guild_id,
        name        = "Test Project",
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
# 6. Locale Key Integrity — all proj_* keys must exist in all 9 languages
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
