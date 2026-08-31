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
        self._channel_id     = channel_id
        self._rate_limit_sec = rate_limit_sec
        self._queue: asyncio.Queue[discord.Embed] = asyncio.Queue(maxsize=50)
        self._last_alert: dict[str, float] = {}   # error_type → last sent time
        self._task: Optional[asyncio.Task] = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background sender task. Call after bot is ready."""
        if not self._channel_id:
            log.info("AlertDispatcher: ADMIN_LOG_CHANNEL_ID not set — alerts disabled")
            return
        self._task = asyncio.create_task(self._consumer(), name="alert_dispatcher")
        log.info("AlertDispatcher started — channel: %s", self._channel_id)

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

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
        Enqueue an error alert embed.
        Rate-limited: same error type skipped within self._rate_limit_sec.
        """
        if not self._channel_id:
            return

        error_type = type(error).__name__
        now = time.time()

        # Rate limit check
        if now - self._last_alert.get(error_type, 0) < self._rate_limit_sec:
            log.debug("AlertDispatcher: rate-limiting alert for %s", error_type)
            return

        self._last_alert[error_type] = now
        embed = self._build_error_embed(error, level=level, command=command,
                                        user_id=user_id, guild_id=guild_id)
        await self._enqueue(embed)

    async def dispatch_health_alert(self, snapshot: HealthSnapshot) -> None:
        """
        Enqueue a health degradation alert.
        Only fires when DB is unreachable or memory is critically high.
        """
        if not self._channel_id:
            return
        if snapshot.is_healthy:
            return   # No alert needed

        rate_key = "health_alert"
        now = time.time()
        if now - self._last_alert.get(rate_key, 0) < self._rate_limit_sec:
            return

        self._last_alert[rate_key] = now
        embed = self._build_health_alert_embed(snapshot)
        await self._enqueue(embed)

    # ── Internal helpers ─────────────────────────────────────────────────────

    async def _enqueue(self, embed: discord.Embed) -> None:
        try:
            self._queue.put_nowait(embed)
        except asyncio.QueueFull:
            log.warning("AlertDispatcher: queue full — dropping alert embed")

    async def _consumer(self) -> None:
        """Background task: drain the queue and send embeds to the admin channel."""
        while True:
            embed = await self._queue.get()
            try:
                channel = self._bot.get_channel(self._channel_id)
                if channel is None:
                    channel = await self._bot.fetch_channel(self._channel_id)
                if isinstance(channel, discord.abc.Messageable):
                    await channel.send(embed=embed)
                else:
                    log.warning("AlertDispatcher: channel %s is not messageable", self._channel_id)
            except discord.Forbidden:
                log.error("AlertDispatcher: no permission to send in channel %s", self._channel_id)
            except discord.NotFound:
                log.error("AlertDispatcher: channel %s not found", self._channel_id)
            except Exception as exc:
                log.error("AlertDispatcher: failed to send alert: %s", exc)
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
