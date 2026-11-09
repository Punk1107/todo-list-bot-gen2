"""
day_planner/cog.py — Discord Slash Command Cog for Automated Daily Time-Blocker.
"""
from __future__ import annotations

import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from day_planner.optimizer import optimize_day_schedule
from day_planner.views import DayPlanActionView, build_day_plan_embed
from utils.helpers import ensure_user, get_user_lang, get_user_timezone

log = logging.getLogger(__name__)


class DayPlannerCog(commands.Cog, name="DayPlanner"):
    """Cog for Smart Daily Time-Blocker & Ergonomic Schedule Optimizer."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="dayplan",
        description="📅 จัดตารางเวลาการทำงานประจำวันให้อัตโนมัติ (Smart Day Plan & Time-Blocker)",
    )
    @app_commands.describe(
        start_time="เวลาเริ่มงาน เช่น 09:00 (Workday start e.g. 09:00)",
        end_time="เวลาเลิกงาน เช่น 18:00 (Workday end e.g. 18:00)",
        focus_mins="ระยะเวลาโฟกัสต่อบล็อก (นาที) ค่าเริ่มต้น 45",
        break_mins="ระยะเวลาพักสายตาต่อบล็อก (นาที) ค่าเริ่มต้น 15",
    )
    async def dayplan(
        self,
        interaction: discord.Interaction,
        start_time: Optional[str] = "09:00",
        end_time: Optional[str] = "18:00",
        focus_mins: Optional[int] = 45,
        break_mins: Optional[int] = 15,
    ) -> None:
        """Calculates and visualizes an ergonomic daily schedule for today's tasks."""
        await interaction.response.defer(ephemeral=False)
        uid = str(interaction.user.id)
        await ensure_user(uid, interaction.user.name)

        lang = await get_user_lang(uid)
        tz_name = await get_user_timezone(uid)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None

        # Calculate optimal schedule
        plan = await optimize_day_schedule(
            user_id=uid,
            guild_id=guild_id,
            start_time=start_time or "09:00",
            end_time=end_time or "18:00",
            focus_mins=focus_mins or 45,
            break_mins=break_mins or 15,
            tz_name=tz_name,
        )

        embed = build_day_plan_embed(plan, lang=lang)
        view = DayPlanActionView(
            user_id=uid,
            first_task_id=plan.first_task_id,
            first_task_title=plan.first_task_title,
            lang=lang,
        )

        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DayPlannerCog(bot))

