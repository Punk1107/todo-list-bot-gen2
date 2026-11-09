"""Pomodoro focus commands and durable session scheduling."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.database import db
from focus import voice_service
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
    voice = app_commands.Group(name="voice", description="Virtual Focus Room voice channel sync", parent=focus)
    chime = app_commands.Group(name="chime", description="Harmonic bell audio alerts", parent=focus)

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.session_loop.start()
        self.voice_room_loop.start()

    def cog_unload(self) -> None:
        self.session_loop.cancel()
        self.voice_room_loop.cancel()

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
               WHERE fs.user_id=$1 AND fs.status='active' AND t.is_deleted=FALSE""",
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
                                  fs.notification_pending, t.task, t.is_deleted, t.status AS task_status
                           FROM focus_sessions fs
                           JOIN tasks t ON t.task_id=fs.task_id
                           WHERE fs.session_id=$1 AND fs.status='active'
                           FOR UPDATE OF fs""",
                        session_id,
                    )
                    if row is None:
                        return

                    if row.get("is_deleted") or row.get("task_status") in ("Completed", "Cancelled"):
                        await conn.execute(
                            """UPDATE focus_sessions
                               SET status='stopped', notification_pending=FALSE, updated_at=NOW()
                               WHERE session_id=$1""",
                            session_id,
                        )
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

    # ─────────────────────────────────────────────────────────────────────────
    # Virtual Focus Room: /focus voice & /focus chime
    # ─────────────────────────────────────────────────────────────────────────

    @voice.command(name="bind", description="ผูกห้อง Voice Channel เข้ากับระบบ Virtual Focus Room")
    @app_commands.describe(
        channel="Voice channel to bind as Virtual Focus Room",
        work_minutes="ระยะเวลาทำงานต่อรอบ (default: 25 นาที)",
        break_minutes="ระยะเวลาพักต่อรอบ (default: 5 นาที)",
    )
    async def voice_bind(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
        work_minutes: Optional[int] = 25,
        break_minutes: Optional[int] = 5,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)

        if not interaction.guild:
            await interaction.response.send_message(t("proj_guild_only", lang), ephemeral=True)
            return

        wm = work_minutes if work_minutes and work_minutes > 0 else 25
        bm = break_minutes if break_minutes and break_minutes > 0 else 5
        guild_id = str(interaction.guild.id)
        cid = str(channel.id)

        await voice_service.bind_voice_room(guild_id, cid, uid, wm, bm)
        await interaction.response.send_message(
            t("focus_voice_bound", lang, channel=channel.mention, work=wm, rest=bm),
            ephemeral=False,
        )

    @voice.command(name="unbind", description="ยกเลิกการผูกห้อง Voice Channel ออกจากระบบ Focus Room")
    @app_commands.describe(channel="Voice channel to unbind")
    async def voice_unbind(self, interaction: discord.Interaction, channel: discord.VoiceChannel) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)

        cid = str(channel.id)
        ok = await voice_service.unbind_voice_room(cid)
        if ok:
            await voice_service.update_voice_channel_status(channel, None)
            await interaction.response.send_message(
                t("focus_voice_unbound", lang, channel=channel.mention),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                t("focus_voice_not_found", lang, channel=channel.mention),
                ephemeral=True,
            )

    @voice.command(name="status", description="ตรวจสอบสถานะรอบโฟกัสของห้อง Voice")
    @app_commands.describe(channel="Voice channel to inspect")
    async def voice_status(self, interaction: discord.Interaction, channel: discord.VoiceChannel) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        cid = str(channel.id)

        room = await voice_service.get_voice_room(cid)
        if not room:
            await interaction.response.send_message(
                t("focus_voice_not_found", lang, channel=channel.mention),
                ephemeral=True,
            )
            return

        phase_str = room["current_phase"]
        round_num = room["current_round"]
        ends_at = room.get("phase_ends_at")
        rem_str = f"<t:{int(ends_at.timestamp())}:R>" if ends_at else "—"

        embed = discord.Embed(
            title=f"🎙️ Focus Room: {channel.name}",
            description=(
                f"• **Status:** `{phase_str.upper()}`\n"
                f"• **Round:** `Round {round_num}`\n"
                f"• **Work/Break:** `{room['work_minutes']}m / {room['break_minutes']}m`\n"
                f"• **Phase Ends:** {rem_str}\n"
                f"• **Members in Room:** `{len([m for m in channel.members if not m.bot])} คน`"
            ),
            color=0x57F287 if phase_str == "work" else (0xFEE75C if phase_str == "break" else 0x5865F2),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @chime.command(name="toggle", description="เปิดหรือปิดเสียงระฆังสมาธิ (Focus Chimes) ส่วนตัว")
    async def chime_toggle(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)

        new_val = await voice_service.toggle_user_chime(uid)
        msg_key = "focus_chime_enabled" if new_val else "focus_chime_disabled"
        await interaction.response.send_message(t(msg_key, lang), ephemeral=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Voice State Event Listener & Background Room Loop
    # ─────────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Auto-start Focus Room when members join, auto-reset when empty."""
        if member.bot:
            return

        now = datetime.now(timezone.utc)
        # Check channel joined
        if after.channel and after.channel != before.channel:
            cid = str(after.channel.id)
            room = await voice_service.get_voice_room(cid)
            if room and room["current_phase"] == "idle":
                # Start Work Phase
                wm = room["work_minutes"]
                ends_at = now + timedelta(minutes=wm)
                await voice_service.update_room_phase(cid, "work", 1, ends_at)
                await voice_service.update_voice_channel_status(
                    after.channel, f"🍅 Focus Round 1 (เหลืออีก {wm} นาที)"
                )
                if room.get("chime_enabled", True):
                    asyncio.create_task(voice_service.play_chime_in_voice(after.channel, "work"))

        # Check channel left
        if before.channel and before.channel != after.channel:
            cid = str(before.channel.id)
            room = await voice_service.get_voice_room(cid)
            if room:
                non_bot_count = len([m for m in before.channel.members if not m.bot])
                if non_bot_count == 0:
                    # Reset to idle
                    await voice_service.reset_room_to_idle(cid)
                    await voice_service.update_voice_channel_status(before.channel, None)

    @tasks.loop(seconds=20)
    async def voice_room_loop(self) -> None:
        """Periodic loop to advance active Focus Room phases and update channel statuses."""
        now = datetime.now(timezone.utc)
        rooms = await voice_service.get_all_active_voice_rooms()
        for r in rooms:
            cid = r["channel_id"]
            phase = r["current_phase"]
            if phase == "idle":
                continue

            channel = self.bot.get_channel(int(cid))
            if not isinstance(channel, discord.VoiceChannel):
                continue

            non_bot_count = len([m for m in channel.members if not m.bot])
            if non_bot_count == 0:
                await voice_service.reset_room_to_idle(cid)
                await voice_service.update_voice_channel_status(channel, None)
                continue

            ends_at = r.get("phase_ends_at")
            if not ends_at:
                continue

            # Check if current phase has ended
            if ends_at <= now:
                if phase == "work":
                    # Transition to Break
                    bm = r["break_minutes"]
                    next_ends = now + timedelta(minutes=bm)
                    await voice_service.update_room_phase(cid, "break", r["current_round"], next_ends)
                    await voice_service.update_voice_channel_status(channel, f"☕ Break Time ({bm} นาที)")
                    if r.get("chime_enabled", True):
                        asyncio.create_task(voice_service.play_chime_in_voice(channel, "break"))
                else:
                    # Transition to next Work Round
                    next_round = r["current_round"] + 1
                    wm = r["work_minutes"]
                    next_ends = now + timedelta(minutes=wm)
                    await voice_service.update_room_phase(cid, "work", next_round, next_ends)
                    await voice_service.update_voice_channel_status(channel, f"🍅 Focus Round {next_round} (เหลืออีก {wm} นาที)")
                    if r.get("chime_enabled", True):
                        asyncio.create_task(voice_service.play_chime_in_voice(channel, "work"))
            else:
                # Update remaining minutes
                rem_mins = max(1, int((ends_at - now).total_seconds() // 60))
                if phase == "work":
                    status_str = f"🍅 Focus Round {r['current_round']} (เหลืออีก {rem_mins} นาที)"
                else:
                    status_str = f"☕ Break Time (เหลืออีก {rem_mins} นาที)"
                await voice_service.update_voice_channel_status(channel, status_str)

    @voice_room_loop.before_loop
    async def before_voice_room_loop(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FocusCog(bot))
