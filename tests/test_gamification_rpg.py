"""
tests/test_gamification_rpg.py — Unit tests for Gen 5.0 Pillar 8:
Productivity RPG, Leveling Curve, Titles & Vacation / Streak Freeze.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch
import pytest

from gamification.rpg import (
    EXP_CHECKLIST,
    EXP_P0_P2,
    EXP_P3_P4,
    EXP_P5_P6,
    EXP_P7,
    EXP_POMODORO,
    award_exp,
    calculate_level_from_exp,
    exp_required_for_next_level,
    get_task_exp,
    get_title_for_level,
    render_rpg_progress_bar,
)
from gamification.vacation import (
    MAX_STREAK_FREEZE_TOKENS,
    STREAK_MILESTONE_INTERVAL,
    evaluate_streak_update,
    get_vacation_status,
    start_vacation,
    stop_vacation,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. RPG EXP Tables & Leveling Math Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_get_task_exp():
    assert get_task_exp(0) == EXP_P0_P2  # 10
    assert get_task_exp(1) == EXP_P0_P2  # 10
    assert get_task_exp(2) == EXP_P0_P2  # 10
    assert get_task_exp(3) == EXP_P3_P4  # 25
    assert get_task_exp(4) == EXP_P3_P4  # 25
    assert get_task_exp(5) == EXP_P5_P6  # 50
    assert get_task_exp(6) == EXP_P5_P6  # 50
    assert get_task_exp(7) == EXP_P7     # 100
    assert EXP_CHECKLIST == 5
    assert EXP_POMODORO == 20


def test_exp_required_for_next_level():
    # Level 1: 100 * 1^1.5 = 100
    assert exp_required_for_next_level(1) == 100
    # Level 2: 100 * 2^1.5 = 100 * 2.8284 = 282
    assert exp_required_for_next_level(2) == 282
    # Level 3: 100 * 3^1.5 = 100 * 5.196 = 519
    assert exp_required_for_next_level(3) == 519
    # Level 4: 100 * 4^1.5 = 100 * 8 = 800
    assert exp_required_for_next_level(4) == 800


def test_calculate_level_from_exp():
    # 0 EXP -> Level 1, 0/100, 0%
    lvl, cur, req, pct = calculate_level_from_exp(0)
    assert (lvl, cur, req, pct) == (1, 0, 100, 0.0)

    # 50 EXP -> Level 1, 50/100, 50%
    lvl, cur, req, pct = calculate_level_from_exp(50)
    assert (lvl, cur, req, pct) == (1, 50, 100, 50.0)

    # 100 EXP -> Level 2, 0/282, 0%
    lvl, cur, req, pct = calculate_level_from_exp(100)
    assert (lvl, cur, req, pct) == (2, 0, 282, 0.0)

    # 241 EXP -> Level 2, 141/282, 50.0%
    lvl, cur, req, pct = calculate_level_from_exp(241)
    assert (lvl, cur, req) == (2, 141, 282)
    assert pct == 50.0


def test_titles_by_level():
    assert get_title_for_level(1) == "🔰 Task Initiate"
    assert get_title_for_level(4) == "🔰 Task Initiate"
    assert get_title_for_level(5) == "⚔️ Task Apprentice"
    assert get_title_for_level(10) == "🛡️ Sprint Adventurer"
    assert get_title_for_level(15) == "🏹 Workflow Scout"
    assert get_title_for_level(20) == "🗡️ Sprint Paladin"
    assert get_title_for_level(30) == "🔮 Focus Sorcerer"
    assert get_title_for_level(45) == "⚡ Productivity Archmage"
    assert get_title_for_level(50) == "👑 Grand Taskmaster Mythic"
    assert get_title_for_level(99) == "👑 Grand Taskmaster Mythic"


def test_render_rpg_progress_bar():
    bar_0 = render_rpg_progress_bar(0.0, length=10)
    assert bar_0 == "[░░░░░░░░░░] 0.0%"

    bar_50 = render_rpg_progress_bar(50.0, length=10)
    assert bar_50 == "[█████░░░░░] 50.0%"

    bar_100 = render_rpg_progress_bar(100.0, length=10)
    assert bar_100 == "[██████████] 100.0%"


@pytest.mark.asyncio
async def test_award_exp_and_level_up():
    mock_user_row = {"total_exp": 80, "rpg_level": 1, "rpg_title": "🔰 Task Initiate"}

    with patch("gamification.rpg.db.execute", new_callable=AsyncMock) as mock_exec, \
         patch("gamification.rpg.db.fetchone", new=AsyncMock(return_value=mock_user_row)):
        # Award 50 EXP: 80 + 50 = 130 EXP (Level 2!)
        res = await award_exp("user_123", 50, reason="P5 Task Complete")
        assert res["total_exp"] == 130
        assert res["old_level"] == 1
        assert res["new_level"] == 2
        assert res["did_level_up"] is True
        assert mock_exec.await_count >= 2


# ─────────────────────────────────────────────────────────────────────────────
# 2. Vacation Mode & Streak Freeze Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_evaluate_streak_update_consecutive():
    today = date(2026, 11, 10)
    yesterday = date(2026, 11, 9)

    streak, freeze_used, vac_used, tokens = evaluate_streak_update(
        current_streak=5,
        last_day=yesterday,
        completion_day=today,
        vacation_until=None,
        freeze_tokens=2,
    )
    assert streak == 6
    assert freeze_used is False
    assert vac_used is False
    assert tokens == 2


def test_evaluate_streak_update_same_day():
    today = date(2026, 11, 10)

    streak, freeze_used, vac_used, tokens = evaluate_streak_update(
        current_streak=5,
        last_day=today,
        completion_day=today,
        vacation_until=None,
        freeze_tokens=2,
    )
    assert streak == 5
    assert freeze_used is False
    assert vac_used is False
    assert tokens == 2


def test_evaluate_streak_update_vacation_mode():
    today = date(2026, 11, 10)
    three_days_ago = date(2026, 11, 7)
    vac_until = date(2026, 11, 12)  # Active vacation covering gap

    streak, freeze_used, vac_used, tokens = evaluate_streak_update(
        current_streak=10,
        last_day=three_days_ago,
        completion_day=today,
        vacation_until=vac_until,
        freeze_tokens=2,
    )
    assert streak == 11
    assert vac_used is True
    assert freeze_used is False
    assert tokens == 2


def test_evaluate_streak_update_missed_day_with_freeze_token():
    today = date(2026, 11, 10)
    two_days_ago = date(2026, 11, 8)  # Missed 1 day (Nov 9)

    streak, freeze_used, vac_used, tokens = evaluate_streak_update(
        current_streak=8,
        last_day=two_days_ago,
        completion_day=today,
        vacation_until=None,
        freeze_tokens=2,
    )
    assert streak == 9
    assert freeze_used is True
    assert vac_used is False
    assert tokens == 1  # 1 token consumed!


def test_evaluate_streak_update_missed_day_without_freeze_token():
    today = date(2026, 11, 10)
    two_days_ago = date(2026, 11, 8)  # Missed 1 day with 0 tokens

    streak, freeze_used, vac_used, tokens = evaluate_streak_update(
        current_streak=8,
        last_day=two_days_ago,
        completion_day=today,
        vacation_until=None,
        freeze_tokens=0,
    )
    assert streak == 1  # Reset!
    assert freeze_used is False
    assert vac_used is False
    assert tokens == 0


@pytest.mark.asyncio
async def test_start_and_stop_vacation():
    with patch("gamification.vacation.db.execute", new_callable=AsyncMock) as mock_exec:
        res = await start_vacation("user_123", days=7, reason="Beach Trip")
        assert res["days"] == 7
        assert res["reason"] == "Beach Trip"
        mock_exec.assert_awaited_once()

        stopped = await stop_vacation("user_123")
        assert stopped is True

