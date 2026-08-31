"""
main.py — Entry point for To-Do List Bot Gen 2 v3
Changes over v2:
  - uvloop guard: uses uvloop on Linux/macOS for 2-4x faster event loop
  - BulkWriter started in setup_hook (requires running event loop)
  - Webserver upgraded to aiohttp async — started via create_task
  - last_active update via on_interaction hook (background, non-blocking)
  - Graceful shutdown: BulkWriter flushed before DB close
  - Startup banner extended with pool/cache config summary
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

import discord
from discord.ext import commands

# ── Bootstrap: project root on sys.path ──────────────────────────────────────
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── uvloop: opt-in faster event loop (Linux/macOS only) ──────────────────────
try:
    import uvloop  # type: ignore
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    _UVLOOP = True
except ImportError:
    _UVLOOP = False   # Windows or package not installed — silently fall back

# ── Config (validates .env — exits if DISCORD_TOKEN missing) ──────────────────
from core.config import config

# ── Logging (structured, multi-file) ─────────────────────────────────────────
from monitoring.logger_setup import setup_logging
setup_logging()

log = logging.getLogger("main")

if _UVLOOP:
    log.info("uvloop active — using high-performance event loop")

# ── Bot setup ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# ── Cog list ──────────────────────────────────────────────────────────────────
# Define BEFORE TodoBot so setup_hook() can reference it without NameError.
COGS = [
    "handlers.tasks_cog",
    "handlers.settings_cog",
    "handlers.reminders_cog",
    "handlers.monitoring_cog",   # admin /health /errors /cmdstats
]


class TodoBot(commands.Bot):
    """Bot subclass that syncs slash commands in setup_hook.

    setup_hook() runs after login (application_id is known) but before
    on_ready, making it the correct place for one-time async setup.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._webserver_runner = None  # hold reference for graceful shutdown

    async def setup_hook(self) -> None:  # noqa: D102
        # Load cogs here so they are registered before sync
        failed = 0
        for cog in COGS:
            try:
                await self.load_extension(cog)
                log.info("[OK] Loaded cog: %s", cog)
            except Exception as exc:
                failed += 1
                log.error("[FAIL] Failed to load cog %s: %s", cog, exc, exc_info=True)

        if failed == len(COGS):
            log.critical("All cogs failed to load — aborting")
            return

        # Initialize database (async — creates asyncpg pool and runs migrations)
        from core.database import db
        await db.initialize()

        # Start BulkWriter (requires a running event loop)
        db.start_bulk_writer()

        # Re-register persistent task views so buttons on old messages stay interactive
        # after a bot restart. Must run after BulkWriter start and DB is ready.
        from handlers.task_views import register_all_persistent_views
        await register_all_persistent_views(self)

        # Start async webserver (no daemon thread — pure coroutine)
        from utils.webserver import start_async
        self._webserver_runner = await start_async()

        # ── Monitoring system ────────────────────────────────────────────────
        if config.monitoring.enabled:
            # Start error tracker auto-reset (24 h)
            from monitoring.error_tracker import error_tracker
            error_tracker.start()

            # Start background health monitor
            from monitoring.health_monitor import health_monitor
            health_monitor._interval = config.monitoring.health_check_interval_min * 60
            await health_monitor.start(self)

            # Start alert dispatcher (sends to admin channel if configured)
            from monitoring.alert_dispatcher import AlertDispatcher
            self._alert_dispatcher = AlertDispatcher(
                bot=self,
                channel_id=config.monitoring.admin_log_channel_id,
                rate_limit_sec=config.monitoring.alert_rate_limit_sec,
            )
            await self._alert_dispatcher.start()

            log.info(
                "Monitoring enabled — health_interval=%dmin  alert_channel=%s",
                config.monitoring.health_check_interval_min,
                config.monitoring.admin_log_channel_id or "not set",
            )
        else:
            self._alert_dispatcher = None

        # Sync slash commands — application_id is available here
        debug_guild_id = os.getenv("DEBUG_GUILD_ID")
        try:
            if debug_guild_id:
                guild = discord.Object(id=int(debug_guild_id))
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                log.info("Synced %d commands to debug guild %s", len(synced), debug_guild_id)
            else:
                synced = await self.tree.sync()
                log.info("Synced %d commands globally", len(synced))
        except Exception as exc:
            log.error("Slash command sync failed: %s", exc)

    async def close(self) -> None:
        """Graceful shutdown: stop monitoring, flush BulkWriter, stop webserver."""
        # Stop monitoring tasks first (they may be writing logs)
        if config.monitoring.enabled:
            try:
                from monitoring.error_tracker import error_tracker
                error_tracker.stop()
                from monitoring.health_monitor import health_monitor
                health_monitor.stop()
                if self._alert_dispatcher:
                    self._alert_dispatcher.stop()
            except Exception as exc:
                log.warning("Monitoring shutdown error: %s", exc)

        from core.database import db
        log.info("Flushing BulkWriter before shutdown...")
        await db.close()  # also stops BulkWriter

        if self._webserver_runner:
            await self._webserver_runner.cleanup()
            log.info("Webserver stopped")

        await super().close()


bot = TodoBot(
    command_prefix=commands.when_mentioned,   # slash-only — prefix ignored
    intents=intents,
    help_command=None,
    description="To-Do List Bot Gen 2",
)

# ── Internal state defaults ────────────────────────────────────────────────────
bot._alert_dispatcher = None   # set in setup_hook if monitoring is enabled

# ── Cog list (defined above TodoBot — kept here as a comment reference) ───────

# ── Events ────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready() -> None:
    from core.database import db
    log.info("━" * 60)
    log.info("  To-Do List Bot Gen 2 v3 — Online")
    log.info("  User     : %s (ID: %s)", bot.user, bot.user.id)
    log.info("  Guilds   : %d", len(bot.guilds))
    log.info("  Latency  : %.1f ms", bot.latency * 1000)
    log.info("  DB pool  : %d conns | schema v%d",
             config.db.pool_size, db.metrics["schema_version"])
    log.info("  QCache   : TTL %.0fs | max %d entries",
             config.db.query_cache_ttl, 2048)
    log.info("  uvloop   : %s", "✓ active" if _UVLOOP else "✗ not available")
    log.info("━" * 60)

    # ── Load guild-specific monitoring settings from Supabase ─────────────────
    # If any guild has set an admin_log_channel_id via /monitoring setup,
    # apply it now so alerts work correctly after a restart.
    if config.monitoring.enabled and bot._alert_dispatcher and bot.guilds:
        try:
            for guild in bot.guilds:
                ch_id_str = await db.get_guild_setting(str(guild.id), "admin_log_channel_id")
                if ch_id_str:
                    ch_id = int(ch_id_str)
                    bot._alert_dispatcher.update_guild_channel(str(guild.id), ch_id)
                    log.info(
                        "Monitoring: loaded admin_log_channel_id=%s for guild %s (%s)",
                        ch_id, guild.id, guild.name,
                    )
        except Exception as exc:
            log.warning("Monitoring: could not load guild settings: %s", exc)

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="📝 /help | To-Do Bot Gen 2",
        )
    )


@bot.event
async def on_interaction(interaction: discord.Interaction) -> None:
    """Update last_active timestamp non-blocking via BulkWriter.
    Also ensures the user row exists (INSERT OR IGNORE) so the UPDATE never silently drops.
    """
    from core.database import db
    # Guard: do not enqueue before the DB pool is initialised (e.g. during reconnect)
    if db._pool is None:
        return
    uid = str(interaction.user.id)
    # Ensure user row exists before updating last_active
    db.bulk_writer.enqueue(
        "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
        (uid,),
    )
    db.bulk_writer.enqueue(
        "UPDATE users SET last_active=NOW() WHERE user_id=$1",
        (uid,),
    )


@bot.event
async def on_app_command_error(
    interaction: discord.Interaction,
    error: discord.app_commands.AppCommandError,
) -> None:
    from utils.helpers import get_user_lang
    from locales.i18n import t
    # get_user_lang is now async
    lang = await get_user_lang(interaction.user.id)

    if isinstance(error, discord.app_commands.CommandOnCooldown):
        msg = t("rate_limited", lang, seconds=error.retry_after)
    elif isinstance(error, discord.app_commands.MissingPermissions):
        msg = t("permission_denied", lang)
    elif isinstance(error, discord.app_commands.BotMissingPermissions):
        msg = "❌ I'm missing required permissions in this channel."
    elif isinstance(error, discord.app_commands.NoPrivateMessage):
        msg = "❌ This command cannot be used in DMs."
    elif isinstance(error, discord.app_commands.CommandNotFound):
        return   # Silently ignore — can happen during deploy
    else:
        # ── Record & dispatch unhandled errors ──────────────────────────────
        cmd_name = interaction.command.name if interaction.command else "-"
        uid      = str(interaction.user.id)
        gid      = str(interaction.guild_id or "DM")

        log.error(
            "Unhandled app_command_error: %s",
            error,
            exc_info=True,
            extra={"guild_id": gid, "user_id": uid, "command": cmd_name},
        )

        # Record into error tracker
        if config.monitoring.enabled:
            from monitoring.error_tracker import error_tracker
            error_tracker.record(error, command=cmd_name, user_id=uid)

            # Dispatch alert to admin channel (rate-limited, non-blocking)
            if bot._alert_dispatcher:
                asyncio.create_task(
                    bot._alert_dispatcher.dispatch_error(
                        error,
                        level=logging.ERROR,
                        command=cmd_name,
                        user_id=uid,
                        guild_id=gid,
                    ),
                    name="alert_dispatch",
                )

            # Log the command as failed
            from monitoring.commands_log import commands_logger
            commands_logger.log_command(
                cmd_name,
                user_id=uid,
                guild_id=gid,
                success=False,
                error_type=type(error).__name__,
            )

        msg = t("err_generic", lang)

    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except discord.InteractionResponded:
        pass   # interaction already responded — safe to ignore
    except Exception as exc:
        log.debug("on_app_command_error: could not reply: %s", exc)


@bot.event
async def on_error(event: str, *args, **kwargs) -> None:
    log.error("Unhandled event error in '%s'", event, exc_info=True)


# ── Main entry ────────────────────────────────────────────────────────────────

async def main() -> None:
    async with bot:
        # setup_hook() handles everything: cogs, BulkWriter, webserver, slash sync
        await bot.start(config.bot.token)


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _shutdown(_signum, _frame):
        """Schedule bot.close() on the running loop so BulkWriter is flushed
        gracefully before the pool is closed.  Simply stopping the loop here
        would skip TodoBot.close() and lose queued BulkWriter writes.
        """
        log.info("Shutdown signal received — scheduling graceful bot close")
        # bot.close() triggers TodoBot.close() → BulkWriter.stop() → pool.close()
        asyncio.ensure_future(bot.close(), loop=loop)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot stopped")
    except Exception as exc:
        log.critical("Fatal error: %s", exc, exc_info=True)
        sys.exit(1)
    finally:
        # db.close() was already called inside TodoBot.close() — do NOT call it again here
        # or asyncpg will raise an error on a double-close of the pool.
        if not loop.is_closed():
            loop.close()
        log.info("Event loop closed — goodbye")
