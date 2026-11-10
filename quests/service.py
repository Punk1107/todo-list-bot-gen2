"""
quests/service.py — Business logic for Server Co-op Quests and Guild Raids.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, List, Optional

from core.database import db
from gamification import rpg
from quests.models import GuildQuest, QuestParticipant

log = logging.getLogger(__name__)


async def create_quest(
    guild_id: str,
    creator_id: str,
    title: str,
    target_tasks: int,
    days: int = 7,
    min_tasks_per_member: int = 3,
    exp_reward: int = 500,
    badge_reward: str = "Guild Raid Hero",
    description: Optional[str] = None,
) -> GuildQuest:
    """Creates a new guild-level co-op quest."""
    clean_target = max(1, int(target_tasks))
    clean_days = max(1, min(int(days), 60))
    clean_min = max(1, int(min_tasks_per_member))
    clean_exp = max(50, int(exp_reward))

    now = datetime.now(timezone.utc)
    end_date = now + timedelta(days=clean_days)

    row = await db.fetchone(
        """
        INSERT INTO guild_quests (
            guild_id, creator_id, title, description, target_tasks,
            min_tasks_per_member, exp_reward, badge_reward,
            start_date, end_date, status, created_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'active', $9
        )
        RETURNING *
        """,
        (
            str(guild_id),
            str(creator_id),
            title.strip(),
            description.strip() if description else None,
            clean_target,
            clean_min,
            clean_exp,
            badge_reward.strip(),
            now,
            end_date,
        ),
    )
    db.query_cache.invalidate_table("guild_quests")
    return GuildQuest.from_row(row)


async def get_active_quest(guild_id: str) -> Optional[GuildQuest]:
    """Retrieves the current active quest for a guild, if any."""
    row = await db.fetchone(
        """
        SELECT * FROM guild_quests
        WHERE guild_id = $1 AND status = 'active' AND end_date > NOW()
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (str(guild_id),),
    )
    return GuildQuest.from_row(row) if row else None


async def list_guild_quests(guild_id: str, limit: int = 5) -> List[GuildQuest]:
    """Lists recent guild quests (both active and completed)."""
    rows = await db.fetchall(
        """
        SELECT * FROM guild_quests
        WHERE guild_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        (str(guild_id), max(1, min(limit, 20))),
    )
    return [GuildQuest.from_row(r) for r in rows] if rows else []


async def get_quest_participants(quest_id: int, limit: int = 10) -> List[QuestParticipant]:
    """Retrieves top contributors for a given quest."""
    rows = await db.fetchall(
        """
        SELECT * FROM guild_quest_participants
        WHERE quest_id = $1
        ORDER BY tasks_contributed DESC, last_contributed_at ASC
        LIMIT $2
        """,
        (int(quest_id), max(1, min(limit, 50))),
    )
    return [QuestParticipant.from_row(r) for r in rows] if rows else []


async def record_task_contribution(guild_id: str, user_id: str) -> Optional[dict[str, Any]]:
    """
    Called whenever a task is completed in a guild.
    Updates the active quest's counter and user contribution.
    If quest target is reached, distributes rewards!
    """
    quest = await get_active_quest(guild_id)
    if not quest:
        return None

    quest_id = quest.quest_id
    uid = str(user_id)

    # Increment quest completion
    updated_row = await db.fetchone(
        """
        UPDATE guild_quests
        SET completed_tasks = completed_tasks + 1
        WHERE quest_id = $1
        RETURNING *
        """,
        (quest_id,),
    )
    if not updated_row:
        return None

    # Upsert participant contribution
    await db.execute(
        """
        INSERT INTO guild_quest_participants (quest_id, user_id, tasks_contributed, last_contributed_at)
        VALUES ($1, $2, 1, NOW())
        ON CONFLICT (quest_id, user_id) DO UPDATE SET
            tasks_contributed = guild_quest_participants.tasks_contributed + 1,
            last_contributed_at = NOW()
        """,
        quest_id, uid,
    )

    db.query_cache.invalidate_table("guild_quests")
    db.query_cache.invalidate_table("guild_quest_participants")

    updated_quest = GuildQuest.from_row(updated_row)

    # Check if quest has just been completed!
    if updated_quest.completed_tasks >= updated_quest.target_tasks:
        await _complete_quest_and_award_rewards(updated_quest)
        return {
            "quest_id": quest_id,
            "just_completed": True,
            "title": updated_quest.title,
            "target": updated_quest.target_tasks,
        }

    return {
        "quest_id": quest_id,
        "just_completed": False,
        "current": updated_quest.completed_tasks,
        "target": updated_quest.target_tasks,
    }


async def _complete_quest_and_award_rewards(quest: GuildQuest) -> None:
    """Marks quest completed and distributes EXP and badges to qualifying participants."""
    await db.execute(
        "UPDATE guild_quests SET status = 'completed' WHERE quest_id = $1",
        quest.quest_id,
    )

    # Fetch all qualifying participants
    participants = await db.fetchall(
        """
        SELECT user_id, tasks_contributed
        FROM guild_quest_participants
        WHERE quest_id = $1 AND tasks_contributed >= $2 AND reward_claimed = FALSE
        """,
        (quest.quest_id, quest.min_tasks_per_member),
    )

    for p in participants or []:
        uid = str(p["user_id"])
        # Award bonus EXP
        try:
            await rpg.award_exp(uid, quest.exp_reward, reason=f"Co-op Quest '{quest.title}' Completed")
        except Exception as e:
            log.warning("Could not award quest EXP to %s: %s", uid, e)

        # Award badge
        try:
            await db.execute(
                """
                INSERT INTO user_achievements (user_id, type)
                VALUES ($1, $2) ON CONFLICT (user_id, type) DO NOTHING
                """,
                uid, quest.badge_reward,
            )
        except Exception as e:
            log.warning("Could not award quest badge to %s: %s", uid, e)

        # Mark claimed
        await db.execute(
            """
            UPDATE guild_quest_participants
            SET reward_claimed = TRUE
            WHERE quest_id = $1 AND user_id = $2
            """,
            quest.quest_id, uid,
        )

    db.query_cache.invalidate_table("guild_quests")
    db.query_cache.invalidate_table("guild_quest_participants")
    db.query_cache.invalidate_table("user_achievements")
    log.info("Quest #%d '%s' successfully completed by guild %s! Rewarded %d participants.",
             quest.quest_id, quest.title, quest.guild_id, len(participants or []))

