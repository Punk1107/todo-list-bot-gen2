"""
history_reporting/cog.py — Slash commands /history and /retrospective
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.security import rate_limit_check
from handlers.tasks_cog import task_autocomplete
from history_reporting import service as history_service
from history_reporting.views import TaskHistoryView, WeeklyRetrospectiveView
from locales.i18n import t
from utils.helpers import ensure_user, get_user_lang, progress_bar

log = logging.getLogger(__name__)


class HistoryReportingCog(commands.Cog, name="HistoryReporting"):
    """Audit Trail, Activity History, and Weekly Retrospective commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="history",
        description="📜 ดูประวัติการแก้ไขและกิจกรรมของ Task / View task audit trail & history",
    )
    @app_commands.describe(task_id="รหัสงาน / Task ID number")
    @app_commands.autocomplete(task_id=task_autocomplete)
    @rate_limit_check("command")
    async def history_cmd(self, interaction: discord.Interaction, task_id: int) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)

        is_admin = bool(
            interaction.user.guild_permissions.administrator
            if (interaction.guild and hasattr(interaction.user, "guild_permissions"))
            else False
        )

        history = await history_service.get_task_audit_history(task_id, uid, is_guild_admin=is_admin)
        if not history:
            await interaction.followup.send(
                t("history_not_found_or_denied", lang, task_id=task_id),
                ephemeral=True,
            )
            return

        view = TaskHistoryView(history=history, user_id=uid, lang=lang)
        await interaction.followup.send(embed=view.make_embed(), view=view, ephemeral=True)

    @app_commands.command(
        name="retrospective",
        description="🌅 ดูรายงานสรุปย้อนหลังประจำสัปดาห์ / View weekly retrospective self-digest",
    )
    @rate_limit_check("command")
    async def retrospective_cmd(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)

        retro_data = await history_service.get_weekly_retrospective_data(uid)

        embed = discord.Embed(
            title=f"🌅 {t('retro_title', lang, week=retro_data.week_str)}",
            description=f"> {retro_data.coaching_tip}",
            color=0x6366f1,
        )

        # Progress Bar
        pbar = progress_bar(retro_data.completed_tasks, retro_data.total_tasks)
        embed.add_field(
            name=t("retro_completion_rate", lang),
            value=f"**{retro_data.completion_rate}%** ({retro_data.completed_tasks}/{retro_data.total_tasks})\n{pbar}",
            inline=False,
        )

        # Snooze Bottleneck Analysis
        if retro_data.top_snoozed_tasks:
            snooze_lines = [
                f"• **{t_info['name']}** &mdash; {t('retro_snoozed_times', lang, count=t_info['snooze_count'])}"
                for t_info in retro_data.top_snoozed_tasks
            ]
            embed.add_field(
                name=f"⏰ {t('retro_snooze_bottlenecks', lang)} ({retro_data.snooze_count_total} total)",
                value="\n".join(snooze_lines),
                inline=False,
            )
        else:
            embed.add_field(
                name=f"⏰ {t('retro_snooze_bottlenecks', lang)}",
                value=f"*{t('retro_no_snoozes', lang)}*",
                inline=False,
            )

        # Overdue Carryovers
        if retro_data.overdue_carryover_tasks:
            carry_lines = [
                f"• [P{t_info['priority']}] **#{t_info['task_id']}** {t_info['task']} *(due {t_info['deadline']})*"
                for t_info in retro_data.overdue_carryover_tasks[:5]
            ]
            if len(retro_data.overdue_carryover_tasks) > 5:
                carry_lines.append(f"... +{len(retro_data.overdue_carryover_tasks) - 5} more")
            embed.add_field(
                name=f"⚠️ {t('retro_overdue_carryovers', lang)} ({len(retro_data.overdue_carryover_tasks)})",
                value="\n".join(carry_lines),
                inline=False,
            )

        # Category Distribution
        if retro_data.category_distribution:
            cat_lines = [
                f"`{cname}`: {cnt}"
                for cname, cnt in sorted(retro_data.category_distribution.items(), key=lambda x: -x[1])[:5]
            ]
            embed.add_field(
                name=f"🏷️ {t('retro_category_breakdown', lang)}",
                value=" &bull; ".join(cat_lines),
                inline=False,
            )

        embed.set_footer(text=t("retro_footer", lang))
        view = WeeklyRetrospectiveView(user_id=uid, lang=lang)

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HistoryReportingCog(bot))
