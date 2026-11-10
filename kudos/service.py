"""
kudos/service.py — Business logic for Peer Kudos & Team Gratitude.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, List, Optional

from core.database import db
from gamification.rpg import EXP_KUDOS, award_exp
from kudos.models import PeerKudos

log = logging.getLogger(__name__)

DAILY_KUDOS_LIMIT = 5


async def send_kudos(
    guild_id: str,
    from_user_id: str,
    to_user_id: str,
    reason: str,
    task_id: Optional[int] = None,
) -> PeerKudos:
    """
    Sends peer appreciation/kudos to a teammate.
    Enforces self-send prevention and a daily rate limit of 5 kudos/day.
    Awards +30 RPG EXP to the recipient.
    """
    f_uid = str(from_user_id)
    t_uid = str(to_user_id)

    if f_uid == t_uid:
        raise ValueError("Cannot send kudos to yourself.")

    clean_reason = reason.strip()
    if not clean_reason:
        raise ValueError("A reason for the kudos must be provided.")

    # Check daily rate limit (24 hours)
    one_day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    sent_count_row = await db.fetchone(
        """
        SELECT COUNT(*) AS count
        FROM peer_kudos
        WHERE from_user_id = $1 AND created_at >= $2
        """,
        (f_uid, one_day_ago),
    )
    sent_count = int(sent_count_row["count"]) if sent_count_row else 0
    if sent_count >= DAILY_KUDOS_LIMIT:
        raise ValueError(f"Daily kudos limit reached ({DAILY_KUDOS_LIMIT}/day). Please send more tomorrow!")

    # Verify task if provided
    task_title: Optional[str] = None
    if task_id:
        t_row = await db.fetchone("SELECT task FROM tasks WHERE task_id = $1", (int(task_id),))
        if t_row:
            task_title = t_row["task"]

    # Insert kudos
    row = await db.fetchone(
        """
        INSERT INTO peer_kudos (guild_id, from_user_id, to_user_id, task_id, reason, points, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, NOW())
        RETURNING *
        """,
        (str(guild_id), f_uid, t_uid, int(task_id) if task_id else None, clean_reason, EXP_KUDOS),
    )
    db.query_cache.invalidate_table("peer_kudos")

    # Award +30 EXP to recipient
    try:
        await award_exp(t_uid, EXP_KUDOS, reason=f"Received Kudos from <@{f_uid}>")
    except Exception as exc:
        log.warning("Could not award kudos EXP to %s: %s", t_uid, exc)

    merged = dict(row) if row else {}
    if task_title:
        merged["task_title"] = task_title

    return PeerKudos.from_row(merged)


async def get_kudos_leaderboard(
    guild_id: str,
    period: str = "month",
    limit: int = 10,
) -> List[dict[str, Any]]:
    """
    Retrieves the gratitude leaderboard for a guild.
    period: 'month' (last 30 days) or 'all_time'.
    """
    params: list[Any] = [str(guild_id)]
    where_sql = "WHERE guild_id = $1"

    if period == "month":
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        params.append(thirty_days_ago)
        where_sql += f" AND created_at >= ${len(params)}"

    params.append(max(1, min(limit, 25)))
    limit_ph = f"${len(params)}"

    query = f"""
        SELECT to_user_id AS user_id,
               COUNT(*) AS kudos_count,
               SUM(points) AS total_points
        FROM peer_kudos
        {where_sql}
        GROUP BY to_user_id
        ORDER BY kudos_count DESC, total_points DESC
        LIMIT {limit_ph}
    """
    rows = await db.fetchall(query, *params)
    return [
        {
            "user_id": r["user_id"],
            "kudos_count": int(r["kudos_count"]),
            "total_points": int(r["total_points"] or 0),
        }
        for r in rows or []
    ]


async def get_user_recent_kudos(
    user_id: str,
    days: int = 7,
    limit: int = 10,
) -> List[dict[str, Any]]:
    """Retrieves recent kudos received by a user (used by Weekly Retrospective)."""
    since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    rows = await db.fetchall(
        """
        SELECT pk.*, t.task AS task_title
        FROM peer_kudos pk
        LEFT JOIN tasks t ON pk.task_id = t.task_id
        WHERE pk.to_user_id = $1 AND pk.created_at >= $2
        ORDER BY pk.created_at DESC
        LIMIT $3
        """,
        (str(user_id), since, max(1, min(limit, 25))),
    )
    return [
        {
            "kudos_id": r["kudos_id"],
            "from_user_id": r["from_user_id"],
            "reason": r["reason"],
            "points": int(r.get("points") or 30),
            "task_id": r.get("task_id"),
            "task_title": r.get("task_title"),
            "created_at": r["created_at"],
        }
        for r in rows or []
    ]

