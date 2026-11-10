"""
tests/test_peer_kudos.py — Unit tests for Peer Kudos & Team Gratitude.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import pytest

from kudos.models import PeerKudos
from kudos.service import (
    DAILY_KUDOS_LIMIT,
    get_kudos_leaderboard,
    get_user_recent_kudos,
    send_kudos,
)


def test_peer_kudos_model():
    now = datetime.now(timezone.utc)
    kudos = PeerKudos(
        kudos_id=1,
        guild_id="G1",
        from_user_id="U1",
        to_user_id="U2",
        reason="Thanks for fixing the critical login bug!",
        points=30,
        created_at=now,
        task_id=101,
        task_title="Fix Login Crash",
    )
    assert kudos.kudos_id == 1
    assert kudos.points == 30
    assert kudos.task_id == 101


@pytest.mark.asyncio
async def test_send_kudos_success():
    now = datetime.now(timezone.utc)
    mock_row = {
        "kudos_id": 1,
        "guild_id": "G1",
        "from_user_id": "U1",
        "to_user_id": "U2",
        "task_id": 42,
        "reason": "Great teamwork on Sprint 12!",
        "points": 30,
        "created_at": now,
    }

    # count_row has count 2 (< 5 daily limit)
    count_row = {"count": 2}
    task_row = {"task": "Complete Documentation"}

    with patch("kudos.service.db.fetchone", side_effect=[count_row, task_row, mock_row]), \
         patch("kudos.service.award_exp", new_callable=AsyncMock) as mock_award:
        kudos = await send_kudos(
            guild_id="G1",
            from_user_id="U1",
            to_user_id="U2",
            reason="Great teamwork on Sprint 12!",
            task_id=42,
        )

        assert kudos.kudos_id == 1
        assert kudos.from_user_id == "U1"
        assert kudos.to_user_id == "U2"
        # 30 EXP awarded to recipient U2
        mock_award.assert_awaited_once_with("U2", 30, reason="Received Kudos from <@U1>")


@pytest.mark.asyncio
async def test_send_kudos_self_error():
    with pytest.raises(ValueError, match="Cannot send kudos to yourself"):
        await send_kudos(
            guild_id="G1",
            from_user_id="U1",
            to_user_id="U1",
            reason="I am awesome!",
        )


@pytest.mark.asyncio
async def test_send_kudos_daily_rate_limit():
    count_row = {"count": DAILY_KUDOS_LIMIT}  # 5 sent in 24 hours

    with patch("kudos.service.db.fetchone", new=AsyncMock(return_value=count_row)):
        with pytest.raises(ValueError, match="Daily kudos limit reached"):
            await send_kudos(
                guild_id="G1",
                from_user_id="U1",
                to_user_id="U2",
                reason="Thanks again!",
            )


@pytest.mark.asyncio
async def test_get_kudos_leaderboard():
    mock_rows = [
        {"user_id": "U2", "kudos_count": 8, "total_points": 240},
        {"user_id": "U3", "kudos_count": 5, "total_points": 150},
    ]

    with patch("kudos.service.db.fetchall", new=AsyncMock(return_value=mock_rows)):
        leaders = await get_kudos_leaderboard("G1", period="month")
        assert len(leaders) == 2
        assert leaders[0]["user_id"] == "U2"
        assert leaders[0]["kudos_count"] == 8
        assert leaders[0]["total_points"] == 240


@pytest.mark.asyncio
async def test_get_user_recent_kudos():
    now = datetime.now(timezone.utc)
    mock_rows = [
        {
            "kudos_id": 1,
            "from_user_id": "U1",
            "reason": "Speedy code review!",
            "points": 30,
            "task_id": 50,
            "task_title": "PR #12 Review",
            "created_at": now,
        }
    ]

    with patch("kudos.service.db.fetchall", new=AsyncMock(return_value=mock_rows)):
        recent = await get_user_recent_kudos("U2", days=7)
        assert len(recent) == 1
        assert recent[0]["from_user_id"] == "U1"
        assert recent[0]["task_title"] == "PR #12 Review"
