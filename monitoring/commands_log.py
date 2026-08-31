"""
monitoring/commands_log.py — JSON-per-line command audit logger.

Writes to logs/commands.log — each line is a valid JSON object:
    {"ts": 1700000000.0, "cmd": "task add", "user": "123", "guild": "456",
     "success": true, "error_type": null, "latency_ms": 42.1}

Usage:
    from monitoring.commands_log import commands_logger

    # Log a successful command:
    commands_logger.log_command("task add", user_id="123", guild_id="456",
                                success=True, latency_ms=38.5)

    # Log a failed command:
    commands_logger.log_command("task delete", user_id="123", guild_id="456",
                                success=False, error_type="PermissionError")

    # Get in-memory stats (since last restart):
    stats = commands_logger.get_stats()
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

ROOT    = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"


class CommandsLogger:
    """
    Dual-purpose command logger:
      1. Writes a JSON audit trail to logs/commands.log.
      2. Keeps lightweight in-memory counters for fast /cmdstats responses.
    """

    def __init__(self) -> None:
        LOG_DIR.mkdir(exist_ok=True)

        # Set up a dedicated logger that only writes to commands.log
        self._file_log = logging.getLogger("monitoring.commands")
        self._file_log.setLevel(logging.DEBUG)
        self._file_log.propagate = False   # don't leak into root logger

        handler = logging.handlers.RotatingFileHandler(
            LOG_DIR / "commands.log",
            maxBytes=10_485_760,   # 10 MB
            backupCount=7,
            encoding="utf-8",
        )
        # Raw handler — we'll write pre-formatted JSON strings
        handler.setFormatter(logging.Formatter("%(message)s"))
        self._file_log.addHandler(handler)

        # ── In-memory counters (reset on restart) ────────────────────────────
        self._cmd_counts:    Counter = Counter()       # cmd → total calls
        self._cmd_errors:    Counter = Counter()       # cmd → error calls
        self._user_counts:   Counter = Counter()       # user_id → total calls
        self._error_types:   Counter = Counter()       # error_type → count
        self._total_latency: defaultdict = defaultdict(float)  # cmd → total ms

        log.info("CommandsLogger initialised — writing to logs/commands.log")

    # ── Public API ───────────────────────────────────────────────────────────

    def log_command(
        self,
        name: str,
        *,
        user_id: str = "-",
        guild_id: str = "-",
        success: bool = True,
        error_type: Optional[str] = None,
        latency_ms: float = 0.0,
    ) -> None:
        """
        Record a command invocation.

        Args:
            name:       Slash command name (e.g. "task add")
            user_id:    Discord user ID string
            guild_id:   Discord guild ID string (or "DM")
            success:    True if command completed without error
            error_type: Exception class name if not success
            latency_ms: Time from interaction received to response sent
        """
        record = {
            "ts":         round(time.time(), 3),
            "cmd":        name,
            "user":       user_id,
            "guild":      guild_id,
            "success":    success,
            "error_type": error_type,
            "latency_ms": round(latency_ms, 2),
        }
        self._file_log.info(json.dumps(record, ensure_ascii=False))

        # Update in-memory counters
        self._cmd_counts[name]  += 1
        self._user_counts[user_id] += 1
        self._total_latency[name]  += latency_ms

        if not success:
            self._cmd_errors[name] += 1
            if error_type:
                self._error_types[error_type] += 1

    def get_stats(self, top_n: int = 10) -> Dict:
        """
        Return aggregated stats since the last bot restart.

        Returns:
            dict with keys:
              top_commands:  list of (cmd, count, error_rate_pct, avg_latency_ms)
              top_users:     list of (user_id, count)
              top_errors:    list of (error_type, count)
              total_calls:   int
              total_errors:  int
        """
        total_calls  = sum(self._cmd_counts.values())
        total_errors = sum(self._cmd_errors.values())

        top_commands: List[Tuple] = []
        for cmd, count in self._cmd_counts.most_common(top_n):
            errors      = self._cmd_errors.get(cmd, 0)
            error_rate  = round((errors / count) * 100, 1) if count else 0.0
            avg_latency = round(self._total_latency[cmd] / count, 1) if count else 0.0
            top_commands.append((cmd, count, error_rate, avg_latency))

        return {
            "top_commands": top_commands,
            "top_users":    self._user_counts.most_common(top_n),
            "top_errors":   self._error_types.most_common(top_n),
            "total_calls":  total_calls,
            "total_errors": total_errors,
        }

    def get_stats_embed(self, top_n: int = 10) -> "discord.Embed":  # type: ignore[name-defined]
        """Build a Discord Embed with command usage stats."""
        import discord  # local import to avoid circular dependency at module level

        stats = self.get_stats(top_n=top_n)
        total  = stats["total_calls"]
        errors = stats["total_errors"]
        error_rate = round((errors / total) * 100, 1) if total else 0.0

        color = 0x3498DB if error_rate < 5 else (0xF39C12 if error_rate < 20 else 0xE74C3C)

        embed = discord.Embed(
            title="📊 Command Usage Stats",
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="📈 Overview",
            value=(
                f"**Total calls:** {total}\n"
                f"**Errors:** {errors} ({error_rate}%)"
            ),
            inline=False,
        )

        if stats["top_commands"]:
            rows = []
            for i, (cmd, count, err_rate, avg_ms) in enumerate(stats["top_commands"], 1):
                err_icon = "🔴" if err_rate > 20 else ("🟡" if err_rate > 5 else "🟢")
                rows.append(
                    f"`{i:>2}.` **/{cmd}** — {count}× | {err_icon} {err_rate}% err | ⚡ {avg_ms}ms"
                )
            embed.add_field(
                name="🏆 Top Commands",
                value="\n".join(rows) or "—",
                inline=False,
            )

        if stats["top_errors"]:
            err_rows = [f"`{etype}` × {cnt}" for etype, cnt in stats["top_errors"][:5]]
            embed.add_field(
                name="⚠️ Frequent Error Types",
                value="\n".join(err_rows) or "—",
                inline=False,
            )

        embed.set_footer(text="Stats since last restart · monitoring/commands_log.py")
        return embed


# ── Module-level singleton ────────────────────────────────────────────────────
commands_logger = CommandsLogger()
