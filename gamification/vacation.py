"""
gamification/vacation.py — Vacation Mode & Streak Freeze Tokens Engine (Gen 5.0).

Handles fair work-life balance rules:
- Freezing streak during scheduled vacation mode (/vacation).
- Auto-awarding Streak Freeze Tokens on every 14-day streak milestone.
- Auto-consuming a Streak Freeze Token to save streaks on missed days.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any, Optional, Tuple

from core.database import db

log = logging.getLogger(__name__)

MAX_STREAK_FREEZE_TOKENS = 3
STREAK_MILESTONE_INTERVAL = 14


def evaluate_streak_update(
    current_streak: int,
    last_day: Optional[date],
    completion_day: date,
    vacation_until: Optional[date],
    freeze_tokens: int,
) -> Tuple[int, bool, bool, int]:
    """
    Computes updated streak incorporating Vacation Mode and Streak Freeze Tokens.
    
    Returns:
        (new_streak, freeze_token_used, vacation_shielded, remaining_freeze_tokens)
    """
    if last_day is None:
        return 1, False, False, freeze_tokens

    # Case 1: Multiple tasks completed on the same day
    if last_day == completion_day:
        return current_streak, False, False, freeze_tokens

    # Case 2: Exact consecutive day
    if last_day == completion_day - timedelta(days=1):
        return current_streak + 1, False, False, freeze_tokens

    # Case 3: Vacation Mode active / bridging
    # If the user set vacation and the gap falls within or bridges the vacation period
    if vacation_until is not None and (vacation_until >= last_day or completion_day <= vacation_until):
        return current_streak + 1, False, True, freeze_tokens

    # Case 4: Missed exactly 1 day (e.g. completed on Friday, next completion on Sunday)
    # last_day is completion_day - 2 days
    if last_day == completion_day - timedelta(days=2) and freeze_tokens > 0:
        new_tokens = max(0, freeze_tokens - 1)
        return current_streak + 1, True, False, new_tokens

    # Case 5: Broken streak (more than 1 missed day or no freeze tokens)
    return 1, False, False, freeze_tokens


async def start_vacation(
    user_id: str,
    days: int,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """Activates Vacation Mode for the specified number of days."""
    uid = str(user_id)
    clean_days = max(1, min(int(days), 90))
    clean_reason = reason.strip() if reason and reason.strip() else None

    today = datetime.now(timezone.utc).date()
    until_date = today + timedelta(days=clean_days)

    await db.execute(
        """
        UPDATE users
        SET vacation_until = $1, vacation_reason = $2
        WHERE user_id = $3
        """,
        until_date, clean_reason, uid,
    )
    db.query_cache.invalidate_table("users")
    db.invalidate_stats(uid)

    return {
        "user_id": uid,
        "days": clean_days,
        "vacation_until": until_date,
        "reason": clean_reason,
    }


async def stop_vacation(user_id: str) -> bool:
    """Terminates active Vacation Mode early."""
    uid = str(user_id)
    res = await db.execute(
        """
        UPDATE users
        SET vacation_until = NULL, vacation_reason = NULL
        WHERE user_id = $1 AND vacation_until IS NOT NULL
        """,
        uid,
    )
    db.query_cache.invalidate_table("users")
    db.invalidate_stats(uid)
    return True


async def get_vacation_status(user_id: str) -> dict[str, Any]:
    """Retrieves current vacation mode and freeze token stats."""
    uid = str(user_id)
    row = await db.fetchone(
        """
        SELECT vacation_until, vacation_reason, streak_freeze_tokens, streak_days
        FROM users
        WHERE user_id = $1
        """,
        (uid,),
    )
    if not row:
        return {
            "is_on_vacation": False,
            "vacation_until": None,
            "days_remaining": 0,
            "reason": None,
            "freeze_tokens": 0,
            "streak_days": 0,
        }

    vacation_until = row.get("vacation_until")
    today = datetime.now(timezone.utc).date()
    is_active = vacation_until is not None and vacation_until >= today
    days_left = (vacation_until - today).days if is_active and vacation_until else 0

    return {
        "is_on_vacation": is_active,
        "vacation_until": vacation_until,
        "days_remaining": max(0, days_left),
        "reason": row.get("vacation_reason"),
        "freeze_tokens": int(row.get("streak_freeze_tokens") or 0),
        "streak_days": int(row.get("streak_days") or 0),
    }

