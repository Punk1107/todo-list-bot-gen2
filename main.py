"""
main.py — Entry point for To-Do List Bot Gen 2 v2
Improvements:
  - Graceful shutdown (SIGINT/SIGTERM)
  - Startup banner with version info
  - Guild-specific sync in debug mode, global sync in production
  - on_error handler for unexpected exceptions
  - Proper log rotation via RotatingFileHandler
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

# Suppress noisy third-party loggers
for _name in ("discord", "discord.http", "discord.gateway", "werkzeug"):
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
    log.info("━" * 60)
    log.info("  To-Do List Bot Gen 2 — Online")
    log.info("  User   : %s (ID: %s)", bot.user, bot.user.id)
    log.info("  Guilds : %d", len(bot.guilds))
    log.info("  Latency: %.1f ms", bot.latency * 1000)
    log.info("━" * 60)

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="📝 /help | To-Do Bot Gen 2",
        )
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
        # setup_hook() handles cog loading and slash command sync automatically.
        # Start keep-alive webserver (daemon thread)
        from utils.webserver import start as start_webserver
        start_webserver()

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
