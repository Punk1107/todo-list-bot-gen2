"""
tests/test_private_tasks.py — Unit tests for Category 8: Private / Confidential Tasks in Shared Projects
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from collaboration import service as collab_service
from collaboration.models import Project, ProjectTask
from collaboration.service import ProjectPermissionError, TaskNotFound


def _make_project(
    project_id: int = 10,
    guild_id: str = "g1",
    name: str = "Security Audit",
    owner_id: str = "u_lead",
    status: str = "active",
) -> Project:
    now = datetime.now(timezone.utc)
    return Project(
        project_id=project_id,
        guild_id=guild_id,
        name=name,
        description="A test project",
        owner_id=owner_id,
        status=status,
        color="#5865F2",
        emoji="📁",
        channel_id=None,
        role_id=None,
        created_at=now,
        updated_at=now,
    )


def _make_project_task(
    task_id: int = 101,
    project_id: int = 10,
    guild_id: str = "g1",
    task: str = "Pentest",
    owner_id: str = "u_creator",
    is_private: bool = False,
) -> ProjectTask:
    now = datetime.now(timezone.utc)
    return ProjectTask(
        task_id=task_id,
        project_id=project_id,
        guild_id=guild_id,
        task=task,
        status="Pending",
        priority=2,
        deadline=None,
        owner_id=owner_id,
        description=None,
        tags=None,
        created_at=now,
        updated_at=now,
        is_private=is_private,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. RLS Policy SQL & Matrix Simulation Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_rls_sql_contains_is_private_rule():
    sql_path = Path("security_rls/sql/02_rls_tasks.sql")
    assert sql_path.exists()
    content = sql_path.read_text(encoding="utf-8")
    assert "NOT COALESCE(is_private, FALSE)" in content
    assert "get_project_role(project_id, current_app_user()) = 'lead'" in content


class TestPrivateTaskMatrix:
    """Simulates the RLS policy evaluation logic for private tasks."""

    @staticmethod
    def can_view_group_task(task: dict, actor: str, is_member: bool, role: str) -> bool:
        if not is_member:
            return False
        is_priv = task.get("is_private", False)
        if not is_priv:
            return True
        return task.get("owner_id") == actor or role == "lead"

    def test_matrix_non_private_task(self):
        task = {"task_id": 1, "owner_id": "alice", "project_id": 10, "is_private": False}
        assert self.can_view_group_task(task, actor="alice", is_member=True, role="member")
        assert self.can_view_group_task(task, actor="bob", is_member=True, role="member")
        assert self.can_view_group_task(task, actor="charlie", is_member=True, role="lead")
        assert not self.can_view_group_task(task, actor="stranger", is_member=False, role="viewer")

    def test_matrix_private_task(self):
        task = {"task_id": 2, "owner_id": "alice", "project_id": 10, "is_private": True}
        # Creator can view
        assert self.can_view_group_task(task, actor="alice", is_member=True, role="member")
        # Lead can view
        assert self.can_view_group_task(task, actor="boss", is_member=True, role="lead")
        # Other member cannot view
        assert not self.can_view_group_task(task, actor="bob", is_member=True, role="member")
        # Stranger cannot view
        assert not self.can_view_group_task(task, actor="stranger", is_member=False, role="viewer")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Add Project Task with Privacy
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_project_task_with_privacy():
    fake_project = _make_project(project_id=10, guild_id="g1", owner_id="u_lead")
    fake_record = {
        "task_id": 101,
        "project_id": 10,
        "guild_id": "g1",
        "task": "Confidential pentest finding",
        "status": "Pending",
        "priority": 4,
        "deadline": None,
        "owner_id": "u_auditor",
        "description": "Exploit details",
        "tags": "security,private",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "is_private": True,
    }

    with patch("collaboration.service.get_project", new=AsyncMock(return_value=fake_project)), \
         patch("collaboration.service.require_project_permission", new=AsyncMock()), \
         patch("utils.helpers.ensure_user", new=AsyncMock()), \
         patch.object(collab_service.db, "fetchone", new=AsyncMock(return_value=fake_record)), \
         patch("collaboration.service.log_activity", new=AsyncMock()):

        task = await collab_service.add_project_task(
            project_id=10,
            guild_id="g1",
            creator_id="u_auditor",
            task_name="Confidential pentest finding",
            deadline_iso=None,
            is_private=True,
        )
        assert task.task_id == 101
        assert task.is_private is True
        assert task.owner_id == "u_auditor"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Get Project Task Privacy Checks
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_project_task_private_by_creator_allowed():
    fake_record = {
        "task_id": 101,
        "project_id": 10,
        "guild_id": "g1",
        "task": "Private task",
        "status": "Pending",
        "priority": 1,
        "deadline": None,
        "owner_id": "u_creator",
        "is_private": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    with patch.object(collab_service.db, "fetchone", new=AsyncMock(return_value=fake_record)), \
         patch("collaboration.service._get_task_assignees", new=AsyncMock(return_value=[])):

        task = await collab_service.get_project_task(
            task_id=101, project_id=10, guild_id="g1", actor_id="u_creator"
        )
        assert task.task_id == 101
        assert task.is_private is True


@pytest.mark.asyncio
async def test_get_project_task_private_by_lead_allowed():
    fake_record = {
        "task_id": 101,
        "project_id": 10,
        "guild_id": "g1",
        "task": "Private task",
        "status": "Pending",
        "priority": 1,
        "deadline": None,
        "owner_id": "u_creator",
        "is_private": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    fake_project = _make_project(project_id=10, guild_id="g1", owner_id="u_owner")

    with patch.object(collab_service.db, "fetchone", new=AsyncMock(return_value=fake_record)), \
         patch("collaboration.service.get_project", new=AsyncMock(return_value=fake_project)), \
         patch("collaboration.service.get_member_role", new=AsyncMock(return_value="lead")), \
         patch("collaboration.service._get_task_assignees", new=AsyncMock(return_value=[])):

        task = await collab_service.get_project_task(
            task_id=101, project_id=10, guild_id="g1", actor_id="u_lead"
        )
        assert task.task_id == 101


@pytest.mark.asyncio
async def test_get_project_task_private_by_peer_denied():
    fake_record = {
        "task_id": 101,
        "project_id": 10,
        "guild_id": "g1",
        "task": "Private task",
        "status": "Pending",
        "priority": 1,
        "deadline": None,
        "owner_id": "u_creator",
        "is_private": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    fake_project = _make_project(project_id=10, guild_id="g1", owner_id="u_owner")

    with patch.object(collab_service.db, "fetchone", new=AsyncMock(return_value=fake_record)), \
         patch("collaboration.service.get_project", new=AsyncMock(return_value=fake_project)), \
         patch("collaboration.service.get_member_role", new=AsyncMock(return_value="member")):

        with pytest.raises(ProjectPermissionError):
            await collab_service.get_project_task(
                task_id=101, project_id=10, guild_id="g1", actor_id="u_peer"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Toggle Task Privacy Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_toggle_task_privacy_by_creator():
    fake_project = _make_project(project_id=10, guild_id="g1", owner_id="u_owner")
    fake_task = _make_project_task(task_id=101, project_id=10, guild_id="g1", owner_id="u_creator", is_private=False)
    fake_toggled_task = _make_project_task(task_id=101, project_id=10, guild_id="g1", owner_id="u_creator", is_private=True)

    with patch("collaboration.service.get_project", new=AsyncMock(return_value=fake_project)), \
         patch("collaboration.service.get_project_task", new=AsyncMock(side_effect=[fake_task, fake_toggled_task])), \
         patch.object(collab_service.db, "execute", new=AsyncMock()) as mock_exec, \
         patch("collaboration.service.log_activity", new=AsyncMock()):

        result = await collab_service.toggle_task_privacy(
            task_id=101, project_id=10, guild_id="g1", actor_id="u_creator", is_private=True
        )
        assert result.is_private is True
        mock_exec.assert_called_once()
        assert "is_private=$1" in mock_exec.call_args[0][0]


@pytest.mark.asyncio
async def test_toggle_task_privacy_by_stranger_denied():
    fake_project = _make_project(project_id=10, guild_id="g1", owner_id="u_owner")
    fake_task = _make_project_task(task_id=101, project_id=10, guild_id="g1", owner_id="u_creator", is_private=False)

    with patch("collaboration.service.get_project", new=AsyncMock(return_value=fake_project)), \
         patch("collaboration.service.get_project_task", new=AsyncMock(return_value=fake_task)), \
         patch("collaboration.service.require_role", new=AsyncMock(side_effect=ProjectPermissionError("lead"))):

        with pytest.raises(ProjectPermissionError):
            await collab_service.toggle_task_privacy(
                task_id=101, project_id=10, guild_id="g1", actor_id="u_stranger", is_private=True
            )
