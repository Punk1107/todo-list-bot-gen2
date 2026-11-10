"""
gamification/rpg.py — Productivity RPG, Leveling Progression & EXP Engine (Gen 5.0).

Calculates player levels, progression formulas, titles, and manages EXP awards
for task completions, checklists, pomodoros, and peer kudos.
"""
from __future__ import annotations

import logging
import math
from typing import Any, List, Optional, Tuple

from core.database import db

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 1. EXP Tables & Constants
# ─────────────────────────────────────────────────────────────────────────────

EXP_P0_P2 = 10
EXP_P3_P4 = 25
EXP_P5_P6 = 50
EXP_P7 = 100

EXP_CHECKLIST = 5
EXP_POMODORO = 20
EXP_KUDOS = 30
EXP_QUEST_BONUS = 500

TITLES_BY_LEVEL: List[Tuple[int, str]] = [
    (1, "🔰 Task Initiate"),
    (5, "⚔️ Task Apprentice"),
    (10, "🛡️ Sprint Adventurer"),
    (15, "🏹 Workflow Scout"),
    (20, "🗡️ Sprint Paladin"),
    (30, "🔮 Focus Sorcerer"),
    (40, "⚡ Productivity Archmage"),
    (50, "👑 Grand Taskmaster Mythic"),
]


def get_task_exp(priority: int) -> int:
    """Returns the EXP earned for completing a task based on its priority."""
    if priority >= 7:
        return EXP_P7
    elif priority >= 5:
        return EXP_P5_P6
    elif priority >= 3:
        return EXP_P3_P4
    else:
        return EXP_P0_P2


def exp_required_for_next_level(level: int) -> int:
    """
    Calculates EXP required to advance from `level` to `level + 1`.
    Formula: EXP Required = floor(100 * Level^(1.5))
    """
    if level < 1:
        level = 1
    return max(100, int(100 * math.pow(level, 1.5)))


def calculate_level_from_exp(total_exp: int) -> Tuple[int, int, int, float]:
    """
    Calculates the player's level from cumulative total EXP.
    Returns:
        (current_level, exp_into_current_level, exp_needed_for_next_level, progress_pct)
    """
    if total_exp <= 0:
        return 1, 0, 100, 0.0

    level = 1
    remaining = total_exp

    while True:
        req = exp_required_for_next_level(level)
        if remaining < req:
            progress_pct = round((remaining / req) * 100, 1)
            return level, remaining, req, progress_pct
        remaining -= req
        level += 1


def get_title_for_level(level: int) -> str:
    """Determines the unlocked title based on current RPG level."""
    chosen = "🔰 Task Initiate"
    for min_lvl, title in TITLES_BY_LEVEL:
        if level >= min_lvl:
            chosen = title
        else:
            break
    return chosen


def render_rpg_progress_bar(progress_pct: float, length: int = 10) -> str:
    """Generates an ASCII/Unicode progress bar e.g. [██████░░░░] 60.0%."""
    filled = max(0, min(length, int(round((progress_pct / 100) * length))))
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {progress_pct:.1f}%"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Database Operations & EXP Awarding
# ─────────────────────────────────────────────────────────────────────────────

async def award_exp(
    user_id: str,
    exp_amount: int,
    reason: str = "",
) -> dict[str, Any]:
    """
    Awards EXP to a user, handles leveling up, and persists changes atomically.
    Returns a dictionary summarizing the award and any level/title changes.
    """
    clean_exp = max(0, int(exp_amount))
    if clean_exp == 0:
        return {"exp_awarded": 0, "did_level_up": False}

    uid = str(user_id)
    # Ensure user exists
    await db.execute(
        "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING",
        uid,
    )

    # Fetch current stats
    row = await db.fetchone(
        "SELECT total_exp, rpg_level, rpg_title FROM users WHERE user_id = $1",
        (uid,),
    )
    old_total_exp = int(row["total_exp"]) if row and row.get("total_exp") is not None else 0
    old_level = int(row["rpg_level"]) if row and row.get("rpg_level") is not None else 1

    new_total_exp = old_total_exp + clean_exp
    new_level, cur_exp, next_exp, pct = calculate_level_from_exp(new_total_exp)
    new_title = get_title_for_level(new_level)
    did_level_up = new_level > old_level

    # Update database
    await db.execute(
        """
        UPDATE users
        SET total_exp = $1, rpg_level = $2, rpg_title = $3
        WHERE user_id = $4
        """,
        new_total_exp, new_level, new_title, uid,
    )
    db.query_cache.invalidate_table("users")
    db.invalidate_stats(uid)

    return {
        "user_id": uid,
        "exp_awarded": clean_exp,
        "reason": reason,
        "old_level": old_level,
        "new_level": new_level,
        "did_level_up": did_level_up,
        "total_exp": new_total_exp,
        "current_level_exp": cur_exp,
        "next_level_exp": next_exp,
        "progress_pct": pct,
        "title": new_title,
    }


async def get_user_rpg_profile(user_id: str) -> dict[str, Any]:
    """Retrieves full RPG stats, level, EXP progress, and achievements for a user."""
    uid = str(user_id)
    row = await db.fetchone(
        """
        SELECT user_id, total_exp, rpg_level, rpg_title, streak_days,
               streak_freeze_tokens, vacation_until, vacation_reason
        FROM users
        WHERE user_id = $1
        """,
        (uid,),
    )

    total_exp = int(row["total_exp"]) if row and row.get("total_exp") is not None else 0
    level, cur_exp, next_exp, pct = calculate_level_from_exp(total_exp)
    title = row.get("rpg_title") if row and row.get("rpg_title") else get_title_for_level(level)

    # Task completion counts
    comp_row = await db.fetchone(
        """
        SELECT COUNT(*) AS total_completed,
               COUNT(*) FILTER (WHERE priority >= 7) AS p7_count,
               COUNT(*) FILTER (WHERE priority BETWEEN 5 AND 6) AS p5_p6_count,
               COUNT(*) FILTER (WHERE priority BETWEEN 3 AND 4) AS p3_p4_count,
               COUNT(*) FILTER (WHERE priority <= 2) AS p0_p2_count
        FROM task_completion_events
        WHERE user_id = $1
        """,
        (uid,),
    )

    # Badges
    badges_rows = await db.fetchall(
        "SELECT type, awarded_at FROM user_achievements WHERE user_id = $1 ORDER BY awarded_at DESC",
        (uid,),
    )
    badges = [dict(b) for b in badges_rows] if badges_rows else []

    return {
        "user_id": uid,
        "total_exp": total_exp,
        "level": level,
        "title": title,
        "current_level_exp": cur_exp,
        "next_level_exp": next_exp,
        "progress_pct": pct,
        "progress_bar": render_rpg_progress_bar(pct),
        "streak_days": int(row["streak_days"]) if row and row.get("streak_days") else 0,
        "streak_freeze_tokens": int(row["streak_freeze_tokens"]) if row and row.get("streak_freeze_tokens") else 0,
        "vacation_until": row.get("vacation_until") if row else None,
        "vacation_reason": row.get("vacation_reason") if row else None,
        "total_completed": int(comp_row["total_completed"]) if comp_row else 0,
        "p7_count": int(comp_row["p7_count"]) if comp_row else 0,
        "p5_p6_count": int(comp_row["p5_p6_count"]) if comp_row else 0,
        "p3_p4_count": int(comp_row["p3_p4_count"]) if comp_row else 0,
        "p0_p2_count": int(comp_row["p0_p2_count"]) if comp_row else 0,
        "badges": badges,
    }


async def get_rpg_leaderboard(guild_id: Optional[str] = None, limit: int = 10) -> list[dict[str, Any]]:
    """Retrieves top players ranked by RPG level and total EXP."""
    if guild_id:
        # Guild-scoped: users who have participated in guild tasks or have activity
        query = """
            SELECT DISTINCT u.user_id, u.total_exp, u.rpg_level, u.rpg_title, u.streak_days
            FROM users u
            WHERE u.user_id IN (
                SELECT DISTINCT owner_id FROM tasks WHERE guild_id = $1
                UNION
                SELECT DISTINCT user_id FROM task_completion_events WHERE guild_id = $1
                UNION
                SELECT DISTINCT user_id FROM project_members pm
                JOIN projects p ON pm.project_id = p.project_id WHERE p.guild_id = $1
            )
            ORDER BY u.rpg_level DESC, u.total_exp DESC
            LIMIT $2
        """
        rows = await db.fetchall(query, (str(guild_id), max(1, min(limit, 25))))
    else:
        query = """
            SELECT user_id, total_exp, rpg_level, rpg_title, streak_days
            FROM users
            ORDER BY rpg_level DESC, total_exp DESC
            LIMIT $1
        """
        rows = await db.fetchall(query, (max(1, min(limit, 25)),))

    results = []
    for r in rows or []:
        lvl, cur_exp, next_exp, pct = calculate_level_from_exp(int(r.get("total_exp") or 0))
        results.append({
            "user_id": r["user_id"],
            "total_exp": int(r.get("total_exp") or 0),
            "level": int(r.get("rpg_level") or lvl),
            "title": r.get("rpg_title") or get_title_for_level(lvl),
            "streak_days": int(r.get("streak_days") or 0),
            "progress_pct": pct,
        })
    return results

