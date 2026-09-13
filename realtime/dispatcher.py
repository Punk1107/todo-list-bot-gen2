"""
realtime/dispatcher.py — CDC Event Router

Receives raw Postgres change payloads from PhoenixWSClient and:
  1. Parses them into typed events.
  2. Filters for events we care about (task completed, task claimed, etc.).
  3. Sends Discord announcement embeds to the project's notification channel.
  4. Triggers debounced live-dashboard updates via DashboardTracker.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import discord

log = logging.getLogger(__name__)


class RealtimeDispatcher:
    """
    Routes Supabase Realtime CDC payloads to the correct Discord actions.

    Registered as a callback with PhoenixWSClient for the "tasks" table.
    """

    def __init__(self, bot: "discord.Client") -> None:
        self._bot = bot

    # ── Entry point — called by PhoenixWSClient ────────────────────────────────

    async def on_task_change(self, change: dict[str, Any]) -> None:
        """Handle any INSERT/UPDATE/DELETE on the tasks table."""
        event_type = change.get("type", change.get("eventType", "")).upper()

        if event_type == "UPDATE":
            await self._handle_task_update(change)
        elif event_type == "INSERT":
            await self._handle_task_insert(change)
        # DELETE events: just trigger a dashboard refresh if project is tracked
        elif event_type == "DELETE":
            old = change.get("old_record", change.get("old", {}))
            project_id = old.get("project_id")
            if project_id:
                await self._trigger_dashboard_update(int(project_id))

    async def on_activity_change(self, change: dict[str, Any]) -> None:
        """Handle INSERT on project_activity_log — trigger dashboard refresh."""
        event_type = change.get("type", change.get("eventType", "")).upper()
        if event_type == "INSERT":
            record = change.get("record", change.get("new", {}))
            project_id = record.get("project_id")
            if project_id:
                await self._trigger_dashboard_update(int(project_id))

    # ── Handlers ───────────────────────────────────────────────────────────────

    async def _handle_task_update(self, change: dict[str, Any]) -> None:
        """
        Detect status changes and fire appropriate notifications.
        Key transition: old_status != 'Completed' AND new_status == 'Completed'
        """
        new = change.get("record",     change.get("new", {}))
        old = change.get("old_record", change.get("old", {}))

        new_status = new.get("status", "")
        old_status = old.get("status", "")
        project_id_raw = new.get("project_id")

        # Only handle project tasks (personal tasks have no project_id)
        if not project_id_raw:
            return

        project_id = int(project_id_raw)

        # Task completed transition
        if new_status == "Completed" and old_status != "Completed":
            await self._announce_task_completed(new, project_id)

        # Always trigger dashboard refresh for any task status change
        await self._trigger_dashboard_update(project_id)

    async def _handle_task_insert(self, change: dict[str, Any]) -> None:
        """New task added to a project — refresh dashboard."""
        record = change.get("record", change.get("new", {}))
        project_id_raw = record.get("project_id")
        if project_id_raw:
            await self._trigger_dashboard_update(int(project_id_raw))

    # ── Announcement helpers ───────────────────────────────────────────────────

    async def _announce_task_completed(
        self,
        task_record: dict[str, Any],
        project_id: int,
    ) -> None:
        """Post a task-completed embed to the project's notification channel."""
        guild_id_raw = task_record.get("guild_id")
        if not guild_id_raw:
            return
        guild_id = str(guild_id_raw)

        # Fetch project from DB for name, emoji, color, notification_channel_id
        project = await self._fetch_project(project_id, guild_id)
        if not project:
            return

        channel_id = project.get("notification_channel_id") or project.get("channel_id")
        if not channel_id:
            log.debug(
                "No notification channel configured for project %d — skipping announcement.",
                project_id,
            )
            return

        # Fetch project stats for progress bar
        progress_pct: Optional[float] = None
        done_count: Optional[int] = None
        total: Optional[int] = None
        try:
            from collaboration import service as collab_service
            stats = await collab_service.get_project_stats(project_id, guild_id)
            progress_pct = stats.progress_pct
            done_count   = stats.completed
            total        = stats.total_tasks - stats.cancelled
        except Exception:
            pass

        # Determine who completed the task (may be in old_record or via audit)
        actor_id = task_record.get("owner_id", "")

        from realtime.notifications import build_task_completed_embed
        embed = build_task_completed_embed(
            task_id=int(task_record.get("task_id", 0)),
            task_name=task_record.get("task", "Unknown"),
            project_id=project_id,
            project_name=project.get("name", "Project"),
            project_emoji=project.get("emoji", "📁"),
            project_color=project.get("color", "#5865F2"),
            actor_id=actor_id,
            progress_pct=progress_pct,
            done_count=done_count,
            total=total,
        )

        await self._send_to_channel(int(channel_id), embed)

    # ── Dashboard refresh ──────────────────────────────────────────────────────

    async def _trigger_dashboard_update(self, project_id: int) -> None:
        from realtime.dashboard_tracker import dashboard_tracker
        if dashboard_tracker.get(project_id):
            dashboard_tracker.schedule_update(self._bot, project_id)

    # ── DB helpers ─────────────────────────────────────────────────────────────

    async def _fetch_project(
        self, project_id: int, guild_id: str
    ) -> Optional[dict]:
        from core.database import db
        try:
            row = await db.fetchone(
                """SELECT project_id, guild_id, name, emoji, color,
                          channel_id, notification_channel_id
                     FROM projects
                    WHERE project_id=$1 AND guild_id=$2""",
                (project_id, guild_id),
            )
            return dict(row) if row else None
        except Exception as exc:
            log.warning("Dispatcher: could not fetch project %d: %s", project_id, exc)
            return None

    # ── Discord channel dispatch ───────────────────────────────────────────────

    async def _send_to_channel(self, channel_id: int, embed: "discord.Embed") -> None:
        try:
            channel = self._bot.get_channel(channel_id)
            if channel is None:
                channel = await self._bot.fetch_channel(channel_id)
            await channel.send(embed=embed)  # type: ignore[union-attr]
        except Exception as exc:
            log.warning(
                "Realtime dispatcher: failed to send to channel %d: %s", channel_id, exc
            )
