"""Pomodoro focus commands and durable session scheduling."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.database import db
from locales.i18n import t
from utils.helpers import ensure_user, format_deadline, get_user_lang, get_user_timezone

log = logging.getLogger(__name__)

WORK_MINUTES = 25
BREAK_MINUTES = 5
WORK_SECONDS = WORK_MINUTES * 60


def _completed_work_seconds(started_at: datetime, ends_at: datetime, now: datetime) -> int:
    """Return only elapsed work time, capped at the scheduled focus interval."""
    return max(0, min(int((min(now, ends_at) - started_at).total_seconds()), WORK_SECONDS))


class FocusCog(commands.Cog, name="Focus"):
    """Persistent work/break timers that add completed focus time to tasks."""

    focus = app_commands.Group(name="focus", description="Pomodoro focus timer")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.session_loop.start()

    def cog_unload(self) -> None:
        self.session_loop.cancel()

    @focus.command(name="start", description="Start a Pomodoro timer for a task")
    @app_commands.describe(task_id="Pending task to focus on")
    async def start(self, interaction: discord.Interaction, task_id: int) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        now = datetime.now(timezone.utc)
        task_name: Optional[str] = None
        active = False

        try:
            async with db.acquire() as conn:
                async with conn.transaction():
                    task = await conn.fetchrow(
                        """SELECT task FROM tasks
                           WHERE task_id=$1 AND owner_id=$2 AND status='Pending' AND is_deleted=FALSE""",
                        task_id, uid,
                    )
                    if task is None:
                        task_name = None
                    else:
                        task_name = task["task"]
                        active = await conn.fetchval(
                            "SELECT EXISTS(SELECT 1 FROM focus_sessions WHERE user_id=$1 AND status='active')",
                            uid,
                        )
                        if not active:
                            await conn.execute(
                                """INSERT INTO focus_sessions
                                   (user_id, task_id, phase, phase_started_at, phase_ends_at)
                                   VALUES ($1,$2,'work',$3,$4)""",
                                uid, task_id, now, now + timedelta(minutes=WORK_MINUTES),
                            )
            if task_name is None:
                await interaction.response.send_message(
                    t("focus_task_unavailable", lang), ephemeral=True
                )
                return
            if active:
                await interaction.response.send_message(
                    t("focus_already_active", lang), ephemeral=True
                )
                return
            db.query_cache.invalidate_table("focus_sessions")
            await interaction.response.send_message(
                t("focus_started", lang, task=task_name, minutes=WORK_MINUTES),
                ephemeral=True,
            )
        except asyncpg.UniqueViolationError:
            await interaction.response.send_message(
                t("focus_already_active", lang), ephemeral=True
            )
        except Exception as exc:
            log.exception("Could not start focus session for user=%s task=%d: %s", uid, task_id, exc)
            await interaction.response.send_message(t("err_db", lang), ephemeral=True)

    @focus.command(name="stop", description="Stop your active Pomodoro timer")
    async def stop(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        now = datetime.now(timezone.utc)
        elapsed_seconds = 0
        task_name: Optional[str] = None

        try:
            async with db.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        """SELECT fs.session_id, fs.task_id, fs.phase,
                                  fs.phase_started_at, fs.phase_ends_at, t.task
                           FROM focus_sessions fs
                           JOIN tasks t ON t.task_id=fs.task_id
                           WHERE fs.user_id=$1 AND fs.status='active'
                           FOR UPDATE OF fs""",
                        uid,
                    )
                    if row is None:
                        await interaction.response.send_message(
                            t("focus_no_active", lang), ephemeral=True
                        )
                        return

                    task_name = row["task"]
                    if row["phase"] == "work":
                        elapsed_seconds = _completed_work_seconds(
                            row["phase_started_at"], row["phase_ends_at"], now
                        )
                        if elapsed_seconds:
                            await conn.execute(
                                """UPDATE tasks
                                   SET actual_hours=COALESCE(actual_hours, 0)+$1
                                   WHERE task_id=$2""",
                                elapsed_seconds / 3600, row["task_id"],
                            )
                    await conn.execute(
                        """UPDATE focus_sessions
                           SET status='stopped', notification_pending=FALSE, updated_at=NOW()
                           WHERE session_id=$1""",
                        row["session_id"],
                    )
            if elapsed_seconds:
                db.invalidate_stats(uid)
            db.query_cache.invalidate_table("focus_sessions")
            await interaction.response.send_message(
                t("focus_stopped", lang, task=task_name, minutes=elapsed_seconds // 60),
                ephemeral=True,
            )
        except Exception as exc:
            log.exception("Could not stop focus session for user=%s: %s", uid, exc)
            await interaction.response.send_message(t("err_db", lang), ephemeral=True)

    @focus.command(name="status", description="Show your active Pomodoro timer")
    async def status(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        tz_name = await get_user_timezone(uid)
        row = await db.afetchone(
            """SELECT fs.phase, fs.phase_ends_at, t.task
               FROM focus_sessions fs
               JOIN tasks t ON t.task_id=fs.task_id
               WHERE fs.user_id=$1 AND fs.status='active'""",
            (uid,),
        )
        if row is None:
            await interaction.response.send_message(t("focus_no_active", lang), ephemeral=True)
            return
        phase_key = "focus_phase_work" if row["phase"] == "work" else "focus_phase_break"
        await interaction.response.send_message(
            t(
                "focus_status",
                lang,
                phase=t(phase_key, lang),
                task=row["task"],
                end_time=format_deadline(row["phase_ends_at"], tz_name),
            ),
            ephemeral=True,
        )

    @tasks.loop(seconds=15)
    async def session_loop(self) -> None:
        now = datetime.now(timezone.utc)
        due = await db.afetchall(
            """SELECT session_id FROM focus_sessions
               WHERE status='active'
                 AND (phase_ends_at <= $1 OR notification_pending=TRUE)""",
            (now,),
        )
        for due_row in due:
            await self._advance_or_notify(due_row["session_id"], now)

    @session_loop.before_loop
    async def before_session_loop(self) -> None:
        await self.bot.wait_until_ready()

    async def _advance_or_notify(self, session_id: int, now: datetime) -> None:
        changed_task: Optional[tuple[str, int]] = None
        notice: Optional[tuple[str, str, str, int]] = None
        try:
            async with db.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        """SELECT fs.session_id, fs.user_id, fs.task_id, fs.phase,
                                  fs.phase_started_at, fs.phase_ends_at,
                                  fs.notification_pending, t.task
                           FROM focus_sessions fs
                           JOIN tasks t ON t.task_id=fs.task_id
                           WHERE fs.session_id=$1 AND fs.status='active'
                           FOR UPDATE OF fs""",
                        session_id,
                    )
                    if row is None:
                        return

                    if row["notification_pending"]:
                        notice_key = "focus_work_finished" if row["phase"] == "break" else "focus_break_finished"
                        notice_duration = BREAK_MINUTES if row["phase"] == "break" else WORK_MINUTES
                        notice = (row["user_id"], notice_key, row["task"], notice_duration)
                    elif row["phase_ends_at"] <= now:
                        next_phase = "break" if row["phase"] == "work" else "work"
                        duration = BREAK_MINUTES if next_phase == "break" else WORK_MINUTES
                        if row["phase"] == "work":
                            elapsed_seconds = _completed_work_seconds(
                                row["phase_started_at"], row["phase_ends_at"], now
                            )
                            if elapsed_seconds:
                                await conn.execute(
                                    """UPDATE tasks
                                       SET actual_hours=COALESCE(actual_hours, 0)+$1
                                       WHERE task_id=$2""",
                                    elapsed_seconds / 3600, row["task_id"],
                                )
                                changed_task = (row["user_id"], row["task_id"])
                        await conn.execute(
                            """UPDATE focus_sessions
                               SET phase=$1, phase_started_at=$2, phase_ends_at=$3,
                                   notification_pending=TRUE, updated_at=NOW()
                               WHERE session_id=$4""",
                            next_phase, now, now + timedelta(minutes=duration), session_id,
                        )
                        notice_key = "focus_work_finished" if next_phase == "break" else "focus_break_finished"
                        notice = (row["user_id"], notice_key, row["task"], duration)

            if changed_task:
                db.invalidate_stats(changed_task[0])
            if notice or changed_task:
                db.query_cache.invalidate_table("focus_sessions")
            if notice:
                lang = await get_user_lang(notice[0])
                content = t(notice[1], lang, task=notice[2], minutes=notice[3])
                await self._deliver_notice(session_id, notice[0], content)
        except Exception as exc:
            log.exception("Focus timer advance failed for session=%d: %s", session_id, exc)

    async def _deliver_notice(self, session_id: int, user_id: str, content: str) -> None:
        try:
            user = self.bot.get_user(int(user_id))
            if user is None:
                user = await self.bot.fetch_user(int(user_id))
            await user.send(content)
        except discord.Forbidden:
            log.warning("Cannot DM focus notification to user=%s session=%d", user_id, session_id)
            await self._clear_pending_notice(session_id)
        except discord.NotFound:
            log.warning("Focus notification recipient not found: user=%s session=%d", user_id, session_id)
            await self._clear_pending_notice(session_id)
        except discord.HTTPException as exc:
            log.warning("Focus notification failed for user=%s session=%d: %s", user_id, session_id, exc)
            await self._clear_pending_notice(session_id)
        except Exception:
            log.exception("Unexpected focus notification failure for session=%d", session_id)
            await self._clear_pending_notice(session_id)
        else:
            await self._clear_pending_notice(session_id)

    @staticmethod
    async def _clear_pending_notice(session_id: int) -> None:
        await db.aexecute(
            """UPDATE focus_sessions SET notification_pending=FALSE, updated_at=NOW()
               WHERE session_id=$1 AND status='active'""",
            (session_id,),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FocusCog(bot))
