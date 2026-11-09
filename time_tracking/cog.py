"""
time_tracking/cog.py — Discord Slash Commands for Time Tracking, Timers, Capacity & Burnout Shield.
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from locales.i18n import t
from time_tracking import service
from time_tracking.views import (
    ActiveTimerControlsView,
    TimesheetExportView,
    build_capacity_embed,
    build_estimation_analytics_embed,
    build_timer_embed,
    build_timesheet_embed,
)
from utils.helpers import ensure_user, get_user_lang

log = logging.getLogger(__name__)


class TimeTrackingCog(commands.Cog, name="TimeTracking"):
    """Time Logging, Stopwatch Timers, Timesheets, Workload Capacity & Burnout Shield."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    time_group = app_commands.Group(
        name="time",
        description="⏱️ Time tracking, stopwatch timers, and timesheet analytics",
    )
    timer_subgroup = app_commands.Group(
        name="timer",
        description="⏳ Live stopwatch timers for tasks",
        parent=time_group,
    )
    workload_group = app_commands.Group(
        name="workload",
        description="🛡️ Workload capacity management and Burnout Shield",
    )

    # ─────────────────────────────────────────────────────────────────────────
    # /time log
    # ─────────────────────────────────────────────────────────────────────────

    @time_group.command(
        name="log",
        description="⏱️ บันทึกเวลาการทำงานลงใน Task / Manually log time spent on a task",
    )
    @app_commands.describe(
        task_id="ID of the task to log time for",
        hours="Number of hours spent (e.g. 1.5)",
        note="Optional description of work done",
        is_billable="Whether this work is billable (defaults to true if project has budget)",
    )
    async def time_log(
        self,
        interaction: discord.Interaction,
        task_id: int,
        hours: float,
        note: Optional[str] = None,
        is_billable: Optional[bool] = None,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)

        if hours <= 0:
            await interaction.response.send_message("❌ Hours must be greater than 0.", ephemeral=True)
            return

        # Check task existence
        task_row = await db.fetchone(
            "SELECT task_id, task, owner_id, project_id, is_private FROM tasks WHERE task_id = $1 AND is_deleted = FALSE",
            (task_id,),
        )
        if not task_row:
            await interaction.response.send_message(f"❌ Task `#{task_id}` not found.", ephemeral=True)
            return

        entry = await service.log_time(
            task_id=task_id,
            user_id=uid,
            hours=hours,
            note=note,
            is_billable=is_billable,
        )

        embed = discord.Embed(
            title=f"✅ {t('time_logged_success', lang)}",
            description=f"Logged **{entry.hours_spent:.2f} hrs** on task **#{task_id}: {task_row['task'][:60]}**",
            color=0x2ECC71,
        )
        embed.add_field(name="💼 Type", value="Billable" if entry.is_billable else "Non-Billable", inline=True)
        if entry.note:
            embed.add_field(name="📝 Note", value=entry.note, inline=True)

        await interaction.response.send_message(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # /time timer (start / stop / status)
    # ─────────────────────────────────────────────────────────────────────────

    @timer_subgroup.command(
        name="start",
        description="▶️ เริ่มต้นจับเวลาการทำงาน (Stopwatch) / Start live stopwatch timer",
    )
    @app_commands.describe(
        task_id="ID of the task to time",
        note="Optional note on what you're working on",
    )
    async def timer_start(
        self,
        interaction: discord.Interaction,
        task_id: int,
        note: Optional[str] = None,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)

        task_row = await db.fetchone(
            "SELECT task_id, task FROM tasks WHERE task_id = $1 AND is_deleted = FALSE",
            (task_id,),
        )
        if not task_row:
            await interaction.response.send_message(f"❌ Task `#{task_id}` not found.", ephemeral=True)
            return

        active = await service.get_active_timer(uid)
        if active:
            embed = build_timer_embed(interaction.user.display_name, active)
            view = ActiveTimerControlsView(uid, active)
            await interaction.response.send_message(
                content=f"⚠️ {t('time_timer_already_running', lang)} Stop or cancel your existing timer first:",
                embed=embed,
                view=view,
                ephemeral=True,
            )
            return

        timer = await service.start_timer(uid, task_id, note)
        embed = build_timer_embed(interaction.user.display_name, timer)
        view = ActiveTimerControlsView(uid, timer)
        await interaction.response.send_message(
            content=f"⏳ {t('time_timer_started', lang)}",
            embed=embed,
            view=view,
        )

    @timer_subgroup.command(
        name="stop",
        description="⏹️ หยุดและบันทึกเวลาที่จับได้ / Stop stopwatch timer and log time",
    )
    async def timer_stop(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)

        res = await service.stop_timer(uid)
        if not res:
            await interaction.response.send_message(
                f"ℹ️ {t('time_timer_none', lang)}",
                ephemeral=True,
            )
            return

        timer, entry = res
        embed = build_timer_embed(interaction.user.display_name, timer, is_stopped=True, logged_entry=entry)
        await interaction.response.send_message(
            content=f"✅ {t('time_timer_stopped', lang)}",
            embed=embed,
        )

    @timer_subgroup.command(
        name="status",
        description="🔍 ดูสถานะตัวจับเวลาที่กำลังเดินอยู่ / View currently running stopwatch timer",
    )
    async def timer_status(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)

        timer = await service.get_active_timer(uid)
        if not timer:
            await interaction.response.send_message(
                f"ℹ️ {t('time_timer_none', lang)}",
                ephemeral=True,
            )
            return

        embed = build_timer_embed(interaction.user.display_name, timer)
        view = ActiveTimerControlsView(uid, timer)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ─────────────────────────────────────────────────────────────────────────
    # /time timesheet
    # ─────────────────────────────────────────────────────────────────────────

    @time_group.command(
        name="timesheet",
        description="📊 ดูรายงานสรุปเวลาทำงานและส่งออก Timesheet / View & export timesheet",
    )
    @app_commands.describe(
        member="Team member to view timesheet for (defaults to yourself)",
        period="Time period to summarize",
    )
    @app_commands.choices(period=[
        app_commands.Choice(name="📅 Today (วันนี้)", value="today"),
        app_commands.Choice(name="📆 Past 7 Days (7 วันล่าสุด)", value="week"),
        app_commands.Choice(name="🗓️ Past 30 Days (30 วันล่าสุด)", value="month"),
        app_commands.Choice(name="♾️ All Time (ทั้งหมด)", value="all"),
    ])
    async def time_timesheet(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
        period: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        target_user = member or interaction.user
        uid = str(target_user.id)
        caller_uid = str(interaction.user.id)
        lang = await get_user_lang(caller_uid)
        await ensure_user(uid, lang)

        period_key = period.value if period else "week"
        timesheet = await service.get_user_timesheet(uid, period=period_key)
        embed = build_timesheet_embed(target_user.display_name, timesheet, lang=lang)
        view = TimesheetExportView(timesheet, target_user.display_name, lang=lang)
        await interaction.response.send_message(embed=embed, view=view)

    # ─────────────────────────────────────────────────────────────────────────
    # /time estimation
    # ─────────────────────────────────────────────────────────────────────────

    @time_group.command(
        name="estimation",
        description="🎯 วิเคราะห์ความแม่นยำในการประเมินเวลา / Estimation Accuracy & Variance",
    )
    @app_commands.describe(
        project_id="Optional project ID to filter analytics",
        member="Optional team member to filter analytics",
    )
    async def time_estimation(
        self,
        interaction: discord.Interaction,
        project_id: Optional[int] = None,
        member: Optional[discord.Member] = None,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        target_uid = str(member.id) if member else None

        scope_title = f"Project #{project_id}" if project_id else (f"Member: {member.display_name}" if member else "All Guild Tasks")
        data = await service.calculate_estimation_accuracy(project_id=project_id, user_id=target_uid)

        embed = build_estimation_analytics_embed(data, scope_title=scope_title, lang=lang)
        await interaction.response.send_message(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # /workload (set-hours & capacity)
    # ─────────────────────────────────────────────────────────────────────────

    @workload_group.command(
        name="set-hours",
        description="⚙️ ตั้งค่าชั่วโมงความพร้อมทำงานต่อสัปดาห์ / Set your weekly capacity hours",
    )
    @app_commands.describe(hours="Available working hours per week (e.g. 35 or 40)")
    async def workload_set_hours(
        self,
        interaction: discord.Interaction,
        hours: float,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)

        saved = await service.set_user_capacity(uid, hours)
        await interaction.response.send_message(
            f"✅ {t('workload_capacity_set', lang, hours=f'{saved:.1f}')}",
            ephemeral=True,
        )

    @workload_group.command(
        name="capacity",
        description="🛡️ ตรวจสอบภาระงานของทีมและ Burnout Shield / Team capacity & Burnout Shield",
    )
    @app_commands.describe(
        project_id="Optional project ID to inspect member workload for",
        member="Optional member to inspect workload for",
    )
    async def workload_capacity(
        self,
        interaction: discord.Interaction,
        project_id: Optional[int] = None,
        member: Optional[discord.Member] = None,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        guild_id = str(interaction.guild.id)

        target_uids = [str(member.id)] if member else []
        if not target_uids and project_id:
            rows = await db.fetchall(
                "SELECT user_id FROM project_members WHERE project_id = $1",
                (project_id,),
            )
            target_uids = [str(r["user_id"]) for r in rows]
        elif not target_uids:
            # Fetch active assignees in this guild
            rows = await db.fetchall(
                """
                SELECT DISTINCT ta.user_id
                FROM task_assignments ta
                JOIN tasks t ON ta.task_id = t.task_id
                JOIN projects p ON t.project_id = p.project_id
                WHERE p.guild_id = $1 AND t.status IN ('Pending', 'In_Progress') AND t.is_deleted = FALSE
                LIMIT 15
                """,
                (guild_id,),
            )
            target_uids = [str(r["user_id"]) for r in rows]
            if uid not in target_uids:
                target_uids.insert(0, uid)

        metrics_list = []
        for u in target_uids:
            m = await service.calculate_member_workload_capacity(guild_id, u)
            metrics_list.append(m)

        scope_title = f"Project #{project_id}" if project_id else (f"Member: {member.display_name}" if member else interaction.guild.name)
        embed = build_capacity_embed(metrics_list, scope_title=scope_title, lang=lang)
        await interaction.response.send_message(embed=embed)

    @workload_group.command(
        name="assign",
        description="👥 มอบหมายงานให้สมาชิกในทีมพร้อมระบบ Burnout Shield / Assign task with Burnout Shield",
    )
    @app_commands.describe(
        task_id="Task ID to assign",
        member="Team member to assign to",
        project_id="Optional project ID (auto-detected if omitted)",
    )
    async def workload_assign(
        self,
        interaction: discord.Interaction,
        task_id: int,
        member: discord.Member,
        project_id: Optional[int] = None,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        guild = interaction.guild

        pid = project_id
        if pid is None:
            t_row = await db.fetchone(
                "SELECT project_id FROM tasks WHERE task_id = $1 AND is_deleted = FALSE",
                (task_id,),
            )
            if not t_row or not t_row["project_id"]:
                await interaction.response.send_message(f"❌ Task `#{task_id}` does not belong to a project.", ephemeral=True)
                return
            pid = int(t_row["project_id"])

        from collaboration import service as collab_service
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        task = await collab_service.assign_task(
            task_id=task_id,
            project_id=pid,
            guild_id=str(guild.id),
            assignee_id=str(member.id),
            actor_id=uid,
            is_guild_admin=is_admin,
        )

        response_text = f"✅ Assigned task **#{task_id}: {task.task[:60]}** to {member.mention}."
        if task.burnout_warning:
            bw = task.burnout_warning
            pct_val = f"{bw['workload_pct']:.0f}"
            burnout_text = t("workload_burnout_warning", lang, member=member.display_name, pct=pct_val)
            response_text += f"\n\n⚠️ **{burnout_text}**"

        await interaction.response.send_message(response_text)


async def setup(bot: commands.Bot) -> None:
    """Register TimeTrackingCog."""
    await bot.add_cog(TimeTrackingCog(bot))

