"""
monitoring/alert_dispatcher.py — Send error & health alerts to an Admin Discord channel.

Usage:
    from monitoring.alert_dispatcher import AlertDispatcher
    dispatcher = AlertDispatcher(bot, channel_id=1234567890)
    await dispatcher.start()

    # In on_app_command_error:
    await dispatcher.dispatch_error(exc, level=logging.ERROR, command="task add", user_id="123")

    # After health check:
    await dispatcher.dispatch_health_alert(snapshot)

Design:
  - Fully non-blocking: uses asyncio.Queue + consumer task.
  - Rate-limiting: same error type cannot trigger an alert more than once per
    ALERT_RATE_LIMIT_SEC (default 300 = 5 min), preventing spam.
  - Gracefully skips sending if channel is not found or not configured.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import discord

from monitoring.health_monitor import HealthSnapshot

log = logging.getLogger(__name__)


class AlertDispatcher:
    """
    Queue-based alert dispatcher.
    All sends happen on a background consumer task — callers never block.
    """

    def __init__(
        self,
        bot: discord.Client,
        channel_id: Optional[int],
        rate_limit_sec: int = 300,
    ) -> None:
        self._bot            = bot
        self._default_channel_id = channel_id
        self._rate_limit_sec = rate_limit_sec
        # Queue contains tuples of (target_channel_id, embed)
        self._queue: asyncio.Queue[tuple[int, discord.Embed]] = asyncio.Queue(maxsize=100)
        self._last_alert: dict[str, float] = {}   # error_type:guild_id → last sent time
        self._task: Optional[asyncio.Task] = None
        self._guild_channels: dict[str, int] = {}  # in-memory cache: guild_id -> channel_id

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background sender task."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._consumer(), name="alert_dispatcher")
            log.info("AlertDispatcher consumer started")

    def update_guild_channel(self, guild_id: str, channel_id: int) -> None:
        """Hot-update a specific guild's alert channel."""
        self._guild_channels[guild_id] = channel_id
        log.info("AlertDispatcher: guild %s channel updated to %s", guild_id, channel_id)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._consumer(), name="alert_dispatcher")

    def update_channel(self, channel_id: int) -> None:
        """Hot-update the fallback/default alert channel."""
        self._default_channel_id = channel_id
        log.info("AlertDispatcher: default channel updated to %s", channel_id)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._consumer(), name="alert_dispatcher")

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    # ── Channel Resolution ───────────────────────────────────────────────────

    async def get_channel_for_guild(self, guild_id: str) -> Optional[int]:
        """Find the configured channel for a guild, from memory, Supabase, or default."""
        if guild_id in self._guild_channels:
            return self._guild_channels[guild_id]

        if guild_id and guild_id != "DM":
            try:
                from core.database import db
                ch_val = await db.get_guild_setting(guild_id, "admin_log_channel_id")
                if ch_val:
                    cid = int(ch_val)
                    self._guild_channels[guild_id] = cid
                    return cid
            except Exception as exc:
                log.debug("AlertDispatcher: DB channel lookup failed for guild %s: %s", guild_id, exc)

        return self._default_channel_id

    # ── Public dispatch API ──────────────────────────────────────────────────

    async def dispatch_error(
        self,
        error: BaseException,
        *,
        level: int = logging.ERROR,
        command: str = "-",
        user_id: str = "-",
        guild_id: str = "-",
    ) -> None:
        """
        Enqueue an error alert embed for the specific guild's admin channel.
        Rate-limited: same error type per guild skipped within self._rate_limit_sec.
        """
        target_ch_id = await self.get_channel_for_guild(guild_id)
        if not target_ch_id:
            return

        error_type = type(error).__name__
        rate_key = f"{error_type}:{guild_id}"
        now = time.time()

        # Rate limit check per error type per guild
        if now - self._last_alert.get(rate_key, 0) < self._rate_limit_sec:
            log.debug("AlertDispatcher: rate-limiting alert for %s in guild %s", error_type, guild_id)
            return

        self._last_alert[rate_key] = now
        embed = self._build_error_embed(error, level=level, command=command,
                                        user_id=user_id, guild_id=guild_id)
        await self._enqueue(target_ch_id, embed)

    async def dispatch_health_alert(self, snapshot: HealthSnapshot) -> None:
        """
        Enqueue a health degradation alert to the default/global admin channel.
        Only fires when DB is unreachable or memory is critically high.
        """
        target_ch_id = self._default_channel_id
        if not target_ch_id:
            # Fallback to any configured guild channel
            if self._guild_channels:
                target_ch_id = next(iter(self._guild_channels.values()))
            else:
                return

        if snapshot.is_healthy:
            return   # No alert needed

        rate_key = "health_alert:global"
        now = time.time()
        if now - self._last_alert.get(rate_key, 0) < self._rate_limit_sec:
            return

        self._last_alert[rate_key] = now
        embed = self._build_health_alert_embed(snapshot)
        await self._enqueue(target_ch_id, embed)

    # ── Internal helpers ─────────────────────────────────────────────────────

    async def _enqueue(self, channel_id: int, embed: discord.Embed) -> None:
        try:
            self._queue.put_nowait((channel_id, embed))
        except asyncio.QueueFull:
            log.warning("AlertDispatcher: queue full — dropping alert embed")

    async def _consumer(self) -> None:
        """Background task: drain the queue and send embeds to their respective channels."""
        while True:
            target_ch_id, embed = await self._queue.get()
            try:
                channel = self._bot.get_channel(target_ch_id)
                if channel is None:
                    channel = await self._bot.fetch_channel(target_ch_id)
                if isinstance(channel, discord.abc.Messageable):
                    await channel.send(embed=embed)
                else:
                    log.warning("AlertDispatcher: channel %s is not messageable", target_ch_id)
            except discord.Forbidden:
                log.error("AlertDispatcher: no permission to send in channel %s", target_ch_id)
            except discord.NotFound:
                log.error("AlertDispatcher: channel %s not found", target_ch_id)
            except Exception as exc:
                log.error("AlertDispatcher: failed to send alert to channel %s: %s", target_ch_id, exc)
            finally:
                self._queue.task_done()
            # Small delay between sends to avoid Discord rate limits
            await asyncio.sleep(1)

    # ── Embed builders ────────────────────────────────────────────────────────

    @staticmethod
    def _build_error_embed(
        error: BaseException,
        *,
        level: int,
        command: str,
        user_id: str,
        guild_id: str,
    ) -> discord.Embed:
        import traceback

        level_meta = {
            logging.CRITICAL: ("🆘 CRITICAL ERROR", 0x8B0000),
            logging.ERROR:    ("❌ Error Detected", 0xE74C3C),
            logging.WARNING:  ("⚠️ Warning",         0xF39C12),
        }
        title, color = level_meta.get(level, ("⚠️ Bot Alert", 0xF39C12))

        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        # Truncate to fit Discord's 1024 char field limit
        if len(tb) > 900:
            tb = "...\n" + tb[-900:]

        embed = discord.Embed(
            title=title,
            description=f"**`{type(error).__name__}`**: {str(error)[:300]}",
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="📌 Command", value=f"`{command}`", inline=True)
        embed.add_field(name="👤 User ID", value=f"`{user_id}`", inline=True)
        embed.add_field(name="🏠 Guild ID", value=f"`{guild_id}`", inline=True)
        embed.add_field(name="🔍 Traceback", value=f"```py\n{tb}\n```", inline=False)
        embed.set_footer(text="monitoring/alert_dispatcher.py")
        return embed

    @staticmethod
    def _build_health_alert_embed(snapshot: HealthSnapshot) -> discord.Embed:
        issues = []
        if not snapshot.is_db_healthy:
            issues.append(f"🗄️ DB unreachable or high latency ({snapshot.db_latency_ms:.0f} ms)")
        if not snapshot.is_memory_ok:
            issues.append(f"💾 Memory critical: {snapshot.memory_mb:.0f} MB ({snapshot.memory_percent:.0f}%)")

        embed = discord.Embed(
            title="🚑 Health Alert — Bot Degraded",
            description="\n".join(issues) or "Unknown degradation",
            color=0xE74C3C,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="⏱️ Uptime", value=f"{int(snapshot.uptime_s)}s", inline=True)
        embed.add_field(name="🌐 Guilds", value=str(snapshot.guilds), inline=True)
        embed.add_field(
            name="📡 Discord Latency",
            value=f"{snapshot.discord_latency_ms:.0f} ms",
            inline=True,
        )
        embed.set_footer(text="monitoring/alert_dispatcher.py")
        return embed
