"""
monitoring/health_monitor.py — Background health check loop.

Monitors:
  - Database connectivity & query latency (asyncpg ping)
  - Memory usage (psutil)
  - Event loop lag (scheduled callback drift)
  - Bot uptime, guild count, Discord latency

Usage:
    from monitoring.health_monitor import health_monitor
    await health_monitor.start(bot)
    snapshot = health_monitor.latest
    embed = health_monitor.get_health_embed()
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import discord

log = logging.getLogger(__name__)

# Try psutil — gracefully degrade if not installed
try:
    import psutil as _psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _psutil = None  # type: ignore
    _PSUTIL_AVAILABLE = False
    log.warning("psutil not installed — memory stats unavailable. Run: pip install psutil")


# ── Snapshot dataclass ────────────────────────────────────────────────────────

@dataclass
class HealthSnapshot:
    timestamp: float = field(default_factory=time.time)
    uptime_s: float = 0.0
    guilds: int = 0
    discord_latency_ms: float = 0.0
    db_latency_ms: float = -1.0   # -1 = could not reach DB
    db_pool_size: int = 0
    memory_mb: float = -1.0       # -1 = psutil unavailable
    memory_percent: float = -1.0
    loop_lag_ms: float = 0.0
    is_db_healthy: bool = True
    is_memory_ok: bool = True

    @property
    def is_healthy(self) -> bool:
        """Overall health: DB reachable + memory under 85%."""
        return self.is_db_healthy and self.is_memory_ok


# ── Monitor ──────────────────────────────────────────────────────────────────

class HealthMonitor:
    """
    Async background health checker.

    Call ``await health_monitor.start(bot)`` once in setup_hook.
    The latest snapshot is always available via ``health_monitor.latest``.
    """

    def __init__(self, check_interval_minutes: int = 5) -> None:
        self._interval = check_interval_minutes * 60
        self._bot: Optional[discord.Client] = None
        self._task: Optional[asyncio.Task] = None
        self._start_time: float = time.monotonic()
        self._latest: HealthSnapshot = HealthSnapshot()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self, bot: discord.Client) -> None:
        """Start the health check loop. Call after event loop is running."""
        self._bot = bot
        self._start_time = time.monotonic()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="health_monitor")
            log.info("HealthMonitor started — interval: %d min", self._interval // 60)

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            log.info("HealthMonitor stopped")

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def latest(self) -> HealthSnapshot:
        return self._latest

    @property
    def is_healthy(self) -> bool:
        return self._latest.is_healthy

    # ── Background loop ──────────────────────────────────────────────────────

    async def _loop(self) -> None:
        # Run an initial check immediately, then repeat
        await asyncio.sleep(10)   # Give the bot a moment to connect
        while True:
            try:
                self._latest = await self._take_snapshot()
                self._log_snapshot(self._latest)
            except Exception as exc:
                log.error("HealthMonitor snapshot failed: %s", exc, exc_info=True)
            await asyncio.sleep(self._interval)

    # ── Snapshot logic ───────────────────────────────────────────────────────

    async def _take_snapshot(self) -> HealthSnapshot:
        snap = HealthSnapshot(
            uptime_s=time.monotonic() - self._start_time,
            guilds=len(self._bot.guilds) if self._bot else 0,
            discord_latency_ms=round((self._bot.latency if self._bot else 0) * 1000, 1),
        )

        # ── DB ping ──────────────────────────────────────────────────────────
        try:
            from core.database import db
            if db._pool is not None:
                t0 = time.perf_counter()
                async with db._pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                snap.db_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                snap.db_pool_size  = db._pool.get_size()
                snap.is_db_healthy = snap.db_latency_ms < 1000   # >1s = unhealthy
            else:
                snap.is_db_healthy = False
        except Exception as exc:
            log.warning("HealthMonitor DB ping failed: %s", exc)
            snap.is_db_healthy = False

        # ── Memory ───────────────────────────────────────────────────────────
        if _PSUTIL_AVAILABLE:
            try:
                proc = _psutil.Process()
                mem  = proc.memory_info()
                snap.memory_mb      = round(mem.rss / 1_048_576, 1)
                snap.memory_percent = round(_psutil.virtual_memory().percent, 1)
                snap.is_memory_ok   = snap.memory_percent < 85.0
            except Exception as exc:
                log.debug("HealthMonitor memory check failed: %s", exc)

        # ── Event loop lag ───────────────────────────────────────────────────
        snap.loop_lag_ms = await self._measure_loop_lag()

        return snap

    @staticmethod
    async def _measure_loop_lag() -> float:
        """
        Measure how long it takes for a no-op coroutine to be scheduled.
        High lag → event loop is overloaded.
        """
        t0 = time.perf_counter()
        await asyncio.sleep(0)
        return round((time.perf_counter() - t0) * 1000, 2)

    def _log_snapshot(self, snap: HealthSnapshot) -> None:
        status = "✓ HEALTHY" if snap.is_healthy else "✗ DEGRADED"
        log.info(
            "HealthMonitor [%s] uptime=%.0fs  guilds=%d  discord=%.0fms  "
            "db=%.1fms  memory=%.1fMB (%.0f%%)  loop_lag=%.2fms",
            status,
            snap.uptime_s,
            snap.guilds,
            snap.discord_latency_ms,
            snap.db_latency_ms,
            snap.memory_mb,
            snap.memory_percent,
            snap.loop_lag_ms,
        )

    # ── Discord Embed ────────────────────────────────────────────────────────

    def get_health_embed(self) -> discord.Embed:
        """Build a rich health status embed from the latest snapshot."""
        snap = self._latest
        ok = snap.is_healthy

        color = 0x2ECC71 if ok else 0xE74C3C
        status_label = "🟢 Healthy" if ok else "🔴 Degraded"

        # Format uptime
        uptime_s = int(snap.uptime_s)
        hours, rem = divmod(uptime_s, 3600)
        mins, secs = divmod(rem, 60)
        uptime_str = f"{hours}h {mins}m {secs}s"

        # DB latency indicator
        if snap.db_latency_ms < 0:
            db_str = "❌ Unreachable"
        elif snap.db_latency_ms < 100:
            db_str = f"🟢 {snap.db_latency_ms} ms"
        elif snap.db_latency_ms < 500:
            db_str = f"🟡 {snap.db_latency_ms} ms"
        else:
            db_str = f"🔴 {snap.db_latency_ms} ms"

        # Memory indicator
        if snap.memory_mb < 0:
            mem_str = "N/A (psutil not installed)"
        elif snap.memory_percent < 50:
            mem_str = f"🟢 {snap.memory_mb} MB ({snap.memory_percent:.0f}%)"
        elif snap.memory_percent < 80:
            mem_str = f"🟡 {snap.memory_mb} MB ({snap.memory_percent:.0f}%)"
        else:
            mem_str = f"🔴 {snap.memory_mb} MB ({snap.memory_percent:.0f}%)"

        # Loop lag indicator
        if snap.loop_lag_ms < 5:
            lag_str = f"🟢 {snap.loop_lag_ms} ms"
        elif snap.loop_lag_ms < 50:
            lag_str = f"🟡 {snap.loop_lag_ms} ms"
        else:
            lag_str = f"🔴 {snap.loop_lag_ms} ms"

        embed = discord.Embed(
            title=f"🏥 Bot Health Status — {status_label}",
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="🤖 Bot",
            value=(
                f"**Uptime:** {uptime_str}\n"
                f"**Guilds:** {snap.guilds}\n"
                f"**Discord latency:** {snap.discord_latency_ms:.0f} ms"
            ),
            inline=True,
        )
        embed.add_field(
            name="🗄️ Database",
            value=(
                f"**Ping:** {db_str}\n"
                f"**Pool size:** {snap.db_pool_size}"
            ),
            inline=True,
        )
        embed.add_field(
            name="💾 System",
            value=(
                f"**Memory:** {mem_str}\n"
                f"**Loop lag:** {lag_str}"
            ),
            inline=True,
        )
        snap_ts = int(snap.timestamp)
        embed.set_footer(text=f"Last checked · <t:{snap_ts}:R>")
        return embed


# ── Module-level singleton ────────────────────────────────────────────────────
health_monitor = HealthMonitor()
