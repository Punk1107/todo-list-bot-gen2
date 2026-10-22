"""Unit & Integration tests for Category 9 (Item 24): Eisenhower Matrix View."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import discord

from organization import service
from organization.models import (
    EisenhowerQuadrant,
    EisenhowerTask,
    EisenhowerMatrixData,
    QUADRANT_META,
)
from organization.views import (
    EisenhowerMatrixView,
    QuadrantDetailView,
    build_matrix_embed,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Classification Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_classify_q1_important_and_urgent():
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
    
    # Priority 5 (Urgent), deadline in 10 hours (<= 48h)
    row1 = {
        "priority": 5,
        "deadline": (now + timedelta(hours=10)).isoformat(),
    }
    q1, urgent, important, rel = service.classify_task_quadrant(row1, now=now)
    assert q1 == EisenhowerQuadrant.Q1_DO_FIRST
    assert urgent is True
    assert important is True
    assert rel == "⏳ In 10h"

    # Priority 7 (Critical), deadline overdue by 2 hours
    row2 = {
        "priority": 7,
        "deadline": (now - timedelta(hours=2)).isoformat(),
    }
    q2, urgent, important, rel = service.classify_task_quadrant(row2, now=now)
    assert q2 == EisenhowerQuadrant.Q1_DO_FIRST
    assert urgent is True
    assert important is True
    assert rel == "🚨 Overdue 2h"


def test_classify_q2_schedule_important_not_urgent():
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
    
    # Priority 4, deadline in 5 days (> 48h)
    row1 = {
        "priority": 4,
        "deadline": (now + timedelta(days=5)).isoformat(),
    }
    q1, urgent, important, rel = service.classify_task_quadrant(row1, now=now)
    assert q1 == EisenhowerQuadrant.Q2_SCHEDULE
    assert urgent is False
    assert important is True
    assert rel == "📅 In 5d"

    # Priority 6, no deadline
    row2 = {
        "priority": 6,
        "deadline": None,
    }
    q2, urgent, important, rel = service.classify_task_quadrant(row2, now=now)
    assert q2 == EisenhowerQuadrant.Q2_SCHEDULE
    assert urgent is False
    assert important is True
    assert rel == ""


def test_classify_q3_delegate_urgent_not_important():
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
    
    # Priority 2 (Medium), deadline in 24 hours
    row1 = {
        "priority": 2,
        "deadline": (now + timedelta(hours=24)).isoformat(),
    }
    q1, urgent, important, rel = service.classify_task_quadrant(row1, now=now)
    assert q1 == EisenhowerQuadrant.Q3_DELEGATE
    assert urgent is True
    assert important is False
    assert rel == "⏳ In 24h"

    # Priority 0, overdue
    row2 = {
        "priority": 0,
        "deadline": (now - timedelta(days=1)).isoformat(),
    }
    q2, urgent, important, rel = service.classify_task_quadrant(row2, now=now)
    assert q2 == EisenhowerQuadrant.Q3_DELEGATE
    assert urgent is True
    assert important is False
    assert "Overdue" in rel


def test_classify_q4_eliminate_not_urgent_not_important():
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
    
    # Priority 1, deadline in 7 days
    row1 = {
        "priority": 1,
        "deadline": (now + timedelta(days=7)).isoformat(),
    }
    q1, urgent, important, rel = service.classify_task_quadrant(row1, now=now)
    assert q1 == EisenhowerQuadrant.Q4_ELIMINATE
    assert urgent is False
    assert important is False
    assert rel == "📅 In 7d"

    # Priority 3, no deadline
    row2 = {
        "priority": 3,
        "deadline": None,
    }
    q2, urgent, important, rel = service.classify_task_quadrant(row2, now=now)
    assert q2 == EisenhowerQuadrant.Q4_ELIMINATE
    assert urgent is False
    assert important is False
    assert rel == ""


# ─────────────────────────────────────────────────────────────────────────────
# 2. Service Matrix Aggregation Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_eisenhower_matrix_empty():
    with patch.object(service.db, "afetchall", new=AsyncMock(return_value=[])):
        matrix = await service.get_eisenhower_matrix("user123")
        assert matrix.total_tasks == 0
        assert matrix.q1_count == 0
        assert matrix.q2_count == 0
        assert matrix.q3_count == 0
        assert matrix.q4_count == 0
        assert matrix.q1_tasks == []


@pytest.mark.asyncio
async def test_get_eisenhower_matrix_distribution():
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
    mock_rows = [
        {
            "task_id": 1,
            "task": "Emergency Bug Fix",
            "priority": 7,
            "status": "In_Progress",
            "deadline": (now + timedelta(hours=2)).isoformat(),
            "tags": ["bug", "critical"],
            "description": "Fix payment gateway",
            "owner_id": "user123",
            "guild_id": "guild1",
            "project_id": None,
            "is_private": False,
        },
        {
            "task_id": 2,
            "task": "Quarterly Strategy",
            "priority": 5,
            "status": "Pending",
            "deadline": (now + timedelta(days=10)).isoformat(),
            "tags": ["strategy"],
            "description": None,
            "owner_id": "user123",
            "guild_id": "guild1",
            "project_id": None,
            "is_private": False,
        },
        {
            "task_id": 3,
            "task": "Order Stationery",
            "priority": 1,
            "status": "Pending",
            "deadline": (now + timedelta(hours=5)).isoformat(),
            "tags": None,
            "description": None,
            "owner_id": "user123",
            "guild_id": "guild1",
            "project_id": None,
            "is_private": False,
        },
        {
            "task_id": 4,
            "task": "Organize Old Files",
            "priority": 0,
            "status": "Pending",
            "deadline": None,
            "tags": None,
            "description": None,
            "owner_id": "user123",
            "guild_id": "guild1",
            "project_id": None,
            "is_private": False,
        },
    ]

    with patch.object(service.db, "afetchall", new=AsyncMock(return_value=mock_rows)):
        matrix = await service.get_eisenhower_matrix("user123", now=now)
        assert matrix.total_tasks == 4
        assert matrix.q1_count == 1
        assert matrix.q2_count == 1
        assert matrix.q3_count == 1
        assert matrix.q4_count == 1

        assert matrix.q1_tasks[0].task_id == 1
        assert matrix.q2_tasks[0].task_id == 2
        assert matrix.q3_tasks[0].task_id == 3
        assert matrix.q4_tasks[0].task_id == 4


@pytest.mark.asyncio
async def test_get_eisenhower_matrix_confidential_filter():
    now = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
    mock_rows = [
        {
            "task_id": 10,
            "task": "Secret Acquisition",
            "priority": 6,
            "status": "Pending",
            "deadline": (now + timedelta(hours=1)).isoformat(),
            "tags": None,
            "description": None,
            "owner_id": "user999", # Different owner
            "guild_id": "guild1",
            "project_id": 5,
            "is_private": True, # Private!
        },
        {
            "task_id": 11,
            "task": "Public Feature",
            "priority": 6,
            "status": "Pending",
            "deadline": (now + timedelta(hours=1)).isoformat(),
            "tags": None,
            "description": None,
            "owner_id": "user999",
            "guild_id": "guild1",
            "project_id": 5,
            "is_private": False,
        },
    ]

    # Non-admin user querying project: confidential task must be omitted
    with patch.object(service.db, "afetchall", new=AsyncMock(return_value=mock_rows)), \
         patch("collaboration.service.get_member_role", new=AsyncMock(return_value="member")), \
         patch("collaboration.service.get_project", new=AsyncMock(return_value=MagicMock(owner_id="user999"))):
        matrix = await service.get_eisenhower_matrix(
            user_id="user123",
            guild_id="guild1",
            project_id=5,
            is_guild_admin=False,
            now=now,
        )
        assert matrix.total_tasks == 1
        assert matrix.q1_tasks[0].task_id == 11

    # Same query by admin: confidential task is included
    with patch.object(service.db, "afetchall", new=AsyncMock(return_value=mock_rows)):
        matrix_admin = await service.get_eisenhower_matrix(
            user_id="user123",
            guild_id="guild1",
            project_id=5,
            is_guild_admin=True,
            now=now,
        )
        assert matrix_admin.total_tasks == 2


# ─────────────────────────────────────────────────────────────────────────────
# 3. UI Embed & View Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_build_matrix_embed():
    matrix = EisenhowerMatrixData(
        q1_tasks=[
            EisenhowerTask(
                task_id=1,
                task="Do ASAP",
                priority=6,
                status="Pending",
                deadline="2026-10-23T10:00:00",
                tags=["urgent"],
                description="desc",
                owner_id="u1",
                guild_id=None,
                project_id=None,
                is_private=False,
                quadrant=EisenhowerQuadrant.Q1_DO_FIRST,
                is_urgent=True,
                is_important=True,
                relative_time="Due in 2h",
            )
        ],
        q2_tasks=[],
        q3_tasks=[],
        q4_tasks=[],
    )

    embed = build_matrix_embed(matrix, lang="en", theme_color=0x5865F2, scope_name="My Tasks")
    assert "Eisenhower Matrix" in embed.title
    assert "My Tasks" in embed.title
    assert len(embed.fields) == 4
    assert "🔴" in embed.fields[0].name
    assert "#1" in embed.fields[0].value
    assert "Do ASAP" in embed.fields[0].value


def test_quadrant_detail_view_pagination():
    tasks = [
        EisenhowerTask(
            task_id=i,
            task=f"Task #{i}",
            priority=5,
            status="Pending",
            deadline=None,
            tags=None,
            description=f"Description {i}",
            owner_id="u1",
            guild_id=None,
            project_id=None,
            is_private=False,
            quadrant=EisenhowerQuadrant.Q1_DO_FIRST,
            is_urgent=True,
            is_important=True,
            relative_time=None,
        )
        for i in range(1, 13) # 12 tasks
    ]

    parent_view = MagicMock(spec=EisenhowerMatrixView)
    view = QuadrantDetailView(
        user_id="u1",
        guild_id=None,
        parent_view=parent_view,
        quadrant=EisenhowerQuadrant.Q1_DO_FIRST,
        tasks=tasks,
        lang="en",
        theme_color=0xED4245,
        page_size=5,
    )

    # 12 tasks with page_size=5 -> 3 pages
    assert view.total_pages == 3
    assert view.page == 0

    embed_p1 = view.build_embed()
    assert "Page 1/3" in embed_p1.footer.text
    assert len(embed_p1.fields) == 5
    assert "#1" in embed_p1.fields[0].name
    assert "#5" in embed_p1.fields[4].name

    # Advance page
    view.page = 1
    embed_p2 = view.build_embed()
    assert "Page 2/3" in embed_p2.footer.text
    assert "#6" in embed_p2.fields[0].name
    assert "#10" in embed_p2.fields[4].name

    # Last page
    view.page = 2
    embed_p3 = view.build_embed()
    assert "Page 3/3" in embed_p3.footer.text
    assert len(embed_p3.fields) == 2
    assert "#11" in embed_p3.fields[0].name
    assert "#12" in embed_p3.fields[1].name
