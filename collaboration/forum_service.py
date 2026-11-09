"""
collaboration/forum_service.py — Discord Forum Channel Kanban Integration.
Transforms a Discord Forum Channel into a real-time Kanban Task Board using Forum Tags and Threaded Posts.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import discord

from core.database import db

log = logging.getLogger(__name__)

TAG_NAMES = {
    "Pending": "⏳ Pending",
    "In_Progress": "🏃 In Progress",
    "Completed": "✅ Completed",
    "Critical": "🔴 P6/P7",
}


async def get_project_forum_config(project_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve forum channel binding for a project."""
    row = await db.fetch_one(
        "SELECT * FROM project_forum_configs WHERE project_id = $1 AND is_active = TRUE",
        (project_id,),
    )
    return dict(row) if row else None


async def set_project_forum_config(
    project_id: int,
    guild_id: str,
    forum_channel_id: str,
) -> None:
    """Save or update forum channel binding for a project."""
    await db.execute(
        """
        INSERT INTO project_forum_configs (project_id, guild_id, forum_channel_id, is_active)
        VALUES ($1, $2, $3, TRUE)
        ON CONFLICT (project_id) DO UPDATE SET
            guild_id = EXCLUDED.guild_id,
            forum_channel_id = EXCLUDED.forum_channel_id,
            is_active = TRUE
        """,
        (project_id, guild_id, forum_channel_id),
    )
    db.query_cache.invalidate_table("project_forum_configs")


async def ensure_forum_kanban_tags(
    forum_channel: discord.ForumChannel,
) -> Dict[str, discord.ForumTag]:
    """
    Ensure the standard 4 Kanban tags exist on the Forum Channel.
    Creates missing tags if bot has manage_channels permission.
    Returns mapping from status key ('Pending', 'In_Progress', 'Completed', 'Critical') to ForumTag.
    """
    tag_map: Dict[str, discord.ForumTag] = {}
    existing_by_name = {t.name.lower(): t for t in forum_channel.available_tags}

    for key, target_name in TAG_NAMES.items():
        matched = existing_by_name.get(target_name.lower())
        if matched:
            tag_map[key] = matched
        else:
            # Attempt to create tag if missing and capacity allows (max 20 tags per forum)
            if len(forum_channel.available_tags) < 20:
                try:
                    new_tag = await forum_channel.create_tag(name=target_name)
                    tag_map[key] = new_tag
                except Exception as exc:
                    log.warning("Could not create tag '%s' in forum %s: %s", target_name, forum_channel.id, exc)

    return tag_map


async def sync_task_to_forum(
    task_id: int,
    project_id: int,
    bot: discord.Client,
) -> Optional[str]:
    """
    Sync a project task to its corresponding Forum Post / Thread.
    Updates tags in real-time or creates a new post if not present.
    Returns the thread jump URL if synced.
    """
    forum_cfg = await get_project_forum_config(project_id)
    if not forum_cfg:
        return None

    forum_channel = bot.get_channel(int(forum_cfg["forum_channel_id"]))
    if not isinstance(forum_channel, discord.ForumChannel):
        return None

    task_row = await db.fetch_one(
        "SELECT task_id, task, status, priority, description, deadline FROM tasks WHERE task_id = $1",
        (task_id,),
    )
    if not task_row:
        return None

    tag_map = await ensure_forum_kanban_tags(forum_channel)
    task_status = task_row["status"]
    priority = task_row.get("priority", 0)

    # Determine applied tags
    applied_tags: List[discord.ForumTag] = []
    status_tag = tag_map.get(task_status)
    if status_tag:
        applied_tags.append(status_tag)
    if priority >= 6 and "Critical" in tag_map:
        applied_tags.append(tag_map["Critical"])

    # Check existing post mapping
    post_row = await db.fetch_one(
        "SELECT thread_id FROM task_forum_posts WHERE task_id = $1",
        (task_id,),
    )

    thread: Optional[discord.Thread] = None
    if post_row:
        thread_id = int(post_row["thread_id"])
        thread = bot.get_channel(thread_id) or await bot.fetch_channel(thread_id)  # type: ignore[assignment]

    if thread and isinstance(thread, discord.Thread):
        # Update existing post tags and name
        try:
            name_str = f"#{task_id} {task_row['task'][:80]}"
            await thread.edit(name=name_str, applied_tags=applied_tags)
            return thread.jump_url
        except Exception as exc:
            log.warning("Could not edit forum thread %s: %s", thread.id, exc)
    else:
        # Create new Forum Post
        try:
            name_str = f"#{task_id} {task_row['task'][:80]}"
            content_lines = [
                f"📋 **Task #{task_id}: {task_row['task']}**",
                f"• **Status:** `{task_status}`",
                f"• **Priority:** `P{priority}`",
            ]
            if task_row.get("deadline"):
                ts = int(task_row["deadline"].timestamp())
                content_lines.append(f"• **Deadline:** <t:{ts}:D> (<t:{ts}:R>)")
            if task_row.get("description"):
                content_lines.append(f"\n**Details:**\n{task_row['description']}")

            result = await forum_channel.create_thread(
                name=name_str,
                content="\n".join(content_lines),
                applied_tags=applied_tags,
                reason=f"Kanban mode: auto-create task #{task_id}",
            )
            created_thread = result[0] if isinstance(result, tuple) else result
            await db.execute(
                """
                INSERT INTO task_forum_posts (task_id, thread_id, forum_channel_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (task_id) DO UPDATE SET
                    thread_id = EXCLUDED.thread_id,
                    forum_channel_id = EXCLUDED.forum_channel_id,
                    synced_at = NOW()
                """,
                (task_id, str(created_thread.id), str(forum_channel.id)),
            )
            db.query_cache.invalidate_table("task_forum_posts")
            return created_thread.jump_url
        except Exception as exc:
            log.warning("Could not create forum thread for task %s: %s", task_id, exc)

    return None

