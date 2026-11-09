"""
standup/service.py — Asynchronous Daily Standup Service layer.
"""
from __future__ import annotations

from datetime import date
import logging
import re
from typing import List, Optional

from core.database import db
from standup.models import DailyStandupEntry, StandupConfig

log = logging.getLogger(__name__)

TASK_REF_RE = re.compile(r"#(\d+)")


async def save_standup_config(
    guild_id: str,
    channel_id: str,
    standup_time: str,
    user_id: str,
) -> StandupConfig:
    """Save or update guild standup channel and daily prompt time."""
    row = await db.fetch_one(
        """
        INSERT INTO standup_configs (guild_id, channel_id, standup_time, is_active, created_by)
        VALUES ($1, $2, $3, TRUE, $4)
        ON CONFLICT (guild_id) DO UPDATE SET
            channel_id = EXCLUDED.channel_id,
            standup_time = EXCLUDED.standup_time,
            is_active = TRUE
        RETURNING *
        """,
        (guild_id, channel_id, standup_time, user_id),
    )
    db.query_cache.invalidate_table("standup_configs")
    return StandupConfig.from_row(row)  # type: ignore[arg-type]


async def get_standup_config(guild_id: str) -> Optional[StandupConfig]:
    """Retrieve active standup configuration for a guild."""
    row = await db.fetch_one(
        "SELECT * FROM standup_configs WHERE guild_id = $1 AND is_active = TRUE",
        (guild_id,),
    )
    return StandupConfig.from_row(row) if row else None


async def get_all_active_standup_configs() -> List[StandupConfig]:
    """Retrieve all active standup configs across all guilds for scheduler."""
    rows = await db.fetch_all("SELECT * FROM standup_configs WHERE is_active = TRUE")
    return [StandupConfig.from_row(r) for r in rows]


async def submit_standup(
    guild_id: str,
    user_id: str,
    yesterday: str,
    today: str,
    blockers: Optional[str] = None,
) -> DailyStandupEntry:
    """Submit daily standup answers (upsert per day)."""
    today_date = date.today()
    clean_blockers = blockers.strip() if blockers and blockers.strip() else None

    row = await db.fetch_one(
        """
        INSERT INTO daily_standups (guild_id, user_id, standup_date, yesterday_text, today_text, blockers_text)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (guild_id, user_id, standup_date) DO UPDATE SET
            yesterday_text = EXCLUDED.yesterday_text,
            today_text = EXCLUDED.today_text,
            blockers_text = EXCLUDED.blockers_text,
            submitted_at = NOW()
        RETURNING *
        """,
        (guild_id, user_id, today_date, yesterday.strip(), today.strip(), clean_blockers),
    )
    db.query_cache.invalidate_table("daily_standups")
    return DailyStandupEntry.from_row(row)  # type: ignore[arg-type]


async def get_daily_standups(
    guild_id: str,
    standup_date: Optional[date] = None,
) -> List[DailyStandupEntry]:
    """Retrieve all standup entries for a guild on a given date."""
    target_date = standup_date or date.today()
    rows = await db.fetch_all(
        """
        SELECT * FROM daily_standups
        WHERE guild_id = $1 AND standup_date = $2
        ORDER BY submitted_at ASC
        """,
        (guild_id, target_date),
    )
    return [DailyStandupEntry.from_row(r) for r in rows]


def format_standup_text_with_tasks(text: str) -> str:
    """Highlights task ID mentions such as #45 in bold code spans."""
    return TASK_REF_RE.sub(r"`#\1`", text)

