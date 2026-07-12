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
import logging.handlers
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

# ── Logging  ──────────────────────────────────────────────────────────────────
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

_fmt = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)-30s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Rotating file handler — 5 MB per file, keep 5 backups
_file_handler = logging.handlers.RotatingFileHandler(
    LOG_DIR / "bot.log", maxBytes=5_242_880, backupCount=5, encoding="utf-8"
)
_file_handler.setFormatter(_fmt)

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_fmt)

logging.basicConfig(level=logging.INFO, handlers=[_file_handler, _console_handler])

log = logging.getLogger("main")

if _UVLOOP:
    log.info("uvloop active — using high-performance event loop")

# Suppress noisy third-party loggers
for _name in ("discord", "discord.http", "discord.gateway", "aiohttp.access"):
    logging.getLogger(_name).setLevel(logging.WARNING)

# ── Bot setup ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True


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
                log.info("✓ Loaded cog: %s", cog)
            except Exception as exc:
                failed += 1
                log.error("✗ Failed to load cog %s: %s", cog, exc, exc_info=True)

        if failed == len(COGS):
            log.critical("All cogs failed to load — aborting")
            return

        # Start BulkWriter (requires a running event loop)
        from core.database import db
        db.start_bulk_writer()

        # Re-register persistent task views so buttons on old messages stay interactive
        # after a bot restart. Must run after BulkWriter start and DB is ready.
        from handlers.task_views import register_all_persistent_views
        await register_all_persistent_views(self)

        # Start async webserver (no daemon thread — pure coroutine)
        from utils.webserver import start_async
        self._webserver_runner = await start_async()

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
        """Graceful shutdown: flush BulkWriter, stop webserver, then close."""
        from core.database import db
        log.info("Flushing BulkWriter before shutdown...")
        await db.bulk_writer.stop()

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

# ── Cog list ──────────────────────────────────────────────────────────────────
COGS = [
    "handlers.tasks_cog",
    "handlers.settings_cog",
    "handlers.reminders_cog",
]

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

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="📝 /help | To-Do Bot Gen 2",
        )
    )


@bot.event
async def on_interaction(interaction: discord.Interaction) -> None:
    """Update last_active timestamp non-blocking via BulkWriter."""
    from core.database import db
    uid = str(interaction.user.id)
    db.bulk_writer.enqueue(
        "UPDATE users SET last_active=CURRENT_TIMESTAMP WHERE user_id=?",
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
        log.error("Unhandled app_command_error: %s", error, exc_info=True)
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
    # Graceful shutdown on SIGINT / SIGTERM
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _shutdown(_signum, _frame):
        log.info("Shutdown signal received — closing bot")
        loop.stop()

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
        from core.database import db
        db.close()
        loop.close()
        log.info("Event loop closed — goodbye")
