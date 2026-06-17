"""
core/security.py — Input sanitisation, rate limiting, and audit utilities.
No network calls; pure in-memory state.
"""
from __future__ import annotations

import logging
import re
import time
from collections import defaultdict, deque
from functools import wraps
from typing import Callable, TypeVar

import discord
from discord.ext import commands

from core.config import config
from locales.i18n import t

log = logging.getLogger(__name__)

_F = TypeVar("_F", bound=Callable)

# ─────────────────────────────────────────────────────────────────────────────
# Dangerous pattern detection
# ─────────────────────────────────────────────────────────────────────────────

# Patterns that look like SQL injection or script injection attempts
_SUSPICIOUS_RE = re.compile(
    r"(--|;|\bDROP\b|\bSELECT\b|\bINSERT\b|\bDELETE\b|\bUPDATE\b|"
    r"<script|javascript:|on\w+=)",
    re.IGNORECASE,
)

# Characters forbidden in task names / descriptions
_FORBIDDEN_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class InputValidator:
    """Static helpers for sanitising user text input."""

    @staticmethod
    def sanitize(text: str, max_length: int | None = None) -> str:
        """
        Strip null bytes and control characters.
        Truncates to max_length if specified.
        """
        text = _FORBIDDEN_CHARS_RE.sub("", text).strip()
        if max_length:
            text = text[:max_length]
        return text

    @staticmethod
    def is_suspicious(text: str) -> bool:
        """Return True if the text contains potentially dangerous patterns."""
        return bool(_SUSPICIOUS_RE.search(text))

    @staticmethod
    def validate_task_name(text: str) -> tuple[bool, str]:
        """
        Returns (is_valid, cleaned_text | error_key).
        error_key is an i18n key string on failure.
        """
        cleaned = InputValidator.sanitize(text, config.rate_limit.max_task_name_length)
        if not cleaned:
            return False, "err_input_invalid"
        if InputValidator.is_suspicious(cleaned):
            return False, "err_suspicious"
        return True, cleaned

    @staticmethod
    def validate_description(text: str) -> tuple[bool, str]:
        cleaned = InputValidator.sanitize(text, config.rate_limit.max_description_length)
        if InputValidator.is_suspicious(cleaned):
            return False, "err_suspicious"
        return True, cleaned


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limiter
# ─────────────────────────────────────────────────────────────────────────────

class RateLimiter:
    """
    In-memory token-bucket style rate limiter.
    Tracks commands, task creations, searches, and exports per user.
    """

    def __init__(self) -> None:
        rl = config.rate_limit
        self._cmds:    dict[str, deque[float]] = defaultdict(deque)
        self._tasks:   dict[str, deque[float]] = defaultdict(deque)
        self._search:  dict[str, deque[float]] = defaultdict(deque)
        self._exports: dict[str, deque[float]] = defaultdict(deque)
        self._blocked: dict[str, float] = {}   # user_id → unblock_at

        self._cmd_limit:    int = rl.commands_per_minute
        self._task_limit:   int = rl.tasks_per_hour
        self._search_limit: int = rl.searches_per_minute
        self._export_limit: int = rl.exports_per_day
        self._block_dur:    int = rl.block_duration_seconds

        self._stats = {"total": 0, "blocked": 0, "cleanups": 0}

    # ── Internal ──────────────────────────────────────────────────────────────

    def _check(
        self,
        uid: str,
        bucket: dict[str, deque[float]],
        window: int,
        limit: int,
        label: str,
    ) -> bool:
        now = time.monotonic()
        q = bucket[uid]
        while q and q[0] < now - window:
            q.popleft()
        if len(q) >= limit:
            self._blocked[uid] = now + self._block_dur
            log.warning("Rate limit [%s] — user=%s count=%d", label, uid, len(q))
            self._stats["blocked"] += 1
            return True           # is limited
        q.append(now)
        return False

    # ── Public ────────────────────────────────────────────────────────────────

    def check_command(self, uid: str) -> bool:
        self._stats["total"] += 1
        if uid in self._blocked and time.monotonic() < self._blocked[uid]:
            self._stats["blocked"] += 1
            return True
        elif uid in self._blocked:
            del self._blocked[uid]
        return self._check(uid, self._cmds, 60, self._cmd_limit, "cmd")

    def check_task_creation(self, uid: str) -> bool:
        return self._check(uid, self._tasks, 3600, self._task_limit, "task")

    def check_search(self, uid: str) -> bool:
        return self._check(uid, self._search, 60, self._search_limit, "search")

    def check_export(self, uid: str) -> bool:
        return self._check(uid, self._exports, 86400, self._export_limit, "export")

    def remaining_block_seconds(self, uid: str) -> float:
        if uid in self._blocked:
            return max(0.0, self._blocked[uid] - time.monotonic())
        return 0.0

    def cleanup(self) -> None:
        """Purge stale entries — call periodically from a background task."""
        now = time.monotonic()
        for bucket, window in (
            (self._cmds, 60),
            (self._tasks, 3600),
            (self._search, 60),
            (self._exports, 86400),
        ):
            for uid in list(bucket):
                q = bucket[uid]
                while q and q[0] < now - window:
                    q.popleft()
                if not q:
                    del bucket[uid]
        self._blocked = {u: t for u, t in self._blocked.items() if t > now}
        self._stats["cleanups"] += 1

    @property
    def stats(self) -> dict:
        return dict(self._stats)


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singletons
# ─────────────────────────────────────────────────────────────────────────────

validator = InputValidator()
rate_limiter = RateLimiter()


# ─────────────────────────────────────────────────────────────────────────────
# Decorator
# ─────────────────────────────────────────────────────────────────────────────

def rate_limit_check(check_type: str = "command"):
    """
    Slash-command decorator that enforces rate limiting and returns an
    ephemeral error to the user in their language if exceeded.

    Usage:
        @app_commands.command()
        @rate_limit_check("command")
        async def my_cmd(interaction, ...): ...
    """
    def decorator(func: _F) -> _F:
        @wraps(func)
        async def wrapper(self_or_interaction, *args, **kwargs):
            # Handle both bound (self, interaction) and unbound (interaction) cases
            if isinstance(self_or_interaction, discord.Interaction):
                interaction: discord.Interaction = self_or_interaction
                remaining_args = args
            else:
                # self_or_interaction is `self` (Cog), args[0] is interaction
                interaction = args[0]
                remaining_args = args[1:]

            uid = str(interaction.user.id)

            # Determine which rate-limit check to run
            limited = False
            if check_type == "command":
                limited = rate_limiter.check_command(uid)
            elif check_type == "task":
                limited = rate_limiter.check_task_creation(uid)
            elif check_type == "search":
                limited = rate_limiter.check_search(uid)
            elif check_type == "export":
                limited = rate_limiter.check_export(uid)

            if limited:
                from core.database import db
                row = db.fetchone("SELECT lang FROM users WHERE user_id=?", (uid,))
                lang = row["lang"] if row else config.bot.default_lang
                secs = rate_limiter.remaining_block_seconds(uid)

                if check_type == "task":
                    msg = t("task_rate_limited", lang,
                            limit=config.rate_limit.tasks_per_hour, seconds=secs)
                else:
                    msg = t("rate_limited", lang, seconds=secs)

                await interaction.response.send_message(msg, ephemeral=True)
                return

            if isinstance(self_or_interaction, discord.Interaction):
                await func(self_or_interaction, *remaining_args, **kwargs)
            else:
                await func(self_or_interaction, interaction, *remaining_args, **kwargs)

        return wrapper  # type: ignore[return-value]
    return decorator
