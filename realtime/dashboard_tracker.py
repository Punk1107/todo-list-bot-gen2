"""
realtime/dashboard_tracker.py — Live Project Dashboard Registry & Debounced Updater

The DashboardTracker keeps an in-memory registry mapping project_id to the
Discord message that is currently showing that project's live dashboard.

When the Realtime dispatcher fires for a project, the tracker:
  1. Notes that project needs an update.
  2. Waits `debounce_sec` (default 1.5 s) to coalesce rapid successive changes.
  3. Fetches fresh stats and edits the original Discord message in-place.

This means users never need to run /project view again — the dashboard
message updates itself automatically.

Thread-safety: all mutation is done inside the asyncio event loop; no locks needed.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import discord

log = logging.getLogger(__name__)


@dataclass
class _DashboardEntry:
    channel_id: int
    message_id: int
    project_id: int
    guild_id:   str
    lang:       str


class DashboardTracker:
    """
    Registry of live dashboard messages per project.

    Typical usage:
        # When a dashboard is opened:
        dashboard_tracker.register(project_id, guild_id, channel_id, message_id, lang)

        # Called automatically by dispatcher when a task changes in that project:
        await dashboard_tracker.schedule_update(bot, project_id)
    """

    def __init__(self, debounce_sec: float = 1.5) -> None:
        self._entries: dict[int, _DashboardEntry] = {}  # project_id -> entry
        self._pending_updates: dict[int, asyncio.Task] = {}  # project_id -> debounce task
        self._debounce_sec = debounce_sec

    # ── Registration ───────────────────────────────────────────────────────────

    def register(
        self,
        project_id: int,
        guild_id: str,
        channel_id: int,
        message_id: int,
        lang: str = "en",
    ) -> None:
        """Register a Discord message as the live dashboard for a project."""
        self._entries[project_id] = _DashboardEntry(
            channel_id=channel_id,
            message_id=message_id,
            project_id=project_id,
            guild_id=guild_id,
            lang=lang,
        )
        log.debug(
            "Dashboard registered: project=%d  chan=%d  msg=%d",
            project_id, channel_id, message_id,
        )

    def unregister(self, project_id: int) -> None:
        """Remove a project's dashboard tracking entry."""
        self._entries.pop(project_id, None)
        task = self._pending_updates.pop(project_id, None)
        if task and not task.done():
            task.cancel()

    def get(self, project_id: int) -> Optional[_DashboardEntry]:
        return self._entries.get(project_id)

    # ── Update scheduling (debounced) ──────────────────────────────────────────

    def schedule_update(self, bot: "discord.Client", project_id: int) -> None:
        """
        Schedule a debounced dashboard refresh.
        If another update is already scheduled for this project, it is cancelled
        and replaced — effectively collapsing rapid successive changes.
        """
        # Cancel existing pending update if any
        existing = self._pending_updates.get(project_id)
        if existing and not existing.done():
            existing.cancel()

        task = asyncio.create_task(
            self._debounced_update(bot, project_id),
            name=f"dashboard_update_{project_id}",
        )
        self._pending_updates[project_id] = task

    async def _debounced_update(self, bot: "discord.Client", project_id: int) -> None:
        """Wait debounce_sec then perform the actual Discord message edit."""
        try:
            await asyncio.sleep(self._debounce_sec)
            await self._do_update(bot, project_id)
        except asyncio.CancelledError:
            pass  # A newer update will run instead
        except Exception as exc:
            log.error(
                "Dashboard update error for project %d: %s", project_id, exc, exc_info=True
            )
        finally:
            self._pending_updates.pop(project_id, None)

    async def _do_update(self, bot: "discord.Client", project_id: int) -> None:
        """Fetch fresh stats and edit the registered dashboard message."""
        entry = self._entries.get(project_id)
        if not entry:
            return  # Dashboard was unregistered while waiting

        try:
            channel = bot.get_channel(entry.channel_id)
            if channel is None:
                channel = await bot.fetch_channel(entry.channel_id)

            message = channel.get_partial_message(entry.message_id)  # type: ignore[union-attr]
        except Exception as exc:
            log.warning(
                "Dashboard update: could not get message project=%d: %s",
                project_id, exc,
            )
            self.unregister(project_id)
            return

        # Import here to avoid circular imports at module level
        from collaboration import service as collab_service
        from collaboration.views import build_project_dashboard_embed, ProjectDashboardView

        try:
            stats = await collab_service.get_project_stats(entry.project_id, entry.guild_id)
        except collab_service.ProjectNotFound:
            self.unregister(project_id)
            return
        except Exception as exc:
            log.warning("Dashboard update: failed to fetch stats project=%d: %s", project_id, exc)
            return

        embed = build_project_dashboard_embed(stats, entry.lang)

        # Reconstruct a placeholder user so ProjectDashboardView can be re-used.
        # The "user" is only needed for admin-only buttons; dashboard embeds work fine with None.
        view = ProjectDashboardView(entry.project_id, entry.guild_id, entry.lang, user=None)  # type: ignore[arg-type]

        try:
            await message.edit(embed=embed, view=view)
            log.info(
                "Dashboard auto-updated: project=%d  msg=%d",
                project_id, entry.message_id,
            )
        except Exception as exc:
            log.warning(
                "Dashboard update: message edit failed project=%d: %s", project_id, exc
            )
            self.unregister(project_id)

    # ── DB persistence helpers ─────────────────────────────────────────────────

    async def persist(self, project_id: int) -> None:
        """Persist the registered message IDs to the DB so they survive restarts."""
        entry = self._entries.get(project_id)
        if not entry:
            return
        from core.database import db
        await db.execute(
            """UPDATE projects
               SET active_dashboard_msg_id=$1,
                   active_dashboard_chan_id=$2,
                   lang=$3
             WHERE project_id=$4""",
            (entry.message_id, entry.channel_id, entry.lang, project_id),
        )

    async def restore_from_db(self, bot: "discord.Client") -> None:
        """Reload dashboard registrations from DB on bot restart."""
        from core.database import db
        from core.config import config
        rows = await db.fetchall(
            """SELECT project_id, guild_id, active_dashboard_msg_id, active_dashboard_chan_id,
                      COALESCE(lang, 'th') AS lang
                 FROM projects
                WHERE active_dashboard_msg_id IS NOT NULL
                  AND active_dashboard_chan_id IS NOT NULL""",
            (),
        )
        if not rows:
            return
        for row in rows:
            self.register(
                project_id=row["project_id"],
                guild_id=row["guild_id"],
                channel_id=int(row["active_dashboard_chan_id"]),
                message_id=int(row["active_dashboard_msg_id"]),
                lang=row["lang"] or config.bot.default_lang,
            )
            log.info(
                "Dashboard restored: project=%d  chan=%d  msg=%d  lang=%s",
                row["project_id"], row["active_dashboard_chan_id"], row["active_dashboard_msg_id"],
                row["lang"] or config.bot.default_lang,
            )


    @property
    def active_count(self) -> int:
        return len(self._entries)


# Module-level singleton — shared across realtime.dispatcher and collaboration.views
dashboard_tracker = DashboardTracker()
