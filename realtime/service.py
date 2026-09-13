"""
realtime/service.py — RealtimeService Lifecycle Manager

Owns the PhoenixWSClient and RealtimeDispatcher.
Called from main.py setup_hook() / close() to start and stop the Realtime subsystem.

Usage (in main.py):
    from realtime.service import setup_realtime, stop_realtime

    # In TodoBot.setup_hook():
    await setup_realtime(self)

    # In TodoBot.close():
    await stop_realtime()
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import discord

from core.config import config
from realtime.client import PhoenixWSClient
from realtime.dispatcher import RealtimeDispatcher
from realtime.dashboard_tracker import dashboard_tracker

log = logging.getLogger(__name__)

# Module-level singleton references for lifecycle management
_client:   Optional[PhoenixWSClient]  = None
_task:     Optional[asyncio.Task]     = None


async def setup_realtime(bot: "discord.Client") -> None:
    """
    Initialise the Realtime subsystem:
      1. Build the Phoenix WS client.
      2. Register callbacks via the dispatcher.
      3. Launch the client as a background asyncio Task.
      4. Restore any live dashboards from the DB.
    Called from TodoBot.setup_hook().
    """
    global _client, _task

    rt_cfg = config.realtime
    if not rt_cfg.enabled:
        log.info("Supabase Realtime disabled (SUPABASE_REALTIME_ENABLED=false or missing credentials).")
        return

    log.info("Starting Supabase Realtime listener…")

    _client = PhoenixWSClient(
        url=rt_cfg.url,
        api_key=rt_cfg.key,
        heartbeat_sec=rt_cfg.heartbeat_sec,
        reconnect_base_sec=rt_cfg.reconnect_base_sec,
        max_reconnect_attempts=rt_cfg.max_reconnect_attempts,
    )

    dispatcher = RealtimeDispatcher(bot)

    # Subscribe dispatcher to CDC events
    _client.subscribe("public", "tasks",                dispatcher.on_task_change)
    _client.subscribe("public", "project_activity_log", dispatcher.on_activity_change)

    # Update debounce from config
    dashboard_tracker._debounce_sec = rt_cfg.debounce_sec

    # Restore dashboard registrations that existed before the bot restarted
    try:
        await dashboard_tracker.restore_from_db(bot)
    except Exception as exc:
        log.warning("Could not restore dashboard registrations: %s", exc)

    # Launch the WS client as a background task
    _task = asyncio.create_task(_client.start(), name="realtime_ws")
    log.info(
        "Supabase Realtime listener started  (url=%s  heartbeat=%ds  debounce=%.1fs)",
        rt_cfg.url, rt_cfg.heartbeat_sec, rt_cfg.debounce_sec,
    )


async def stop_realtime() -> None:
    """Graceful shutdown — stop client and cancel the background task."""
    global _client, _task

    if _client:
        try:
            await _client.stop()
        except Exception as exc:
            log.warning("Realtime client stop error: %s", exc)
        _client = None

    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None

    log.info("Supabase Realtime listener stopped.")


def get_client() -> Optional[PhoenixWSClient]:
    """Return the current WS client (or None if not started)."""
    return _client


def get_metrics() -> dict:
    """Return realtime subsystem health metrics for /health endpoint."""
    if _client:
        return {
            "enabled": True,
            "running": _task is not None and not _task.done(),
            **_client.metrics,
            "dashboards_tracked": dashboard_tracker.active_count,
        }
    return {
        "enabled": config.realtime.enabled,
        "running": False,
        "dashboards_tracked": 0,
    }
