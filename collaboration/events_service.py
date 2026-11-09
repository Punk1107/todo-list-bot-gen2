"""
collaboration/events_service.py — Discord Scheduled Events Auto-Sync Engine.
Syncs strategic milestones and critical high-priority tasks (P6/P7) to Discord Guild Scheduled Events.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List

import discord

from core.database import db

log = logging.getLogger(__name__)


async def get_project_synced_events(project_id: int) -> List[Dict[str, Any]]:
    """Retrieve all synced event mappings for a project."""
    rows = await db.fetch_all(
        "SELECT * FROM project_scheduled_events WHERE project_id = $1",
        (project_id,),
    )
    return [dict(r) for r in rows]


async def save_synced_event(
    event_id: str,
    guild_id: str,
    project_id: int,
    entity_type: str,
    entity_id: int,
) -> None:
    """Save or update event mapping in database."""
    await db.execute(
        """
        INSERT INTO project_scheduled_events (event_id, guild_id, project_id, entity_type, entity_id)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (event_id) DO UPDATE SET
            synced_at = NOW()
        """,
        (event_id, guild_id, project_id, entity_type, entity_id),
    )
    db.query_cache.invalidate_table("project_scheduled_events")


async def sync_project_events(
    project_id: int,
    guild: discord.Guild,
) -> Dict[str, int]:
    """
    Scan project milestones and critical tasks (P6/P7) and synchronize with Discord Scheduled Events.
    Returns counts of created and updated events.
    """
    now = datetime.now(timezone.utc)
    created_count = 0
    updated_count = 0

    # 1. Fetch project details
    proj_row = await db.fetch_one(
        "SELECT project_id, name, emoji FROM projects WHERE project_id = $1 AND guild_id = $2",
        (project_id, str(guild.id)),
    )
    if not proj_row:
        return {"created": 0, "updated": 0}

    proj_prefix = f"[{proj_row['name'][:15]}]"

    # 2. Fetch existing mappings and guild events
    synced_mappings = await get_project_synced_events(project_id)
    mapping_by_entity: Dict[tuple[str, int], str] = {
        (m["entity_type"], m["entity_id"]): m["event_id"] for m in synced_mappings
    }
    guild_events: Dict[str, discord.ScheduledEvent] = {
        str(ev.id): ev for ev in guild.scheduled_events
    }

    # 3. Fetch Milestones
    milestone_rows = await db.fetch_all(
        """
        SELECT milestone_id, title, target_date
        FROM project_milestones
        WHERE project_id = $1 AND status = 'active'
        """,
        (project_id,),
    )

    for m in milestone_rows:
        mid = m["milestone_id"]
        title = m["title"]
        target_dt: datetime = m["target_date"]
        if target_dt.tzinfo is None:
            target_dt = target_dt.replace(tzinfo=timezone.utc)

        # Scheduled events must start in future (at least +2 mins)
        start_time = max(target_dt, now + timedelta(minutes=2))
        end_time = start_time + timedelta(hours=1)
        event_name = f"{proj_prefix} 🎯 {title[:75]}"
        event_desc = f"Strategic Milestone for Project #{project_id} ({proj_row['name']})"

        mapped_event_id = mapping_by_entity.get(("milestone", mid))
        existing_event = guild_events.get(mapped_event_id) if mapped_event_id else None

        if existing_event and existing_event.status == discord.EventStatus.scheduled:
            try:
                await existing_event.edit(
                    name=event_name,
                    start_time=start_time,
                    end_time=end_time,
                    description=event_desc,
                )
                updated_count += 1
            except Exception as exc:
                log.warning("Could not update scheduled event %s: %s", existing_event.id, exc)
        elif not mapped_event_id or not existing_event:
            try:
                new_ev = await guild.create_scheduled_event(
                    name=event_name,
                    start_time=start_time,
                    end_time=end_time,
                    entity_type=discord.EntityType.external,
                    privacy_level=discord.PrivacyLevel.guild_only,
                    location="To-Do List Bot Workboard",
                    description=event_desc,
                    reason=f"Auto-sync milestone #{mid} from project #{project_id}",
                )
                await save_synced_event(str(new_ev.id), str(guild.id), project_id, "milestone", mid)
                created_count += 1
            except Exception as exc:
                log.warning("Could not create scheduled event for milestone %s: %s", mid, exc)

    # 4. Fetch Critical Tasks (P6 / P7)
    task_rows = await db.fetch_all(
        """
        SELECT task_id, task, priority, deadline
        FROM tasks
        WHERE project_id = $1 AND priority >= 6 AND status != 'Completed'
          AND is_deleted = FALSE AND deadline IS NOT NULL
        """,
        (project_id,),
    )

    for t_item in task_rows:
        tid = t_item["task_id"]
        t_name = t_item["task"]
        prio = t_item["priority"]
        deadline: datetime = t_item["deadline"]
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)

        start_time = max(deadline, now + timedelta(minutes=2))
        end_time = start_time + timedelta(hours=1)
        event_name = f"{proj_prefix} 🔴 P{prio}: {t_name[:70]}"
        event_desc = f"Critical Deadline for Task #{tid} in Project #{project_id}"

        mapped_event_id = mapping_by_entity.get(("task", tid))
        existing_event = guild_events.get(mapped_event_id) if mapped_event_id else None

        if existing_event and existing_event.status == discord.EventStatus.scheduled:
            try:
                await existing_event.edit(
                    name=event_name,
                    start_time=start_time,
                    end_time=end_time,
                    description=event_desc,
                )
                updated_count += 1
            except Exception as exc:
                log.warning("Could not update scheduled event %s: %s", existing_event.id, exc)
        elif not mapped_event_id or not existing_event:
            try:
                new_ev = await guild.create_scheduled_event(
                    name=event_name,
                    start_time=start_time,
                    end_time=end_time,
                    entity_type=discord.EntityType.external,
                    privacy_level=discord.PrivacyLevel.guild_only,
                    location="To-Do List Bot Workboard",
                    description=event_desc,
                    reason=f"Auto-sync critical task #{tid} from project #{project_id}",
                )
                await save_synced_event(str(new_ev.id), str(guild.id), project_id, "task", tid)
                created_count += 1
            except Exception as exc:
                log.warning("Could not create scheduled event for task %s: %s", tid, exc)

    return {"created": created_count, "updated": updated_count}
