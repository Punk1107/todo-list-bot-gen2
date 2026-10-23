"""Slash commands and local-time streak reminders."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.database import db
from gamification import service
from locales.i18n import t
from utils.helpers import get_user_lang

log = logging.getLogger(__name__)


class GamificationCog(commands.Cog, name="Gamification"):
    """Expose streaks, habit summaries, achievements, and guild leaderboards."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.streak_reminder_loop.start()

    def cog_unload(self) -> None:
        self.streak_reminder_loop.cancel()

    @app_commands.command(name="streak", description="🔥 View your current task-completion streak")
    async def streak(self, interaction: discord.Interaction) -> None:
        user_id = str(interaction.user.id)
        lang = await get_user_lang(user_id)
        summary = await service.get_habit_summary(user_id)
        await interaction.response.send_message(
            t("habit_streak_value", lang, streak_days=summary["streak_days"]),
            ephemeral=True,
        )

    @app_commands.command(name="habits", description="📊 View your task habits and achievements")
    async def habits(self, interaction: discord.Interaction) -> None:
        user_id = str(interaction.user.id)
        lang = await get_user_lang(user_id)
        summary = await service.get_habit_summary(user_id)
        embed = discord.Embed(
            title=t("habit_summary_title", lang),
            color=0xF1C40F,
        )
        embed.add_field(
            name=t("habit_streak_heading", lang),
            value=t("habit_streak_value", lang, streak_days=summary["streak_days"]),
            inline=True,
        )
        embed.add_field(
            name=t("habit_today_heading", lang),
            value=t("habit_today_value", lang, count=summary["today_completions"]),
            inline=True,
        )
        badges = summary["badges"]
        badge_text = "\n".join(
            f"• {t(service.BADGE_KEYS.get(badge['type'], badge['type']), lang)}"
            for badge in badges
        ) or t("habit_no_badges", lang)
        embed.add_field(name=t("habit_badges_heading", lang), value=badge_text[:1024], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="leaderboard", description="🏆 View this server's shared-task leaderboard")
    @app_commands.guild_only()
    @app_commands.choices(period=[
        app_commands.Choice(name="Week (last 7 days)", value="week"),
        app_commands.Choice(name="Month (last 30 days)", value="month"),
    ])
    async def leaderboard(
        self, interaction: discord.Interaction, period: app_commands.Choice[str]
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                t("permission_denied", await get_user_lang(interaction.user.id)),
                ephemeral=True,
            )
            return
        lang = await get_user_lang(interaction.user.id)
        rows = await service.get_guild_leaderboard(str(interaction.guild.id), period.value)
        title_key = "leaderboard_week_title" if period.value == "week" else "leaderboard_month_title"
        embed = discord.Embed(title=t(title_key, lang), color=0xF1C40F)
        if rows:
            lines = [
                t(
                    "leaderboard_entry",
                    lang,
                    rank=index,
                    user=f"<@{row['user_id']}>",
                    completed=row["completed"],
                    score=row["score"],
                )
                for index, row in enumerate(rows[:10], start=1)
            ]
            embed.description = "\n".join(lines)
            embed.set_footer(text=t("leaderboard_score_note", lang))
        else:
            embed.description = t("leaderboard_empty", lang)
        await interaction.response.send_message(embed=embed)

    @tasks.loop(minutes=1)
    async def streak_reminder_loop(self) -> None:
        try:
            rows = await db.afetchall(
                """SELECT user_id, timezone, streak_days, streak_last_completion
                   FROM users
                   WHERE notify_enabled=1 AND streak_days > 0
                     AND streak_last_completion IS NOT NULL"""
            )
            now = datetime.now(timezone.utc)
            for row in rows or []:
                try:
                    user_tz = ZoneInfo(row["timezone"] or "UTC")
                except ZoneInfoNotFoundError:
                    log.warning(
                        "Unknown timezone %r for streak reminder user %s; using UTC",
                        row["timezone"], row["user_id"],
                    )
                    user_tz = timezone.utc
                local_now = now.astimezone(user_tz)
                if local_now.hour != 20:
                    continue
                local_day = local_now.date()
                if row["streak_last_completion"] != local_day - timedelta(days=1):
                    continue
                if not await service.claim_streak_reminder(row["user_id"], local_day):
                    continue
                try:
                    user = self.bot.get_user(int(row["user_id"]))
                    if user is None:
                        user = await self.bot.fetch_user(int(row["user_id"]))
                    lang = await get_user_lang(row["user_id"])
                    await user.send(
                        t("streak_reminder", lang, streak_days=int(row["streak_days"]))
                    )
                except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
                    log.warning("Could not send streak reminder to %s: %s", row["user_id"], exc)
        except Exception as loop_exc:
            log.error("Unexpected error in streak_reminder_loop: %s", loop_exc, exc_info=True)

    @streak_reminder_loop.before_loop
    async def before_streak_reminder_loop(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GamificationCog(bot))
