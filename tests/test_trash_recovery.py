"""
tests/test_trash_recovery.py — Unit tests for Category 8: Soft Delete & Recycle Bin
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import discord

from recovery import service
from recovery.models import TrashTask
from recovery.cog import RecoveryCog


# ─────────────────────────────────────────────────────────────────────────────
# 1. Model & Calculation Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_trash_task_days_remaining():
    now = datetime.now(timezone.utc)

    # Deleted just now
    task_recent = TrashTask(
        task_id=1,
        task="Recent task",
        owner_id="u1",
        deleted_at=now,
    )
    assert task_recent.days_remaining == 30
    assert not task_recent.is_expired

    # Deleted 10 days ago
    ten_days_ago = now - timedelta(days=10)
    task_10d = TrashTask(
        task_id=2,
        task="10d task",
        owner_id="u1",
        deleted_at=ten_days_ago,
    )
    assert task_10d.days_remaining == 20
    assert not task_10d.is_expired

    # Deleted 31 days ago (expired)
    thirty_one_days_ago = now - timedelta(days=31)
    task_expired = TrashTask(
        task_id=3,
        task="Expired task",
        owner_id="u1",
        deleted_at=thirty_one_days_ago,
    )
    assert task_expired.days_remaining == 0
    assert task_expired.is_expired

    # Deleted_at is None
    task_none = TrashTask(
        task_id=4,
        task="None date task",
        owner_id="u1",
        deleted_at=None,
    )
    assert task_none.days_remaining == 30


def test_trash_task_from_record():
    now = datetime.now(timezone.utc)
    record = {
        "task_id": 101,
        "task": "Test task",
        "description": "Some description",
        "priority": 2,
        "owner_id": "user123",
        "project_id": 42,
        "guild_id": "guild999",
        "deleted_at": now,
        "is_private": True,
        "parent_task_id": 100,
    }
    t = TrashTask.from_record(record)
    assert t.task_id == 101
    assert t.task == "Test task"
    assert t.project_id == 42
    assert t.guild_id == "guild999"
    assert t.is_private is True
    assert t.parent_task_id == 100


# ─────────────────────────────────────────────────────────────────────────────
# 2. Soft Delete Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_soft_delete_personal_task_by_owner():
    fake_row = {
        "task_id": 1,
        "task": "Personal task",
        "owner_id": "u1",
        "project_id": None,
        "guild_id": None,
        "is_deleted": False,
    }
    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=fake_row)), \
         patch.object(service.db, "aexecute", new=AsyncMock()) as mock_exec, \
         patch.object(service.db, "alog_action", new=AsyncMock()) as mock_audit:

        ok = await service.soft_delete_task(task_id=1, user_id="u1")
        assert ok is True
        mock_exec.assert_called_once()
        # Verify query updates is_deleted and deleted_at
        call_sql = mock_exec.call_args[0][0]
        assert "is_deleted=TRUE" in call_sql
        assert "deleted_at=NOW()" in call_sql
        mock_audit.assert_called_once_with("u1", "task_soft_deleted", "1")


@pytest.mark.asyncio
async def test_soft_delete_personal_task_by_stranger_rejected():
    fake_row = {
        "task_id": 1,
        "task": "Personal task",
        "owner_id": "u1",
        "project_id": None,
        "guild_id": None,
        "is_deleted": False,
    }
    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=fake_row)), \
         patch.object(service.db, "aexecute", new=AsyncMock()) as mock_exec:

        ok = await service.soft_delete_task(task_id=1, user_id="stranger", is_guild_admin=False)
        assert ok is False
        mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_soft_delete_project_task_by_member_with_permission():
    fake_row = {
        "task_id": 10,
        "task": "Collab task",
        "owner_id": "u1",
        "project_id": 5,
        "guild_id": "g1",
        "is_deleted": False,
    }
    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=fake_row)), \
         patch("collaboration.service.check_project_permission", new=AsyncMock(return_value=True)), \
         patch("collaboration.service.log_activity", new=AsyncMock()), \
         patch.object(service.db, "alog_action", new=AsyncMock()), \
         patch.object(service.db, "aexecute", new=AsyncMock()) as mock_exec:

        ok = await service.soft_delete_task(task_id=10, user_id="u2", project_id=5, guild_id="g1")
        assert ok is True
        mock_exec.assert_called_once()


@pytest.mark.asyncio
async def test_soft_delete_project_task_by_member_without_permission_rejected():
    fake_row = {
        "task_id": 10,
        "task": "Collab task",
        "owner_id": "u1",
        "project_id": 5,
        "guild_id": "g1",
        "is_deleted": False,
    }
    fake_proj = MagicMock(owner_id="owner_user")
    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=fake_row)), \
         patch("collaboration.service.check_project_permission", new=AsyncMock(return_value=False)), \
         patch("collaboration.service.get_project", new=AsyncMock(return_value=fake_proj)), \
         patch("collaboration.service.get_member_role", new=AsyncMock(return_value="member")), \
         patch.object(service.db, "aexecute", new=AsyncMock()) as mock_exec:

        ok = await service.soft_delete_task(task_id=10, user_id="u2", project_id=5, guild_id="g1")
        assert ok is False
        mock_exec.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Restore Task Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_restore_task_not_found():
    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=None)):
        ok, msg, tid = await service.restore_task(task_id=999, user_id="u1")
        assert ok is False
        assert msg == "trash_not_found"
        assert tid is None


@pytest.mark.asyncio
async def test_restore_task_expired():
    thirty_five_days_ago = datetime.now(timezone.utc) - timedelta(days=35)
    fake_row = {
        "task_id": 1,
        "task": "Old task",
        "owner_id": "u1",
        "project_id": None,
        "guild_id": None,
        "parent_task_id": None,
        "is_deleted": True,
        "deleted_at": thirty_five_days_ago,
    }
    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=fake_row)):
        ok, msg, tid = await service.restore_task(task_id=1, user_id="u1")
        assert ok is False
        assert msg == "trash_expired"
        assert tid is None


@pytest.mark.asyncio
async def test_restore_task_success():
    five_days_ago = datetime.now(timezone.utc) - timedelta(days=5)
    fake_row = {
        "task_id": 2,
        "task": "Recoverable task",
        "owner_id": "u1",
        "project_id": None,
        "guild_id": None,
        "parent_task_id": None,
        "is_deleted": True,
        "deleted_at": five_days_ago,
    }
    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=fake_row)), \
         patch.object(service.db, "aexecute", new=AsyncMock()) as mock_exec, \
         patch.object(service.db, "alog_action", new=AsyncMock()):

        ok, msg, tid = await service.restore_task(task_id=2, user_id="u1")
        assert ok is True
        assert msg == "trash_restored"
        assert tid == 2
        mock_exec.assert_called_once()
        call_sql = mock_exec.call_args[0][0]
        assert "is_deleted=FALSE" in call_sql
        assert "deleted_at=NULL" in call_sql


@pytest.mark.asyncio
async def test_restore_subtask_also_restores_deleted_parent():
    fake_subtask = {
        "task_id": 12,
        "task": "Subtask",
        "owner_id": "u1",
        "project_id": None,
        "guild_id": None,
        "parent_task_id": 10,
        "is_deleted": True,
        "deleted_at": datetime.now(timezone.utc),
    }
    fake_parent = {
        "task_id": 10,
        "is_deleted": True,
    }
    mock_fetchone = AsyncMock(side_effect=[fake_subtask, fake_parent])
    with patch.object(service.db, "afetchone", new=mock_fetchone), \
         patch.object(service.db, "aexecute", new=AsyncMock()) as mock_exec, \
         patch.object(service.db, "alog_action", new=AsyncMock()):

        ok, msg, tid = await service.restore_task(task_id=12, user_id="u1")
        assert ok is True
        assert tid == 12
        # Should have executed two updates: one for subtask, one for parent
        assert mock_exec.call_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# 4. List Trash, Hard Delete & Purge Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_trash_guild():
    fake_rows = [
        {
            "task_id": 1,
            "task": "T1",
            "owner_id": "u1",
            "guild_id": "g1",
            "project_id": None,
            "deleted_at": datetime.now(timezone.utc),
            "is_deleted": True,
        }
    ]
    with patch.object(service.db, "afetchall", new=AsyncMock(return_value=fake_rows)) as mock_fetch:
        tasks = await service.list_trash(user_id="u1", guild_id="g1")
        assert len(tasks) == 1
        assert tasks[0].task_id == 1
        mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_hard_delete_trash():
    fake_row = {
        "task_id": 5,
        "owner_id": "u1",
        "project_id": None,
        "guild_id": None,
        "is_deleted": True,
    }
    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=fake_row)), \
         patch.object(service.db, "aexecute", new=AsyncMock()) as mock_exec, \
         patch.object(service.db, "alog_action", new=AsyncMock()):

        ok = await service.hard_delete_trash(task_id=5, user_id="u1")
        assert ok is True
        mock_exec.assert_called_once()
        assert "DELETE FROM tasks" in mock_exec.call_args[0][0]


@pytest.mark.asyncio
async def test_purge_expired_trash():
    with patch.object(service.db, "afetchall", new=AsyncMock(return_value=[{"task_id": 1}, {"task_id": 2}])) as mock_fetch:
        count = await service.purge_expired_trash(days=30)
        assert count == 2
        mock_fetch.assert_called_once()
        assert "INTERVAL '30 days'" in mock_fetch.call_args[0][0]


# ─────────────────────────────────────────────────────────────────────────────
# 5. RecoveryCog Registration Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_recovery_cog_commands():
    bot = MagicMock()
    cog = RecoveryCog(bot)
    commands = cog.get_app_commands()
    cmd_names = [c.name for c in commands]
    assert "trash" in cmd_names
    assert "restore" in cmd_names
