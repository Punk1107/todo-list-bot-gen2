"""
tests/test_task_history.py — Unit tests for Category 10: Task Audit Trail & Activity History
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import discord

from history_reporting.models import TaskAuditEvent, TaskAuditHistory
from history_reporting import service as history_service
from history_reporting.views import TaskHistoryView


# ─────────────────────────────────────────────────────────────────────────────
# 1. Model & Helper Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_task_audit_event_icons_and_descriptions():
    now = datetime.now(timezone.utc)

    # 1. Creation
    e_create = TaskAuditEvent(
        log_id=1, user_id="111", action="task_created", target_id="10",
        detail="Buy groceries", created_at=now,
    )
    assert e_create.icon == "➕"
    assert "Buy groceries" in e_create.format_description()

    # 2. Snooze with new_dl
    e_snooze1 = TaskAuditEvent(
        log_id=2, user_id="111", action="task_snoozed", target_id="10",
        detail="new_dl=2026-10-25T12:00:00", created_at=now,
    )
    assert e_snooze1.icon == "⏰"
    assert "2026-10-25T12:00:00" in e_snooze1.format_description()

    # 3. Snooze with preset
    e_snooze2 = TaskAuditEvent(
        log_id=3, user_id="111", action="task_snoozed", target_id="10",
        detail="preset=3h", created_at=now,
    )
    assert "+3h" in e_snooze2.format_description()

    # 4. Priority changed
    e_prio = TaskAuditEvent(
        log_id=4, user_id="111", action="task_priority_changed", target_id="10",
        detail="P5 (Urgent)", created_at=now,
    )
    assert e_prio.icon == "⚡"
    assert "P5" in e_prio.format_description()

    # 5. Completed
    e_comp = TaskAuditEvent(
        log_id=5, user_id="111", action="task_completed", target_id="10",
        detail=None, created_at=now,
    )
    assert e_comp.icon == "✅"
    assert "completed" in e_comp.format_description().lower()

    # 6. Moved to trash & restored
    e_del = TaskAuditEvent(
        log_id=6, user_id="111", action="task_soft_deleted", target_id="10",
        detail=None, created_at=now,
    )
    assert e_del.icon == "🗑️"
    e_res = TaskAuditEvent(
        log_id=7, user_id="111", action="task_restored", target_id="10",
        detail=None, created_at=now,
    )
    assert e_res.icon == "♻️"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Service & Permission Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_task_audit_history_task_not_found():
    with patch.object(history_service.db, "afetchone", new=AsyncMock(return_value=None)):
        res = await history_service.get_task_audit_history(task_id=999, user_id="u1")
        assert res is None


@pytest.mark.asyncio
async def test_get_task_audit_history_permission_denied_for_stranger():
    task_row = {
        "task_id": 10,
        "task": "Private task",
        "owner_id": "owner_123",
        "project_id": None,
        "guild_id": None,
        "status": "pending",
        "priority": 2,
        "deadline": None,
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc),
        "category_name": "General",
    }
    with patch.object(history_service.db, "afetchone", new=AsyncMock(return_value=task_row)):
        # Stranger (not owner, not admin)
        res = await history_service.get_task_audit_history(task_id=10, user_id="stranger_999", is_guild_admin=False)
        assert res is None

        # Admin can view
        with patch.object(history_service.db, "afetchall", new=AsyncMock(return_value=[])):
            admin_res = await history_service.get_task_audit_history(
                task_id=10, user_id="admin_999", is_guild_admin=True
            )
            assert admin_res is not None
            assert admin_res.task_id == 10


@pytest.mark.asyncio
async def test_get_task_audit_history_success_with_snooze_counting():
    now = datetime.now(timezone.utc)
    task_row = {
        "task_id": 15,
        "task": "Deploy Website",
        "owner_id": "user_42",
        "project_id": None,
        "guild_id": None,
        "status": "Pending",
        "priority": 4,
        "deadline": "2026-10-30T10:00:00",
        "is_deleted": False,
        "created_at": "2026-10-20T08:00:00",
        "category_name": "Work",
    }
    audit_rows = [
        {"log_id": 103, "user_id": "user_42", "action": "task_snoozed", "target_id": "15", "detail": "preset=1d", "created_at": now},
        {"log_id": 102, "user_id": "user_42", "action": "task_snoozed", "target_id": "15", "detail": "new_dl=2026-10-25", "created_at": now},
        {"log_id": 101, "user_id": "user_42", "action": "task_priority_changed", "target_id": "15", "detail": "4", "created_at": now},
        {"log_id": 100, "user_id": "creator_1", "action": "task_created", "target_id": "15", "detail": "Deploy Website", "created_at": now},
    ]

    with patch.object(history_service.db, "afetchone", new=AsyncMock(return_value=task_row)), \
         patch.object(history_service.db, "afetchall", new=AsyncMock(return_value=audit_rows)):

        history = await history_service.get_task_audit_history(task_id=15, user_id="user_42")

        assert history is not None
        assert history.task_id == 15
        assert history.task_name == "Deploy Website"
        assert history.snooze_count == 2
        assert len(history.events) == 4
        assert history.creator_id == "creator_1"
        assert history.current_priority == 4
        assert history.category_name == "Work"


# ─────────────────────────────────────────────────────────────────────────────
# 3. View & Embed Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_task_history_view_pagination_and_embed():
    now = datetime.now(timezone.utc)
    events = [
        TaskAuditEvent(log_id=i, user_id="user_1", action="task_snoozed", target_id="7", detail=f"snooze {i}", created_at=now)
        for i in range(12)  # 12 events -> 3 pages of 5 events (5, 5, 2)
    ]
    history = TaskAuditHistory(
        task_id=7,
        task_name="Write Documentation",
        owner_id="user_1",
        created_at=now,
        snooze_count=12,
        events=events,
        current_status="pending",
        current_priority=3,
        category_name="Documentation",
        creator_id="user_1",
    )

    view = TaskHistoryView(history=history, user_id="user_1", lang="en", page=0)
    assert view.total_pages == 3
    assert view.prev_btn.disabled is True
    assert view.next_btn.disabled is False

    embed = view.make_embed()
    assert "Task #7 Audit History" in embed.title
    assert "Write Documentation" in embed.description
    assert "Snoozed count: **12**" in embed.description
    assert len(embed.fields) == 5  # Page 0 has 5 events

    # Page 2 (last page)
    view.page = 2
    view._update_button_states()
    assert view.prev_btn.disabled is False
    assert view.next_btn.disabled is True
    embed_page2 = view.make_embed()
    assert len(embed_page2.fields) == 2
