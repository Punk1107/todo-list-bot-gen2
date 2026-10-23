"""Persistence and business rules for streaks, achievements, and leaderboards."""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytz

from core.database import db

log = logging.getLogger(__name__)

BADGE_KEYS = {
    "early_bird": "habit_badge_early_bird",
    "speed_demon": "habit_badge_speed_demon",
    "p7_slayer": "habit_badge_p7_slayer",
    "inbox_zero": "habit_badge_inbox_zero",
}


def _next_streak(current: int, last_day: Optional[date], completion_day: date) -> int:
    if last_day == completion_day:
        return current
    if last_day == completion_day - timedelta(days=1):
        return current + 1
    return 1


def _productivity_score(
    completed: int, on_time: int, deadline_count: int,
    active_days: int, p7_completed: int,
) -> float:
    if completed <= 0:
        return 0.0
    on_time_rate = on_time / deadline_count if deadline_count else 0
    return round(
        40 * on_time_rate
        + 30 * min(completed / 6, 1)
        + 20 * min(active_days / 5, 1)
        + 10 * min(p7_completed, 1),
        1,
    )


def _deadline_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        log.warning("Ignoring unparseable task deadline in completion snapshot: %r", value)
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def _award(conn: Any, user_id: str, badge: str) -> bool:
    row = await conn.fetchrow(
        """INSERT INTO user_achievements (user_id, type)
           VALUES ($1, $2) ON CONFLICT (user_id, type) DO NOTHING
           RETURNING achievement_id""",
        user_id, badge,
    )
    return row is not None


async def _record_completion(
    conn: Any,
    task: Any,
    user_id: str,
    completed_at: datetime,
) -> list[str]:
    """Snapshot a completion and update the user's local-calendar streak atomically."""
    completed_at = completed_at.astimezone(timezone.utc)
    deadline = _deadline_datetime(task["deadline"])

    await conn.execute(
        "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING",
        user_id,
    )
    await conn.execute(
        """INSERT INTO task_completion_events
           (task_id, user_id, guild_id, project_id, task_title, priority, deadline, completed_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
        task["task_id"], user_id, task["guild_id"], task["project_id"],
        task["task"], task["priority"], deadline, completed_at,
    )

    user = await conn.fetchrow(
        """SELECT timezone, streak_days, streak_last_completion
           FROM users WHERE user_id=$1 FOR UPDATE""",
        user_id,
    )
    if user is None:
        raise RuntimeError(f"Completion actor {user_id} has no user profile")

    tz_name = user["timezone"] or "UTC"
    try:
        user_tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        log.warning("Unknown timezone %r for user %s; using UTC for streak", tz_name, user_id)
        user_tz = timezone.utc
    local_day = completed_at.astimezone(user_tz).date()
    last_day = user["streak_last_completion"]
    streak = int(user["streak_days"] or 0)
    if last_day != local_day:
        streak = _next_streak(streak, last_day, local_day)
        await conn.execute(
            """UPDATE users SET streak_days=$1, streak_last_completion=$2
               WHERE user_id=$3""",
            streak, local_day, user_id,
        )

    badges: list[str] = []
    local_time = completed_at.astimezone(user_tz).time()
    if local_time < time(9, 0):
        badges.append("early_bird")
    if deadline is not None and deadline - completed_at >= timedelta(hours=24):
        badges.append("speed_demon")
    if int(task["priority"] or 0) == 7:
        badges.append("p7_slayer")

    # /today and /overdue both list owner-owned Pending tasks; together they cover
    # every deadline before the end of this local day, including overdue work.
    end_of_local_day = datetime.combine(
        local_day + timedelta(days=1), time.min, tzinfo=user_tz
    ).astimezone(timezone.utc)
    remaining = await conn.fetchval(
        """SELECT EXISTS (
             SELECT 1 FROM tasks
             WHERE owner_id=$1 AND status='Pending' AND is_deleted=FALSE
               AND CASE
                     WHEN deadline ~ '^\\d{4}-\\d{2}-\\d{2}'
                     THEN deadline::timestamptz < $2
                     ELSE TRUE
                   END
           )""",
        user_id, end_of_local_day,
    )
    if not remaining:
        badges.append("inbox_zero")

    awarded: list[str] = []
    for badge in badges:
        if await _award(conn, user_id, badge):
            awarded.append(badge)
    return awarded


async def complete_personal_task(task_id: int, user_id: str) -> Optional[list[str]]:
    """Complete an owned task and record gamification data in the same transaction."""
    async with db.acquire() as conn:
        async with conn.transaction():
            task = await conn.fetchrow(
                """UPDATE tasks
                   SET status='Completed', completed_at=NOW(), updated_at=NOW()
                   WHERE task_id=$1 AND owner_id=$2
                     AND status IN ('Pending','In_Progress')
                     AND is_deleted = FALSE
                   RETURNING task_id, task, priority, deadline, project_id, guild_id,
                             completed_at""",
                task_id, user_id,
            )
            if task is None:
                return None
            completed_at = task["completed_at"]
            if completed_at.tzinfo is None:
                completed_at = completed_at.replace(tzinfo=timezone.utc)
            awarded = await _record_completion(conn, task, user_id, completed_at)
    db.invalidate_stats(user_id)
    db.query_cache.invalidate_tables([
        "tasks", "users", "task_completion_events", "user_achievements",
    ])
    return awarded


async def complete_shared_task(
    task_id: int, project_id: int, guild_id: str, user_id: str
) -> Optional[list[str]]:
    """Complete a guild-scoped shared task for an authorized actor."""
    async with db.acquire() as conn:
        async with conn.transaction():
            task = await conn.fetchrow(
                """UPDATE tasks
                   SET status='Completed', completed_at=NOW(), updated_at=NOW()
                   WHERE task_id=$1 AND project_id=$2 AND guild_id=$3
                     AND status IN ('Pending','In_Progress')
                   RETURNING task_id, task, priority, deadline, project_id, guild_id,
                             completed_at""",
                task_id, project_id, guild_id,
            )
            if task is None:
                return None
            completed_at = task["completed_at"]
            if completed_at.tzinfo is None:
                completed_at = completed_at.replace(tzinfo=timezone.utc)
            awarded = await _record_completion(conn, task, user_id, completed_at)
    db.invalidate_stats(user_id)
    db.query_cache.invalidate_tables([
        "tasks", "users", "task_completion_events", "user_achievements",
    ])
    return awarded


async def complete_shared_project_tasks(
    project_id: int, guild_id: str, actor_id: str
) -> int:
    """Record bulk completions from the authorized project-completion action."""
    async with db.acquire() as conn:
        async with conn.transaction():
            tasks = await conn.fetch(
                """UPDATE tasks
                   SET status='Completed', completed_at=NOW(), updated_at=NOW()
                   WHERE project_id=$1 AND guild_id=$2
                     AND status IN ('Pending','In_Progress')
                   RETURNING task_id, task, priority, deadline, project_id, guild_id,
                             completed_at, owner_id""",
                project_id, guild_id,
            )
            if tasks:
                assignments = await conn.fetch(
                    """SELECT DISTINCT user_id FROM task_assignments
                       WHERE task_id = ANY($1::int[])""",
                    [task["task_id"] for task in tasks],
                )
                for task in tasks:
                    completed_at = task["completed_at"]
                    if completed_at.tzinfo is None:
                        completed_at = completed_at.replace(tzinfo=timezone.utc)
                    await _record_completion(conn, task, actor_id, completed_at)
                    db.invalidate_stats(task["owner_id"])
                for assignment in assignments:
                    db.invalidate_stats(assignment["user_id"])
    db.invalidate_stats(actor_id)
    db.query_cache.invalidate_tables([
        "tasks", "task_assignments", "users",
        "task_completion_events", "user_achievements",
    ])
    return len(tasks)


async def get_habit_summary(user_id: str) -> dict[str, Any]:
    row = await db.afetchone(
        """SELECT timezone, streak_days, streak_last_completion
           FROM users WHERE user_id=$1""",
        (user_id,),
    )
    if row is None:
        return {"streak_days": 0, "today_completions": 0, "badges": []}
    tz_name = row["timezone"] or "UTC"
    try:
        user_tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        log.warning("Unknown timezone %r for user %s; using UTC", tz_name, user_id)
        user_tz = pytz.UTC
    now = datetime.now(timezone.utc).astimezone(user_tz)
    today = now.date()
    last_day = row["streak_last_completion"]
    streak = int(row["streak_days"] or 0)
    if last_day is None or last_day < today - timedelta(days=1):
        streak = 0
    start = user_tz.localize(datetime.combine(today, time.min)).astimezone(pytz.UTC)
    end = user_tz.localize(
        datetime.combine(today + timedelta(days=1), time.min)
    ).astimezone(pytz.UTC)
    completions = await db.afetchone(
        """SELECT COUNT(*) AS count FROM task_completion_events
           WHERE user_id=$1 AND guild_id IS NULL
             AND completed_at >= $2 AND completed_at < $3""",
        (user_id, start, end),
    )
    achievements = await db.afetchall(
        "SELECT type, awarded_at FROM user_achievements WHERE user_id=$1 ORDER BY awarded_at DESC",
        (user_id,),
    )
    return {
        "streak_days": streak,
        "today_completions": int(completions["count"] or 0) if completions else 0,
        "badges": [dict(item) for item in (achievements or [])],
    }


async def get_guild_leaderboard(guild_id: str, period: str) -> list[dict[str, Any]]:
    if period not in {"week", "month"}:
        raise ValueError("period must be 'week' or 'month'")
    since = datetime.now(timezone.utc) - timedelta(days=7 if period == "week" else 30)
    rows = await db.afetchall(
        """SELECT user_id, COUNT(*) AS completed,
                  COUNT(*) FILTER (WHERE deadline IS NOT NULL) AS deadline_count,
                  COUNT(*) FILTER (WHERE deadline IS NOT NULL
                                    AND completed_at <= deadline) AS on_time,
                  COUNT(DISTINCT (completed_at AT TIME ZONE 'UTC')::date) AS active_days,
                  COUNT(*) FILTER (WHERE priority=7) AS p7_completed
           FROM task_completion_events
           WHERE guild_id=$1 AND completed_at >= $2
           GROUP BY user_id""",
        (guild_id, since),
    )
    result = []
    for row in rows or []:
        completed = int(row["completed"])
        on_time = int(row["on_time"])
        deadline_count = int(row["deadline_count"])
        active_days = int(row["active_days"])
        p7_completed = int(row["p7_completed"])
        result.append({
            "user_id": row["user_id"],
            "completed": completed,
            "on_time": on_time,
            "score": _productivity_score(
                completed, on_time, deadline_count, active_days, p7_completed
            ),
        })
    return sorted(result, key=lambda item: (-item["score"], -item["completed"], item["user_id"]))


async def claim_streak_reminder(user_id: str, local_day: date) -> bool:
    """Atomically mark the date before sending so restarts cannot duplicate a DM."""
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE users SET streak_reminder_date=$2
               WHERE user_id=$1 AND notify_enabled=1
                 AND streak_reminder_date IS DISTINCT FROM $2
               RETURNING user_id""",
            user_id, local_day,
        )
    if row is not None:
        db.query_cache.invalidate_tables(["users"])
    return row is not None
