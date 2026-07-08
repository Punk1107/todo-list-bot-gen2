"""
handlers/reminders_cog.py — Background loops v4 (DB & Transport Upgrade)
Changes over v3:
  - reminder_loop: LIMIT 50 → 100, uses compound index idx_tasks_compound_status_dl
  - cleanup_loop: also purges query_cache expired entries
  - New: db_wal_checkpoint_loop — runs PRAGMA wal_checkpoint(TRUNCATE) every N hours
    to keep WAL file size bounded under sustained write load
  - All DB calls async, structured logging preserved
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks
import pytz

from core.database import db
from core.config import config
from locales.i18n import t
from utils.helpers import (
    format_deadline, time_left_str, calculate_next_deadline,
)

log = logging.getLogger(__name__)

UTC = pytz.utc

# Priority icons: index = priority value (0=lowest → 7=highest)
_PRIO_ICONS = ["⬜", "🟦", "🟩", "🟨", "🟧", "🟥", "🔴", "🆘"]


class RemindersCog(commands.Cog, name="Reminders"):
    """Background task loops: reminders, recurring, backup, cache, digest, WAL."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._digest_sent_today: set[str] = set()
        self._digest_day: str = ""

        # Configure intervals from config
        self.reminder_loop.change_interval(
            minutes=config.notifications.reminder_interval_minutes
        )
        self.recurring_loop.change_interval(
            minutes=config.notifications.recurring_check_interval_minutes
        )
        self.backup_loop.change_interval(
            hours=config.db.backup_interval_hours
        )
        self.db_wal_checkpoint_loop.change_interval(
            hours=config.db.wal_checkpoint_interval_hours
        )

        self.reminder_loop.start()
        self.recurring_loop.start()
        self.backup_loop.start()
        self.cleanup_loop.start()
        self.daily_digest_loop.start()
        self.db_wal_checkpoint_loop.start()

        log.info(
            "RemindersCog started — reminder=%dmin recurring=%dmin backup=%dh wal_checkpoint=%dh",
            config.notifications.reminder_interval_minutes,
            config.notifications.recurring_check_interval_minutes,
            config.db.backup_interval_hours,
            config.db.wal_checkpoint_interval_hours,
        )

    def cog_unload(self) -> None:
        self.reminder_loop.cancel()
        self.recurring_loop.cancel()
        self.backup_loop.cancel()
        self.cleanup_loop.cancel()
        self.daily_digest_loop.cancel()
        self.db_wal_checkpoint_loop.cancel()

    # ── Reminder loop ─────────────────────────────────────────────────────────

    @tasks.loop(minutes=30)
    async def reminder_loop(self) -> None:
        """Send reminders for tasks due soon or overdue (respects notify_enabled).
        Uses compound index idx_tasks_compound_status_dl for fast filtering.
        Processes up to 100 tasks per run (was 50).
        """
        now            = datetime.now(UTC)
        soon_threshold = (now + timedelta(hours=24)).isoformat()
        remind_cutoff  = (now - timedelta(hours=config.notifications.overdue_remind_hours)).isoformat()

        rows = await db.afetchall(
            """SELECT t.task_id, t.task, t.deadline, t.is_pinned, t.priority,
                      u.user_id, u.channel_id, u.timezone, u.lang, u.notify_enabled
               FROM tasks t
               JOIN users u ON t.owner_id = u.user_id
               WHERE t.status = 'Pending'
                 AND t.deadline <= ?
                 AND t.deadline > ?
                 AND u.notify_enabled = 1
                 AND u.channel_id IS NOT NULL
                 AND (t.last_reminder IS NULL OR t.last_reminder < ?)
               ORDER BY t.deadline ASC
               LIMIT 100""",
            (soon_threshold, (now - timedelta(days=30)).isoformat(), remind_cutoff),
        )

        # Batch-update last_reminder timestamps to reduce individual execute() calls
        reminder_updates: list[tuple[str, tuple]] = []

        for row in rows:
            channel = self.bot.get_channel(row["channel_id"])
            if not channel:
                continue

            lang    = row["lang"] or "th"
            tz_name = row["timezone"] or "Asia/Bangkok"
            tid     = row["task_id"]

            try:
                dt = datetime.fromisoformat(row["deadline"])
                if dt.tzinfo is None:
                    dt = UTC.localize(dt)
                is_overdue = dt < now

                if is_overdue:
                    msg   = t("reminder_overdue", lang,
                              task=row["task"], deadline=format_deadline(row["deadline"], tz_name))
                    color = 0xED4245
                    icon  = "🚨"
                else:
                    msg   = t("reminder_due_soon", lang,
                              task=row["task"], time_left=time_left_str(row["deadline"]))
                    color = 0xE67E22
                    icon  = "⏰"

                pin_note  = " 📌" if row["is_pinned"] else ""
                prio_icon = _PRIO_ICONS[min(row["priority"], 7)]

                embed = discord.Embed(
                    title=f"{icon} {t('reminder_title', lang)}{pin_note}",
                    description=msg,
                    color=color,
                )
                embed.add_field(
                    name="📅 Deadline",
                    value=f"`{format_deadline(row['deadline'], tz_name)}`  ({time_left_str(row['deadline'])})",
                    inline=True,
                )
                embed.add_field(
                    name="⚡ Priority",
                    value=prio_icon,
                    inline=True,
                )
                embed.set_footer(text=t("footer_text", lang))

                await channel.send(f"<@{row['user_id']}>", embed=embed)

                # Queue last_reminder update into BulkWriter instead of individual execute()
                reminder_updates.append((
                    "UPDATE tasks SET last_reminder=CURRENT_TIMESTAMP WHERE task_id=?",
                    (tid,),
                ))
                log.debug("Reminder sent: task_id=%d user=%s", tid, row["user_id"])
            except discord.Forbidden:
                log.warning("No permission to send reminder in channel %s", row["channel_id"])
            except Exception as exc:
                log.error("Reminder error task_id=%d: %s", tid, exc)

        # Flush all last_reminder updates as a batch
        if reminder_updates:
            try:
                await db.aexecute_batch(reminder_updates)
            except Exception as exc:
                log.error("Batch reminder update failed: %s", exc)

    @reminder_loop.before_loop
    async def before_reminder(self) -> None:
        await self.bot.wait_until_ready()

    # ── Recurring loop ────────────────────────────────────────────────────────

    @tasks.loop(minutes=60)
    async def recurring_loop(self) -> None:
        """Renew recurring tasks whose deadline has passed (idempotent check)."""
        now     = datetime.now(UTC).isoformat()
        expired = await db.afetchall(
            """SELECT * FROM tasks
               WHERE status='Pending' AND recurring IS NOT NULL AND deadline < ?""",
            (now,),
        )
        for row in expired:
            nxt = calculate_next_deadline(row["deadline"], row["recurring"])
            if not nxt:
                continue
            try:
                # Batch both the complete + new insert in one transaction
                await db.aexecute_batch([
                    (
                        "UPDATE tasks SET status='Completed', updated_at=CURRENT_TIMESTAMP WHERE task_id=?",
                        (row["task_id"],),
                    ),
                    (
                        """INSERT INTO tasks (task, deadline, priority, status, recurring,
                           category_id, tags, description, owner_id)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (row["task"], nxt, row["priority"], "Pending", row["recurring"],
                         row["category_id"], row["tags"], row["description"], row["owner_id"]),
                    ),
                ])
                db.invalidate_stats(row["owner_id"])
                log.info("Recurring task renewed: id=%d owner=%s next=%s",
                         row["task_id"], row["owner_id"], nxt[:16])
            except Exception as exc:
                log.error("Recurring renewal failed id=%d: %s", row["task_id"], exc)

    @recurring_loop.before_loop
    async def before_recurring(self) -> None:
        await self.bot.wait_until_ready()

    # ── Daily digest ──────────────────────────────────────────────────────────

    @tasks.loop(minutes=5)
    async def daily_digest_loop(self) -> None:
        """
        Send a daily digest at the configured hour.
        Runs every 5 min but only fires once per user per UTC day.
        """
        now = datetime.now(UTC)
        if now.hour != config.notifications.daily_summary_hour:
            return
        if not config.notifications.daily_summary_enabled:
            return

        # Reset tracking at midnight
        today_key = now.strftime("%Y-%m-%d")
        if self._digest_day != today_key:
            self._digest_sent_today = set()
            self._digest_day = today_key

        users = await db.afetchall(
            """SELECT user_id, channel_id, timezone, lang
               FROM users
               WHERE daily_digest=1 AND notify_enabled=1 AND channel_id IS NOT NULL""",
        )

        for user in users:
            uid = user["user_id"]
            if uid in self._digest_sent_today:
                continue

            channel = self.bot.get_channel(user["channel_id"])
            if not channel:
                continue

            lang    = user["lang"] or "th"
            tz_name = user["timezone"] or "Asia/Bangkok"

            try:
                local_tz   = pytz.timezone(tz_name)
                local_now  = now.astimezone(local_tz)
                day_start  = local_now.replace(hour=0, minute=0, second=0).astimezone(UTC).isoformat()
                day_end    = local_now.replace(hour=23, minute=59, second=59).astimezone(UTC).isoformat()
            except Exception:
                continue

            today_tasks = await db.afetchall(
                """SELECT task_id, task, deadline, priority FROM tasks
                   WHERE owner_id=? AND status='Pending'
                     AND deadline BETWEEN ? AND ?
                   ORDER BY priority DESC, deadline ASC LIMIT 10""",
                (uid, day_start, day_end),
            )
            overdue_row = await db.afetchone(
                "SELECT COUNT(*) AS c FROM tasks WHERE owner_id=? AND status='Pending' AND deadline<?",
                (uid, now.isoformat()),
            )
            overdue_count = overdue_row["c"] if overdue_row else 0

            embed = discord.Embed(
                title=f"☀️ {'สรุป Task วันนี้' if lang == 'th' else 'Daily Task Digest'} — {local_now.strftime('%d/%m/%Y')}",
                color=0x5865F2,
            )
            if today_tasks:
                lines = [
                    f"{_PRIO_ICONS[min(r['priority'], 7)]} `#{r['task_id']}` **{r['task'][:50]}** — `{format_deadline(r['deadline'], tz_name)}`"
                    for r in today_tasks
                ]
                embed.add_field(
                    name="📅 " + ("Task วันนี้" if lang == "th" else "Today's Tasks"),
                    value="\n".join(lines),
                    inline=False,
                )
            else:
                embed.description = "> ✅ " + ("ไม่มี Task วันนี้!" if lang == "th" else "No tasks due today!")

            if overdue_count > 0:
                embed.add_field(
                    name="🚨 Overdue",
                    value=f"**{overdue_count}** task(s) — use `/overdue`",
                    inline=False,
                )
            embed.set_footer(text=t("footer_text", lang))

            try:
                await channel.send(f"<@{uid}>", embed=embed)
                self._digest_sent_today.add(uid)
            except Exception as exc:
                log.error("Daily digest send error uid=%s: %s", uid, exc)

    @daily_digest_loop.before_loop
    async def before_digest(self) -> None:
        await self.bot.wait_until_ready()

    # ── DB Backup ─────────────────────────────────────────────────────────────

    @tasks.loop(hours=24)
    async def backup_loop(self) -> None:
        import asyncio
        path = await asyncio.to_thread(db.backup)
        if path:
            log.info("Scheduled DB backup: %s", path)

    @backup_loop.before_loop
    async def before_backup(self) -> None:
        await self.bot.wait_until_ready()

    # ── WAL checkpoint ────────────────────────────────────────────────────────

    @tasks.loop(hours=6)
    async def db_wal_checkpoint_loop(self) -> None:
        """
        Truncate the WAL file periodically to keep disk usage bounded.
        Interval is configurable via DB_WAL_CHECKPOINT_HOURS (default 6h).
        """
        await db.awa_checkpoint()

    @db_wal_checkpoint_loop.before_loop
    async def before_wal(self) -> None:
        await self.bot.wait_until_ready()

    # ── Cache + rate-limiter cleanup ──────────────────────────────────────────

    @tasks.loop(minutes=10)
    async def cleanup_loop(self) -> None:
        from core.security import rate_limiter
        rate_limiter.cleanup()
        counts = db.purge_all_caches()
        total_removed = sum(counts.values())
        if total_removed:
            log.debug("Cache cleanup: %s", counts)

    @cleanup_loop.before_loop
    async def before_cleanup(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RemindersCog(bot))
