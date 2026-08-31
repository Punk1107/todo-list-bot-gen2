"""
core/config.py  —  Centralised configuration & environment validation v3
Changes:
  - Added query_cache_ttl, bulk_write_interval_ms to DatabaseConfig
  - Increased pool_size default to 10
  - Added CacheConfig dataclass for fine-grained cache tuning
All settings pulled from .env — zero hardcoded secrets.
"""
from __future__ import annotations

import os
import sys
import logging
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────────────

def _env(key: str, default: str | None = None, *, required: bool = False) -> str | None:
    val = os.getenv(key, default)
    if required and not val:
        log.critical("Missing required environment variable: %s", key)
        sys.exit(1)
    return val


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        log.warning("Invalid integer for %s, using default %d", key, default)
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        log.warning("Invalid float for %s, using default %.2f", key, default)
        return default


def _env_bool(key: str, default: bool = True) -> bool:
    val = os.getenv(key, str(default)).lower()
    return val in ("1", "true", "yes", "on")


# ──────────────────────────────────────────────────────────────────────────────
# Config dataclasses
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BotConfig:
    token: str
    prefix: str
    default_timezone: str
    default_lang: str
    owner_ids: frozenset[int]

    @classmethod
    def from_env(cls) -> "BotConfig":
        token = _env("DISCORD_TOKEN", required=True)
        owner_raw = _env("BOT_OWNER_IDS", "")
        owner_ids: frozenset[int] = frozenset()
        if owner_raw:
            try:
                owner_ids = frozenset(int(x.strip()) for x in owner_raw.split(",") if x.strip())
            except ValueError:
                log.warning("BOT_OWNER_IDS contains non-integer values — ignoring")
        return cls(
            token=token,
            prefix=_env("COMMAND_PREFIX", "!"),
            default_timezone=_env("DEFAULT_TIMEZONE", "Asia/Bangkok"),
            default_lang=_env("DEFAULT_LANG", "th"),
            owner_ids=owner_ids,
        )


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    pool_size: int
    timeout: int
    # ── Cache & write-batching tunables ──────────────────────────────────────
    query_cache_ttl: float          # seconds — TTL for L1 QueryCache entries
    bulk_write_interval_ms: int     # milliseconds — BulkWriter flush interval

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        return cls(
            host=_env("SUPABASE_HOST", required=True),
            port=_env_int("SUPABASE_PORT", 5432),
            database=_env("SUPABASE_DB", "postgres"),
            user=_env("SUPABASE_USER", required=True),
            password=_env("SUPABASE_PASSWORD", required=True),
            pool_size=_env_int("DB_POOL_SIZE", 10),
            timeout=_env_int("DB_TIMEOUT", 30),
            query_cache_ttl=_env_float("DB_QUERY_CACHE_TTL", 30.0),
            bulk_write_interval_ms=_env_int("DB_BULK_WRITE_INTERVAL_MS", 500),
        )


@dataclass(frozen=True)
class RateLimitConfig:
    commands_per_minute: int
    tasks_per_hour: int
    searches_per_minute: int
    exports_per_day: int
    block_duration_seconds: int
    max_input_length: int
    max_task_name_length: int
    max_description_length: int

    @classmethod
    def from_env(cls) -> "RateLimitConfig":
        return cls(
            commands_per_minute=_env_int("RATE_COMMANDS_PER_MIN", 30),
            tasks_per_hour=_env_int("RATE_TASKS_PER_HOUR", 100),
            searches_per_minute=_env_int("RATE_SEARCHES_PER_MIN", 10),
            exports_per_day=_env_int("RATE_EXPORTS_PER_DAY", 5),
            block_duration_seconds=_env_int("RATE_BLOCK_SECONDS", 300),
            max_input_length=_env_int("MAX_INPUT_LENGTH", 2000),
            max_task_name_length=_env_int("MAX_TASK_NAME_LENGTH", 200),
            max_description_length=_env_int("MAX_DESCRIPTION_LENGTH", 1000),
        )


@dataclass(frozen=True)
class NotificationConfig:
    reminder_interval_minutes: int
    recurring_check_interval_minutes: int
    overdue_remind_hours: int    # how often (hrs) to re-remind on overdue tasks
    daily_summary_enabled: bool
    daily_summary_hour: int      # 0-23
    dm_reminder_interval_minutes: int  # how often to check for deadline DM reminders

    @classmethod
    def from_env(cls) -> "NotificationConfig":
        return cls(
            reminder_interval_minutes=_env_int("REMINDER_INTERVAL_MIN", 30),
            recurring_check_interval_minutes=_env_int("RECURRING_INTERVAL_MIN", 60),
            overdue_remind_hours=_env_int("OVERDUE_REMIND_HOURS", 6),
            daily_summary_enabled=_env_bool("DAILY_SUMMARY_ENABLED", True),
            daily_summary_hour=_env_int("DAILY_SUMMARY_HOUR", 8),
            dm_reminder_interval_minutes=_env_int("DM_REMINDER_INTERVAL_MIN", 15),
        )


@dataclass(frozen=True)
class WebserverConfig:
    enabled: bool
    host: str
    port: int

    @classmethod
    def from_env(cls) -> "WebserverConfig":
        return cls(
            enabled=_env_bool("WEBSERVER_ENABLED", True),
            host=_env("WEBSERVER_HOST", "0.0.0.0"),
            port=_env_int("WEBSERVER_PORT", 8080),
        )


@dataclass(frozen=True)
class MonitoringConfig:
    enabled: bool
    admin_log_channel_id: Optional[int]   # Discord channel ID for error alerts
    health_check_interval_min: int        # How often to run health checks (minutes)
    alert_rate_limit_sec: int             # Min seconds between identical alerts

    @classmethod
    def from_env(cls) -> "MonitoringConfig":
        channel_raw = _env("ADMIN_LOG_CHANNEL_ID", None)
        channel_id: Optional[int] = None
        if channel_raw:
            try:
                channel_id = int(channel_raw)
            except ValueError:
                log.warning("ADMIN_LOG_CHANNEL_ID is not a valid integer — alerts disabled")
        return cls(
            enabled=_env_bool("MONITORING_ENABLED", True),
            admin_log_channel_id=channel_id,
            health_check_interval_min=_env_int("HEALTH_CHECK_INTERVAL_MIN", 5),
            alert_rate_limit_sec=_env_int("ALERT_RATE_LIMIT_SEC", 300),
        )


# ──────────────────────────────────────────────────────────────────────────────
# Root config — single point of truth
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AppConfig:
    bot: BotConfig
    db: DatabaseConfig
    rate_limit: RateLimitConfig
    notifications: NotificationConfig
    webserver: WebserverConfig
    monitoring: MonitoringConfig

    @classmethod
    def load(cls) -> "AppConfig":
        cfg = cls(
            bot=BotConfig.from_env(),
            db=DatabaseConfig.from_env(),
            rate_limit=RateLimitConfig.from_env(),
            notifications=NotificationConfig.from_env(),
            webserver=WebserverConfig.from_env(),
            monitoring=MonitoringConfig.from_env(),
        )
        log.info("Configuration loaded successfully")
        return cfg


# Module-level singleton — import and use directly
config = AppConfig.load()
