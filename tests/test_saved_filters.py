"""Unit & Integration tests for Category 9 (Item 25): Custom Saved Filters (Smart Lists)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import discord

from organization import service
from organization.models import SavedFilter, SavedFilterCriteria
from organization.views import build_filter_list_embed, build_saved_filter_embed


# ─────────────────────────────────────────────────────────────────────────────
# 1. Validation & Creation Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_saved_filter_name_validation():
    # Empty name
    with pytest.raises(ValueError, match="Filter name cannot be empty"):
        await service.create_saved_filter(
            owner_id="u1",
            name="",
            criteria=SavedFilterCriteria(),
        )

    # Whitespace only
    with pytest.raises(ValueError, match="Filter name cannot be empty"):
        await service.create_saved_filter(
            owner_id="u1",
            name="   ",
            criteria=SavedFilterCriteria(),
        )

    # Too long (> 50 chars)
    with pytest.raises(ValueError, match="cannot exceed 50 characters"):
        await service.create_saved_filter(
            owner_id="u1",
            name="a" * 51,
            criteria=SavedFilterCriteria(),
        )


@pytest.mark.asyncio
async def test_create_saved_filter_priority_validation():
    # Min priority > Max priority
    with pytest.raises(ValueError, match="min_priority.*cannot be greater than max_priority"):
        await service.create_saved_filter(
            owner_id="u1",
            name="Invalid Prios",
            criteria=SavedFilterCriteria(min_priority=6, max_priority=2),
        )

    # Priority out of bounds (< 0 or > 7)
    with pytest.raises(ValueError, match="must be between 0 and 7"):
        await service.create_saved_filter(
            owner_id="u1",
            name="Invalid Bounds",
            criteria=SavedFilterCriteria(min_priority=-1),
        )

    with pytest.raises(ValueError, match="must be between 0 and 7"):
        await service.create_saved_filter(
            owner_id="u1",
            name="Invalid Bounds 2",
            criteria=SavedFilterCriteria(max_priority=9),
        )


@pytest.mark.asyncio
async def test_create_saved_filter_limit_exceeded():
    # Mock user having 25 existing filters and new filter name
    with patch("organization.service.get_saved_filter_by_name", new=AsyncMock(return_value=None)), \
         patch.object(service.db, "afetchone", new=AsyncMock(return_value={"cnt": 25})):
        with pytest.raises(ValueError, match="limit of 25 saved filters reached"):
            await service.create_saved_filter(
                owner_id="u1",
                name="Filter 26",
                criteria=SavedFilterCriteria(),
            )


@pytest.mark.asyncio
async def test_create_saved_filter_success():
    mock_row = {
        "filter_id": 42,
        "owner_id": "u1",
        "guild_id": "g1",
        "name": "Urgent Bugs",
        "criteria": json.dumps({
            "tags": ["bug"],
            "min_priority": 5,
            "max_priority": 7,
            "status": "Active",
            "project_id": 10,
            "due_within_days": 3,
            "sort_by": "priority_desc",
        }),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    # First fetchone: count check (returns 5)
    # Second fetchone: INSERT ... RETURNING row
    side_effects = [{"cnt": 5}, mock_row]
    with patch("organization.service.get_saved_filter_by_name", new=AsyncMock(return_value=None)), \
         patch.object(service.db, "afetchone", new=AsyncMock(side_effect=side_effects)):
        crit = SavedFilterCriteria(
            tags=["bug"],
            min_priority=5,
            max_priority=7,
            status="Active",
            project_id=10,
            due_within_days=3,
            sort_by="priority_desc",
        )
        saved = await service.create_saved_filter("u1", "Urgent Bugs", crit, guild_id="g1")
        assert saved.filter_id == 42
        assert saved.name == "Urgent Bugs"
        assert saved.owner_id == "u1"
        assert saved.criteria.tags == ["bug"]
        assert saved.criteria.min_priority == 5
        assert saved.criteria.due_within_days == 3


# ─────────────────────────────────────────────────────────────────────────────
# 2. Retrieval & Deletion Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_saved_filter_by_name():
    mock_row = {
        "filter_id": 1,
        "owner_id": "u1",
        "guild_id": None,
        "name": "My Filter",
        "criteria": {"tags": ["work"], "min_priority": 3},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=mock_row)):
        sf = await service.get_saved_filter_by_name("u1", "My Filter")
        assert sf is not None
        assert sf.filter_id == 1
        assert sf.name == "My Filter"
        assert sf.criteria.tags == ["work"]
        assert sf.criteria.min_priority == 3

    # Non-existent
    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=None)):
        sf_none = await service.get_saved_filter_by_name("u1", "NonExistent")
        assert sf_none is None


@pytest.mark.asyncio
async def test_list_saved_filters():
    mock_rows = [
        {
            "filter_id": 1,
            "owner_id": "u1",
            "guild_id": None,
            "name": "Filter 1",
            "criteria": {"tags": ["ops"]},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        },
        {
            "filter_id": 2,
            "owner_id": "u1",
            "guild_id": None,
            "name": "Filter 2",
            "criteria": {"status": "Pending"},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        },
    ]

    with patch.object(service.db, "afetchall", new=AsyncMock(return_value=mock_rows)):
        filters = await service.list_saved_filters("u1")
        assert len(filters) == 2
        assert filters[0].name == "Filter 1"
        assert filters[1].name == "Filter 2"


@pytest.mark.asyncio
async def test_delete_saved_filter_by_name():
    with patch.object(service.db, "afetchone", new=AsyncMock(return_value={"filter_id": 1})):
        deleted = await service.delete_saved_filter_by_name("u1", "My Filter")
        assert deleted is True

    with patch.object(service.db, "afetchone", new=AsyncMock(return_value=None)):
        deleted = await service.delete_saved_filter_by_name("u1", "NonExistent")
        assert deleted is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Dynamic Query Execution Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_saved_filter_query_builder():
    sf = SavedFilter(
        filter_id=1,
        owner_id="u1",
        guild_id="g1",
        name="Sprint Backlog",
        criteria=SavedFilterCriteria(
            tags=["backend", "v2"],
            min_priority=4,
            max_priority=7,
            status="Active",
            project_id=15,
            due_within_days=7,
            sort_by="deadline_asc",
        ),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    captured_sql = None
    captured_params = None

    async def mock_fetchall(sql, params):
        nonlocal captured_sql, captured_params
        captured_sql = sql
        captured_params = params
        return [
            {
                "task_id": 100,
                "task": "Migrate API Endpoints",
                "priority": 5,
                "status": "In_Progress",
                "deadline": "2026-10-25T18:00:00",
            }
        ]

    with patch.object(service.db, "afetchall", new=mock_fetchall):
        tasks = await service.execute_saved_filter(sf, user_id="u1", guild_id="g1")
        assert len(tasks) == 1
        assert tasks[0]["task_id"] == 100

        # Verify SQL components
        assert "t.is_deleted = FALSE" in captured_sql
        assert "t.project_id = $" in captured_sql
        assert "t.priority >= $" in captured_sql
        assert "t.priority <= $" in captured_sql
        assert "t.status NOT IN ('Completed', 'Cancelled')" in captured_sql
        assert "ORDER BY t.deadline ASC NULLS LAST" in captured_sql

        # Verify parameters
        assert 15 in captured_params # project_id
        assert 4 in captured_params  # min_prio
        assert 7 in captured_params  # max_prio


# ─────────────────────────────────────────────────────────────────────────────
# 4. Embed Builder Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_build_saved_filter_embed():
    sf = SavedFilter(
        filter_id=5,
        owner_id="u1",
        guild_id=None,
        name="High Priority Bugs",
        criteria=SavedFilterCriteria(
            tags=["bug"],
            min_priority=5,
            status="Pending",
            due_within_days=2,
        ),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    tasks = [
        {
            "task_id": 1,
            "task": "Fix Crash on Launch",
            "priority": 7,
            "status": "Pending",
            "deadline": "2026-10-23T15:00:00",
        }
    ]

    embed = build_saved_filter_embed(sf, tasks, lang="en", theme_color=0x5865F2)
    assert "High Priority Bugs" in embed.title
    assert "Tags: `bug`" in embed.description
    assert "Priority: `5..7`" in embed.description
    assert len(embed.fields) == 1
    assert "Fix Crash on Launch" in embed.fields[0].name
    assert "🚨 #1" in embed.fields[0].name


def test_build_filter_list_embed():
    filters = [
        SavedFilter(
            filter_id=1,
            owner_id="u1",
            guild_id=None,
            name="Filter Alpha",
            criteria=SavedFilterCriteria(tags=["alpha"]),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        SavedFilter(
            filter_id=2,
            owner_id="u1",
            guild_id=None,
            name="Filter Beta",
            criteria=SavedFilterCriteria(status="Active"),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    ]

    embed = build_filter_list_embed(filters, lang="en", theme_color=0x5865F2)
    assert "Custom Saved Filters" in embed.title
    assert len(embed.fields) == 2
    assert "Filter Alpha" in embed.fields[0].name
    assert "Filter Beta" in embed.fields[1].name
