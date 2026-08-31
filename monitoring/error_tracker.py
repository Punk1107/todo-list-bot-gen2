"""
monitoring/error_tracker.py — Aggregate and count errors in-memory.

Usage:
    from monitoring.error_tracker import error_tracker

    error_tracker.record(exc, command="task add", user_id="123456")
    embed = error_tracker.get_summary_embed()

The tracker auto-resets counters every 24 hours so the dashboard
always shows "errors in the last 24 h" rather than a forever-growing total.
"""
from __future__ import annotations

import asyncio
import logging
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import discord

log = logging.getLogger(__name__)

# ── Data model ───────────────────────────────────────────────────────────────

@dataclass
class ErrorEntry:
    error_type: str          # e.g. "ValueError", "asyncpg.PostgresError"
    count: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    last_user_id: str = "-"
    last_command: str = "-"
    snippet: str = ""        # short traceback (last 3 lines)


# ── Tracker ──────────────────────────────────────────────────────────────────

class ErrorTracker:
    """
    Thread-safe (asyncio-safe) in-memory error aggregator.

    - Uses a simple dict; access is safe because CPython's GIL protects
      dict operations and all callers run on the same event loop thread.
    - Auto-resets every 24 hours via a background asyncio.Task.
    """

    _RESET_INTERVAL = 86_400   # 24 hours

    def __init__(self) -> None:
        self._entries: Dict[str, ErrorEntry] = {}
        self._total_errors: int = 0
        self._reset_at: float = time.time() + self._RESET_INTERVAL
        self._task: Optional[asyncio.Task] = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the auto-reset background task. Call after event loop is running."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._auto_reset_loop(), name="error_tracker_reset")
            log.info("ErrorTracker auto-reset task started (interval: 24h)")

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    async def _auto_reset_loop(self) -> None:
        while True:
            await asyncio.sleep(self._RESET_INTERVAL)
            self.reset()
            log.info("ErrorTracker: daily reset complete")

    # ── Core API ─────────────────────────────────────────────────────────────

    def record(
        self,
        error: BaseException,
        *,
        command: str = "-",
        user_id: str = "-",
    ) -> ErrorEntry:
        """
        Record an exception. Returns the (updated) ErrorEntry for the caller
        to forward to AlertDispatcher if needed.
        """
        error_type = type(error).__name__
        snippet = self._extract_snippet(error)

        if error_type in self._entries:
            entry = self._entries[error_type]
            entry.count += 1
            entry.last_seen = time.time()
            entry.last_user_id = user_id
            entry.last_command = command
            entry.snippet = snippet
        else:
            entry = ErrorEntry(
                error_type=error_type,
                count=1,
                last_user_id=user_id,
                last_command=command,
                snippet=snippet,
            )
            self._entries[error_type] = entry

        self._total_errors += 1
        log.debug("ErrorTracker recorded: %s (total count: %d)", error_type, entry.count)
        return entry

    def get_top_errors(self, n: int = 5) -> List[ErrorEntry]:
        """Return top-N errors sorted by count descending."""
        return sorted(self._entries.values(), key=lambda e: e.count, reverse=True)[:n]

    def reset(self) -> None:
        """Manually reset all counters (also called by auto-reset loop)."""
        self._entries.clear()
        self._total_errors = 0
        self._reset_at = time.time() + self._RESET_INTERVAL

    @property
    def total_errors(self) -> int:
        return self._total_errors

    @property
    def unique_error_types(self) -> int:
        return len(self._entries)

    # ── Discord Embed ────────────────────────────────────────────────────────

    def get_summary_embed(self) -> discord.Embed:
        """Build a colour-coded Discord Embed showing error stats."""
        top = self.get_top_errors(5)
        total = self._total_errors
        next_reset_ts = int(self._reset_at)

        # Colour logic: green = 0 errors, yellow = 1-10, red = 10+
        if total == 0:
            color = 0x2ECC71   # green
        elif total <= 10:
            color = 0xF39C12   # amber
        else:
            color = 0xE74C3C   # red

        embed = discord.Embed(
            title="🚨 Error Report (Last 24 h)",
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="📊 Overview",
            value=(
                f"**Total errors:** {total}\n"
                f"**Unique types:** {self.unique_error_types}\n"
                f"**Resets:** <t:{next_reset_ts}:R>"
            ),
            inline=False,
        )

        if not top:
            embed.add_field(name="✅ Status", value="No errors recorded — all clear!", inline=False)
        else:
            for entry in top:
                last_ts = int(entry.last_seen)
                embed.add_field(
                    name=f"❌ `{entry.error_type}` × {entry.count}",
                    value=(
                        f"Last seen: <t:{last_ts}:R>\n"
                        f"Command: `{entry.last_command}`  |  User: `{entry.last_user_id}`\n"
                        f"```\n{entry.snippet[:200]}\n```"
                    ),
                    inline=False,
                )

        embed.set_footer(text="monitoring/error_tracker.py")
        return embed

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_snippet(error: BaseException, lines: int = 3) -> str:
        """Extract the last N lines of a traceback as a short snippet."""
        tb_lines = traceback.format_exception(type(error), error, error.__traceback__)
        full = "".join(tb_lines)
        # Take last `lines` non-empty lines
        parts = [l for l in full.splitlines() if l.strip()]
        return "\n".join(parts[-lines:])


# ── Module-level singleton ────────────────────────────────────────────────────
error_tracker = ErrorTracker()
