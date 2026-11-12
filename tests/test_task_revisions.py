"""
tests/test_task_revisions.py — Unit tests for Feature 35: Task Revision History & Git Diff Rollback.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from history_reporting import service as history_service
from history_reporting.models import TaskDiffResult, TaskRevision
from history_reporting.views import TaskRevisionDiffView


def test_compute_unified_diff_counts_and_truncation():
    old_txt = "line 1\nold requirement\nline 3"
    new_txt = "line 1\nupdated requirement\nextra line\nline 3"

    preview, added, removed, full, truncated = history_service.compute_unified_diff(
        old_txt, new_txt, from_label="rev#1", to_label="current"
    )
    assert added == 2
    assert removed == 1
    assert "-old requirement" in preview
    assert "+updated requirement" in preview
    assert truncated is False

    big_old = "\n".join(f"old line {i}" for i in range(200))
    big_new = "\n".join(f"new line {i}" for i in range(200))
    preview2, _, _, full2, trunc2 = history_service.compute_unified_diff(
        big_old, big_new, max_preview_chars=300
    )
    assert trunc2 is True
    assert len(full2) > len(preview2)
    assert "(diff truncated)" in preview2


@pytest.mark.asyncio
async def test_record_task_revision_skips_unchanged_and_inserts_on_change():
    # Unchanged description must NOT insert a duplicate revision
    with patch.object(history_service.db, "afetchone", new=AsyncMock()) as mock_fetch:
        rev_none = await history_service.record_task_revision(
            task_id=10,
            edited_by="u1",
            previous_description="Same text",
            new_description="Same text",
        )
        assert rev_none is None
        mock_fetch.assert_not_called()

    # Changed description inserts snapshot
    with patch("utils.helpers.ensure_user", new=AsyncMock()), \
         patch.object(history_service.db, "afetchone", new=AsyncMock(return_value={"revision_id": 44})):
        rev_id = await history_service.record_task_revision(
            task_id=10,
            edited_by="u1",
            previous_description="Old v1",
            new_description="New v2",
        )
        assert rev_id == 44


@pytest.mark.asyncio
async def test_rollback_task_description_creates_compensating_snapshot_and_updates():
    task_row = {
        "task_id": 55,
        "task": "Refactor Auth",
        "owner_id": "u1",
        "status": "Pending",
        "priority": 3,
        "deadline": None,
        "description": "Current broken description",
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc),
        "project_id": None,
        "guild_id": None,
        "category_name": "Backend",
    }
    rev_row = {
        "revision_id": 12,
        "task_id": 55,
        "previous_description": "Clean original description",
    }

    with patch.object(
        history_service.db,
        "afetchone",
        new=AsyncMock(side_effect=[task_row, rev_row, {"revision_id": 13}]),
    ), \
         patch("utils.helpers.ensure_user", new=AsyncMock()), \
         patch.object(history_service.db, "aexecute", new=AsyncMock()) as mock_exec, \
         patch.object(history_service.db, "alog_action", new=AsyncMock()) as mock_log:
        ok, msg_key = await history_service.rollback_task_description(
            task_id=55,
            revision_id=12,
            actor_id="u1",
        )

    assert ok is True
    assert msg_key == "rev_rollback_success"
    mock_exec.assert_awaited_once()
    sql_called, params_called = mock_exec.call_args.args
    assert "UPDATE tasks" in sql_called
    assert params_called == ("Clean original description", 55)
    mock_log.assert_awaited_once()


@pytest.mark.asyncio
async def test_revision_diff_view_renders_embed_and_buttons():
    now = datetime.now(timezone.utc)
    rev = TaskRevision(
        revision_id=9,
        task_id=55,
        edited_by="u1",
        previous_description="Alpha",
        new_description="Beta",
        change_source="edit",
        created_at=now,
    )
    diff_res = TaskDiffResult(
        task_id=55,
        task_title="Build API",
        current_description="Beta",
        revisions=[rev],
        selected_revision=rev,
        unified_diff_preview="--- rev#9\n+++ current\n-Alpha\n+Beta",
        unified_diff_full="--- rev#9\n+++ current\n-Alpha\n+Beta",
        added_lines=1,
        removed_lines=1,
        truncated=False,
        can_rollback=True,
    )
    view = TaskRevisionDiffView(diff_result=diff_res, user_id="u1", lang="en")
    embed = view.make_embed()
    assert "#55" in embed.title
    assert "```diff" in embed.description
    assert view.rollback_btn.disabled is False
    assert view.download_diff_btn.disabled is False

