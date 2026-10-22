"""
tests/test_project_permissions.py — Unit tests for Category 8: Granular Project Role Permissions
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from collaboration import service as collab_service
from collaboration.models import (
    DEFAULT_ROLE_PERMISSIONS,
    PROJECT_PERMISSIONS,
    Project,
    ProjectTask,
)
from collaboration.service import ProjectPermissionError


def _make_project(
    project_id: int = 10,
    guild_id: str = "g1",
    name: str = "Permission Test Proj",
    owner_id: str = "u_owner",
) -> Project:
    now = datetime.now(timezone.utc)
    return Project(
        project_id=project_id,
        guild_id=guild_id,
        name=name,
        description="Testing permissions",
        owner_id=owner_id,
        status="active",
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
    owner_id: str = "u_creator",
) -> ProjectTask:
    now = datetime.now(timezone.utc)
    return ProjectTask(
        task_id=task_id,
        project_id=project_id,
        guild_id=guild_id,
        task="Test Task",
        status="Pending",
        priority=2,
        deadline=None,
        owner_id=owner_id,
        description=None,
        tags=None,
        created_at=now,
        updated_at=now,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Permission Matrix & Defaults Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_default_role_permissions():
    assert len(PROJECT_PERMISSIONS) == 5
    for perm in PROJECT_PERMISSIONS:
        # Lead has full access
        assert DEFAULT_ROLE_PERMISSIONS["lead"][perm] is True
        # Viewer has no write access
        assert DEFAULT_ROLE_PERMISSIONS["viewer"][perm] is False

    # Member default permissions
    assert DEFAULT_ROLE_PERMISSIONS["member"]["can_create_tasks"] is True
    assert DEFAULT_ROLE_PERMISSIONS["member"]["can_change_deadline"] is True
    assert DEFAULT_ROLE_PERMISSIONS["member"]["can_assign_tasks"] is True
    assert DEFAULT_ROLE_PERMISSIONS["member"]["can_delete_tasks"] is False
    assert DEFAULT_ROLE_PERMISSIONS["member"]["can_manage_dependencies"] is True


@pytest.mark.asyncio
async def test_get_project_role_permissions_defaults():
    with patch.object(collab_service.db, "fetchall", new=AsyncMock(return_value=[])):
        perms = await collab_service.get_project_role_permissions(project_id=10, role="member")
        assert perms["can_create_tasks"] is True
        assert perms["can_delete_tasks"] is False
        assert perms["can_assign_tasks"] is True


@pytest.mark.asyncio
async def test_get_project_role_permissions_with_db_override():
    fake_rows = [
        {"permission": "can_delete_tasks", "is_allowed": True},
        {"permission": "can_assign_tasks", "is_allowed": False},
    ]
    with patch.object(collab_service.db, "fetchall", new=AsyncMock(return_value=fake_rows)):
        perms = await collab_service.get_project_role_permissions(project_id=10, role="member")
        # Overridden
        assert perms["can_delete_tasks"] is True
        assert perms["can_assign_tasks"] is False
        # Unchanged from default
        assert perms["can_create_tasks"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 2. Permission Checking (check_project_permission)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_project_permission_admin_and_owner():
    # Guild admin always True
    assert await collab_service.check_project_permission(
        project_id=10, user_id="u_admin", permission="can_delete_tasks", is_guild_admin=True
    ) is True

    # Project owner always True
    with patch.object(collab_service.db, "fetchone", new=AsyncMock(return_value={"owner_id": "u_owner"})):
        assert await collab_service.check_project_permission(
            project_id=10, user_id="u_owner", permission="can_delete_tasks"
        ) is True


@pytest.mark.asyncio
async def test_check_project_permission_non_member_denied():
    with patch.object(collab_service.db, "fetchone", new=AsyncMock(return_value={"owner_id": "u_owner"})), \
         patch("collaboration.service.get_member_role", new=AsyncMock(return_value=None)):

        allowed = await collab_service.check_project_permission(
            project_id=10, user_id="u_stranger", permission="can_create_tasks"
        )
        assert allowed is False


@pytest.mark.asyncio
async def test_check_project_permission_lead_always_true():
    with patch.object(collab_service.db, "fetchone", new=AsyncMock(return_value={"owner_id": "u_owner"})), \
         patch("collaboration.service.get_member_role", new=AsyncMock(return_value="lead")):

        allowed = await collab_service.check_project_permission(
            project_id=10, user_id="u_lead", permission="can_delete_tasks"
        )
        assert allowed is True


@pytest.mark.asyncio
async def test_check_project_permission_member_custom_override():
    with patch.object(collab_service.db, "fetchone", new=AsyncMock(side_effect=[
        {"owner_id": "u_owner"},  # owner check
        {"is_allowed": True},     # custom permission row in project_role_permissions
    ])), patch("collaboration.service.get_member_role", new=AsyncMock(return_value="member")):

        # Member now has can_delete_tasks allowed via DB override
        allowed = await collab_service.check_project_permission(
            project_id=10, user_id="u_member", permission="can_delete_tasks"
        )
        assert allowed is True


# ─────────────────────────────────────────────────────────────────────────────
# 3. Setting Project Role Permissions (set_project_role_permission)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_permission_lead_immutable():
    with pytest.raises(ValueError, match="Cannot customize permissions for role 'lead'"):
        await collab_service.set_project_role_permission(
            project_id=10, guild_id="g1", role="lead", permission="can_delete_tasks",
            is_allowed=False, actor_id="u_owner"
        )


@pytest.mark.asyncio
async def test_set_permission_invalid_permission_name():
    with pytest.raises(ValueError, match="Unknown project permission"):
        await collab_service.set_project_role_permission(
            project_id=10, guild_id="g1", role="member", permission="super_admin_delete_all",
            is_allowed=True, actor_id="u_owner"
        )


@pytest.mark.asyncio
async def test_set_permission_member_success():
    fake_project = _make_project(project_id=10, guild_id="g1", owner_id="u_owner")
    with patch("collaboration.service.get_project", new=AsyncMock(return_value=fake_project)), \
         patch("collaboration.service.require_role", new=AsyncMock()), \
         patch.object(collab_service.db, "execute", new=AsyncMock()) as mock_exec, \
         patch("collaboration.service.log_activity", new=AsyncMock()):

        await collab_service.set_project_role_permission(
            project_id=10,
            guild_id="g1",
            role="member",
            permission="can_delete_tasks",
            is_allowed=True,
            actor_id="u_owner",
        )
        mock_exec.assert_called_once()
        sql = mock_exec.call_args[0][0]
        assert "INSERT INTO project_role_permissions" in sql
        assert "ON CONFLICT (project_id, role, permission) DO UPDATE" in sql


# ─────────────────────────────────────────────────────────────────────────────
# 4. Action Enforcements
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_project_task_rejected_when_can_create_tasks_denied():
    fake_project = _make_project(project_id=10, guild_id="g1", owner_id="u_owner")
    with patch("collaboration.service.get_project", new=AsyncMock(return_value=fake_project)), \
         patch("collaboration.service.check_project_permission", new=AsyncMock(return_value=False)):

        with pytest.raises(ProjectPermissionError):
            await collab_service.add_project_task(
                project_id=10, guild_id="g1", creator_id="u_viewer", task_name="Unauthorized Task",
                deadline_iso=None
            )


@pytest.mark.asyncio
async def test_assign_task_role_rejected_when_can_assign_tasks_denied():
    fake_project = _make_project(project_id=10, guild_id="g1", owner_id="u_owner")
    with patch("collaboration.service.get_project", new=AsyncMock(return_value=fake_project)), \
         patch("collaboration.service.require_role", new=AsyncMock()), \
         patch("collaboration.service.check_project_permission", new=AsyncMock(return_value=False)):

        with pytest.raises(ProjectPermissionError):
            await collab_service.assign_task_role(
                task_id=101, project_id=10, guild_id="g1", role_id=999, actor_id="u_restricted"
            )


@pytest.mark.asyncio
async def test_add_task_dependency_rejected_when_can_manage_dependencies_denied():
    fake_project = _make_project(project_id=10, guild_id="g1", owner_id="u_owner")
    fake_task1 = _make_project_task(task_id=101, project_id=10, guild_id="g1")
    fake_task2 = _make_project_task(task_id=102, project_id=10, guild_id="g1")
    with patch("collaboration.service.get_project", new=AsyncMock(return_value=fake_project)), \
         patch("collaboration.service.require_role", new=AsyncMock()), \
         patch("collaboration.service.get_project_task", new=AsyncMock(side_effect=[fake_task1, fake_task2])), \
         patch("collaboration.service.check_project_permission", new=AsyncMock(return_value=False)):

        with pytest.raises(ProjectPermissionError):
            await collab_service.add_task_dependency(
                task_id=101, blocked_by_task_id=102, project_id=10, guild_id="g1", actor_id="u_viewer"
            )


@pytest.mark.asyncio
async def test_delete_project_task_rejected_when_can_delete_tasks_denied_and_not_creator():
    fake_project = _make_project(project_id=10, guild_id="g1", owner_id="u_owner")
    fake_task = _make_project_task(task_id=101, project_id=10, guild_id="g1", owner_id="u_creator")

    with patch("collaboration.service.get_project", new=AsyncMock(return_value=fake_project)), \
         patch("collaboration.service.get_project_task", new=AsyncMock(return_value=fake_task)), \
         patch("collaboration.service.check_project_permission", new=AsyncMock(return_value=False)), \
         patch("collaboration.service.require_role", new=AsyncMock(side_effect=ProjectPermissionError("lead"))):

        with pytest.raises(ProjectPermissionError):
            await collab_service.delete_project_task(
                task_id=101, project_id=10, guild_id="g1", actor_id="u_other_member"
            )
