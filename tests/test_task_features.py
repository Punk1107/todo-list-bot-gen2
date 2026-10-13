"""Tests for task comments and progress persistence/access rules."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from task_features import service


def _personal_task(owner_id: str = "owner-1", progress_pct: int = 0) -> dict:
    return {
        "task_id": 7,
        "task": "Write the report",
        "owner_id": owner_id,
        "project_id": None,
        "guild_id": None,
        "progress_pct": progress_pct,
    }


class TestTaskFeatureAccess:
    @pytest.mark.asyncio
    async def test_personal_task_is_only_accessible_to_owner(self):
        with patch.object(service.db, "afetchone", new=AsyncMock(return_value=_personal_task())):
            result = await service.get_accessible_task(7, "owner-1")
            assert result["task_id"] == 7

        with patch.object(service.db, "afetchone", new=AsyncMock(return_value=_personal_task())):
            with pytest.raises(service.TaskAccessDenied):
                await service.get_accessible_task(7, "other-user")

    @pytest.mark.asyncio
    async def test_project_viewer_can_read_but_cannot_write(self):
        task = {
            "task_id": 7,
            "task": "Write the report",
            "owner_id": "creator",
            "project_id": 3,
            "guild_id": "guild-1",
            "progress_pct": 25,
        }
        with (
            patch.object(service.db, "afetchone", new=AsyncMock(return_value=task)),
            patch("collaboration.service.get_project", new=AsyncMock(return_value=MagicMock(owner_id="creator"))),
            patch("collaboration.service.get_member_role", new=AsyncMock(return_value="viewer")),
        ):
            await service.get_accessible_task(7, "viewer-1", minimum_role="viewer")
            with pytest.raises(service.TaskAccessDenied):
                await service.get_accessible_task(7, "viewer-1", minimum_role="member")


class TestTaskCommentPersistence:
    @pytest.mark.asyncio
    async def test_comment_list_clamps_page_and_orders_newest_first(self):
        task = _personal_task()
        rows = [{"comment_id": 3, "user_id": "owner-1", "content": "latest"}]
        with (
            patch.object(service.db, "afetchone", new=AsyncMock(side_effect=[task, {"total": 8}])),
            patch.object(service.db, "afetchall", new=AsyncMock(return_value=rows)) as fetchall,
        ):
            result_task, comments, total = await service.get_comments(7, "owner-1", page=99)

        assert result_task["task_id"] == 7
        assert comments == rows
        assert total == 8
        assert fetchall.await_args.args[1] == (7, 5, 5)
        assert "ORDER BY created_at DESC, comment_id DESC" in fetchall.await_args.args[0]

    @pytest.mark.asyncio
    async def test_add_comment_sanitizes_content_and_records_audit(self):
        task = _personal_task()
        with (
            patch.object(service.db, "afetchone", new=AsyncMock(return_value=task)),
            patch.object(service.db, "aexecute", new=AsyncMock()) as execute,
            patch("task_features.service.ensure_user", new=AsyncMock()) as ensure_user,
            patch.object(service.db, "alog_action", new=AsyncMock()) as log_action,
            patch.object(service.db.query_cache, "invalidate_tables") as invalidate_tables,
        ):
            await service.add_comment(7, "owner-1", "  Note\x00 for the task  ")

        ensure_user.assert_awaited_once_with("owner-1")
        assert execute.await_args.args[1] == (7, "owner-1", "Note for the task")
        invalidate_tables.assert_called_once_with(["task_comments"])
        log_action.assert_awaited_once_with("owner-1", "task_commented", "7")

    @pytest.mark.asyncio
    async def test_add_comment_rejects_empty_content(self):
        with pytest.raises(service.InvalidComment):
            await service.add_comment(7, "owner-1", " \x00 ")


class TestTaskProgressPersistence:
    @pytest.mark.asyncio
    async def test_progress_validation_prevents_invalid_database_write(self):
        with patch.object(service.db, "afetchone", new=AsyncMock()) as fetchone:
            for value in (-1, 101, True, "50"):
                with pytest.raises(service.InvalidProgress):
                    await service.update_progress(7, "owner-1", value)
        fetchone.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_valid_progress_is_saved_and_cache_invalidated(self):
        task = _personal_task(progress_pct=20)
        with (
            patch.object(service.db, "afetchone", new=AsyncMock(return_value=task)),
            patch.object(service.db, "aexecute", new=AsyncMock(return_value="UPDATE 1")) as execute,
            patch.object(service.db, "alog_action", new=AsyncMock()) as log_action,
            patch.object(service.db, "invalidate_stats") as invalidate_stats,
        ):
            result = await service.update_progress(7, "owner-1", 75)

        assert result["progress_pct"] == 75
        assert execute.await_args.args[1] == (75, 7)
        log_action.assert_awaited_once_with(
            "owner-1", "task_progress_updated", "7", "progress_pct=75"
        )
        invalidate_stats.assert_called_once_with("owner-1")


class TestTaskFeatureModals:
    def test_modal_inputs_use_supported_discord_components(self):
        from task_features.views import TaskCommentModal, TaskProgressModal

        comment_modal = TaskCommentModal(7, "owner-1", "en", "Write the report")
        progress_modal = TaskProgressModal(7, "owner-1", "en", 35, None)

        assert comment_modal.content.max_length == 1000
        assert progress_modal.progress.default == "35"
        assert progress_modal.progress.max_length == 3
