"""
monitoring/logger_setup.py — Structured multi-file logging setup.

Provides:
  - setup_logging()  : Call once at startup in main.py to replace the inline setup.
  - get_logger(name) : Per-module logger factory (thin wrapper).

Log files:
  logs/bot.log      — INFO and above  (rotating, 5 MB × 5 backups)
  logs/errors.log   — WARNING and above only (easy to grep for problems)
  logs/commands.log — Command audit trail written by CommandsLogger
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"

# ── Formatters ──────────────────────────────────────────────────────────────

_STANDARD_FMT = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)-30s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_ERROR_FMT = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)-30s — %(message)s\n"
    "  guild=%(guild_id)s  user=%(user_id)s  cmd=%(command)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ── Filters ─────────────────────────────────────────────────────────────────

class _ErrorOnlyFilter(logging.Filter):
    """Pass only WARNING and above — keeps errors.log lean."""
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.WARNING


class ContextInjectFilter(logging.Filter):
    """
    Inject optional context fields so _ERROR_FMT never raises KeyError.
    Call log.warning(..., extra={"guild_id": ..., "user_id": ..., "command": ...})
    to populate these fields; they default to '-' when absent.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        record.guild_id  = getattr(record, "guild_id",  "-")
        record.user_id   = getattr(record, "user_id",   "-")
        record.command   = getattr(record, "command",   "-")
        return True


# ── Public API ───────────────────────────────────────────────────────────────

def setup_logging(level: int = logging.INFO) -> None:
    """
    Configure the root logger with rotating file + console handlers.
    Call this ONCE in main.py before any other import that uses logging.

    Args:
        level: Root log level (default INFO). Use logging.DEBUG for verbose output.
    """
    LOG_DIR.mkdir(exist_ok=True)

    context_filter = ContextInjectFilter()
    error_filter   = _ErrorOnlyFilter()

    # ── bot.log — general INFO+ ──────────────────────────────────────────────
    bot_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "bot.log",
        maxBytes=5_242_880,   # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    bot_handler.setFormatter(_STANDARD_FMT)
    bot_handler.addFilter(context_filter)

    # ── errors.log — WARNING+ with context ──────────────────────────────────
    error_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "errors.log",
        maxBytes=2_097_152,   # 2 MB
        backupCount=10,
        encoding="utf-8",
    )
    error_handler.setFormatter(_ERROR_FMT)
    error_handler.addFilter(context_filter)
    error_handler.addFilter(error_filter)

    # ── console — INFO+ ──────────────────────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(_STANDARD_FMT)
    console_handler.addFilter(context_filter)

    logging.basicConfig(
        level=level,
        handlers=[bot_handler, error_handler, console_handler],
        force=True,   # override any previous basicConfig call
    )

    # Suppress noisy third-party loggers
    for _name in ("discord", "discord.http", "discord.gateway", "aiohttp.access"):
        logging.getLogger(_name).setLevel(logging.WARNING)

    logging.getLogger("monitoring").info("Logging system initialised — logs dir: %s", LOG_DIR)


def get_logger(name: str) -> logging.Logger:
    """Thin convenience wrapper — mirrors logging.getLogger."""
    return logging.getLogger(name)
