"""
tests/test_guild_quests.py — Unit tests for Server Co-op Quests and Guild Raids.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import pytest

from quests.models import GuildQuest, QuestParticipant
from quests.service import (
    create_quest,
    get_active_quest,
    list_guild_quests,
    record_task_contribution,
)


def test_guild_quest_model():
    now = datetime.now(timezone.utc)
    quest = GuildQuest(
        quest_id=1,
        guild_id="G100",
        creator_id="U1",
        title="Weekly Sprint Raid",
        description="Clear 100 tasks together",
        target_tasks=100,
        completed_tasks=45,
        min_tasks_per_member=3,
        exp_reward=500,
        badge_reward="Guild Raid Hero",
        start_date=now,
        end_date=now + timedelta(days=7),
        status="active",
        created_at=now,
    )

    assert quest.progress_pct == 45.0
    assert quest.is_completed is False
    bar = quest.render_progress_bar(length=10)
    assert "[████░░░░░░] 45/100 (45.0%)" == bar


@pytest.mark.asyncio
async def test_create_quest():
    now = datetime.now(timezone.utc)
    mock_row = {
        "quest_id": 10,
        "guild_id": "G100",
        "creator_id": "U1",
        "title": "Clear 50 Bugs",
        "description": "Fix bug tasks before Friday",
        "target_tasks": 50,
        "completed_tasks": 0,
        "min_tasks_per_member": 3,
        "exp_reward": 500,
        "badge_reward": "Bug Buster Guild",
        "start_date": now,
        "end_date": now + timedelta(days=5),
        "status": "active",
        "created_at": now,
    }

    with patch("quests.service.db.fetchone", new=AsyncMock(return_value=mock_row)):
        q = await create_quest(
            guild_id="G100",
            creator_id="U1",
            title="Clear 50 Bugs",
            target_tasks=50,
            days=5,
        )
        assert q.quest_id == 10
        assert q.title == "Clear 50 Bugs"
        assert q.target_tasks == 50


@pytest.mark.asyncio
async def test_record_task_contribution_in_progress():
    now = datetime.now(timezone.utc)
    active_quest_row = {
        "quest_id": 1,
        "guild_id": "G100",
        "creator_id": "U1",
        "title": "Raid 100",
        "description": None,
        "target_tasks": 100,
        "completed_tasks": 10,
        "min_tasks_per_member": 3,
        "exp_reward": 500,
        "badge_reward": "Guild Raid Hero",
        "start_date": now,
        "end_date": now + timedelta(days=7),
        "status": "active",
        "created_at": now,
    }

    updated_quest_row = dict(active_quest_row)
    updated_quest_row["completed_tasks"] = 11

    with patch("quests.service.db.fetchone", side_effect=[active_quest_row, updated_quest_row]), \
         patch("quests.service.db.execute", new_callable=AsyncMock) as mock_exec:
        res = await record_task_contribution("G100", "user_42")
        assert res is not None
        assert res["quest_id"] == 1
        assert res["just_completed"] is False
        assert res["current"] == 11
        mock_exec.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_task_contribution_completes_quest_and_rewards():
    now = datetime.now(timezone.utc)
    active_quest_row = {
        "quest_id": 1,
        "guild_id": "G100",
        "creator_id": "U1",
        "title": "Raid 100",
        "description": None,
        "target_tasks": 10,
        "completed_tasks": 9,
        "min_tasks_per_member": 3,
        "exp_reward": 500,
        "badge_reward": "Guild Raid Hero",
        "start_date": now,
        "end_date": now + timedelta(days=7),
        "status": "active",
        "created_at": now,
    }

    updated_quest_row = dict(active_quest_row)
    updated_quest_row["completed_tasks"] = 10  # Hit target!

    mock_qualifying_participants = [
        {"user_id": "U1", "tasks_contributed": 5},
        {"user_id": "U2", "tasks_contributed": 3},
    ]

    with patch("quests.service.db.fetchone", side_effect=[active_quest_row, updated_quest_row]), \
         patch("quests.service.db.execute", new_callable=AsyncMock) as mock_exec, \
         patch("quests.service.db.fetchall", new=AsyncMock(return_value=mock_qualifying_participants)), \
         patch("gamification.rpg.award_exp", new_callable=AsyncMock) as mock_award:
        res = await record_task_contribution("G100", "user_42")
        assert res is not None
        assert res["just_completed"] is True
        assert res["target"] == 10

        # Verify participants with >= 3 tasks received bonus EXP
        assert mock_award.await_count == 2

