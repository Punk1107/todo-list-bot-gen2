"""
realtime/notifications.py — Discord Announcement Embed Builders for Realtime Events

Builds rich Discord embeds that are posted to the project's notification channel
when key events occur (task completed, task assigned, new attachment uploaded).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import discord

log = logging.getLogger(__name__)

# Progress bar renderer (same logic as collaboration.views)
def _progress_bar(pct: float, width: int = 14) -> str:
    filled = int(round(pct / 100 * width))
    bar = "▰" * filled + "▱" * (width - filled)
    return f"`{bar}` **{pct:.1f}%**"


def build_task_completed_embed(
    *,
    task_id: int,
    task_name: str,
    project_id: int,
    project_name: str,
    project_emoji: str,
    project_color: str,
    actor_id: str,
    progress_pct: Optional[float] = None,
    done_count: Optional[int] = None,
    total: Optional[int] = None,
    lang: str = "en",
) -> discord.Embed:
    """Celebratory embed when a shared-project task is completed."""
    from locales.i18n import t

    color = int(project_color.lstrip("#"), 16) if project_color.startswith("#") else 0x57F287

    embed = discord.Embed(
        title=t("rt_task_completed_title", lang),
        description=t(
            "rt_task_completed_body", lang,
            user=f"<@{actor_id}>",
            task_id=task_id,
            task_name=task_name[:80],
            project_emoji=project_emoji,
            project_name=project_name,
        ),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    if progress_pct is not None:
        bar = _progress_bar(progress_pct)
        label = (
            f"{bar}  ({done_count}/{total} tasks)" if done_count is not None and total is not None
            else bar
        )
        embed.add_field(name=t("rt_progress_title", lang), value=label, inline=False)

    embed.set_footer(text=f"{project_emoji} Project #{project_id} · To-Do List Bot Gen 2")
    return embed


def build_task_claimed_embed(
    *,
    task_id: int,
    task_name: str,
    project_name: str,
    project_emoji: str,
    project_color: str,
    claimer_id: str,
    lang: str = "en",
) -> discord.Embed:
    """Embed when a member claims/self-assigns a task."""
    from locales.i18n import t

    color = int(project_color.lstrip("#"), 16) if project_color.startswith("#") else 0x5865F2

    embed = discord.Embed(
        title=t("rt_task_claimed_title", lang),
        description=t(
            "rt_task_claimed_body", lang,
            user=f"<@{claimer_id}>",
            task_id=task_id,
            task_name=task_name[:80],
            project_emoji=project_emoji,
            project_name=project_name,
        ),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text=f"{project_emoji} {project_name} · To-Do List Bot Gen 2")
    return embed


def build_attachment_uploaded_embed(
    *,
    task_id: int,
    task_name: str,
    file_name: str,
    file_size_human: str,
    public_url: str,
    uploader_id: str,
    is_image: bool,
    lang: str = "en",
) -> discord.Embed:
    """Embed notification when a file attachment is uploaded to a task."""
    from locales.i18n import t

    embed = discord.Embed(
        title=t("rt_attachment_uploaded_title", lang),
        description=t(
            "rt_attachment_uploaded_body", lang,
            user=f"<@{uploader_id}>",
            file_name=file_name,
            file_size=file_size_human,
            task_id=task_id,
            task_name=task_name[:60],
        ),
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc),
    )
    if is_image:
        embed.set_image(url=public_url)
    else:
        embed.add_field(name=t("rt_download_title", lang), value=f"[{file_name}]({public_url})", inline=False)
    embed.set_footer(text="To-Do List Bot Gen 2")
    return embed
