"""Slash commands and local-time streak reminders."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.database import db
from gamification import rpg, service, vacation
from locales.i18n import t
from utils.helpers import get_user_lang, ensure_user
from visualization import render_block_sparkline, render_braille_wave, render_streak_heatmap
from visualization import service as viz_service

log = logging.getLogger(__name__)


class GamificationCog(commands.Cog, name="Gamification"):
    """Expose streaks, habit summaries, achievements, and guild leaderboards."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.streak_reminder_loop.start()

    def cog_unload(self) -> None:
        self.streak_reminder_loop.cancel()

    @app_commands.command(
        name="streak",
        description="🔥 View your task-completion streak and 365-day contribution heatmap",
    )
    @app_commands.describe(heatmap="สร้างและส่งภาพกราฟิก 365-Day Contribution Heatmap / Generate 365-day heatmap image")
    async def streak(self, interaction: discord.Interaction, heatmap: bool = False) -> None:
        user_id = str(interaction.user.id)
        lang = await get_user_lang(user_id)
        summary = await service.get_habit_summary(user_id)
        streak_days = summary.get("streak_days", 0)

        activity_7d = await viz_service.get_user_7day_activity(user_id)
        sparkline = render_block_sparkline(activity_7d) or "       "
        wave = render_braille_wave(count=6)

        if not heatmap:
            embed = discord.Embed(
                title=f"🔥 Task Completion Streak: {streak_days} Days",
                description=(
                    f"**Current Streak:** {streak_days} days {wave}\n"
                    f"**7-Day Trend:** `{sparkline}`\n\n"
                    f"💡 *ใช้ `/streak heatmap:True` เพื่อดูภาพตาราง 365-Day Heatmap ฉบับเต็ม!*"
                ),
                color=0xF1C40F,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        counts = await viz_service.get_user_365_day_completions(user_id)
        buf = render_streak_heatmap(
            completion_counts=counts,
            title="365-Day Contribution Heatmap",
            username=interaction.user.display_name,
            streak_days=streak_days,
            longest_streak=max(streak_days, summary.get("longest_streak", streak_days)),
        )
        file = discord.File(fp=buf, filename="streak_heatmap.png")
        embed = discord.Embed(
            title=f"🔥 365-Day Contribution Heatmap — {interaction.user.display_name}",
            description=f"**Current Streak:** {streak_days} days · **7-Day Trend:** `{sparkline}`",
            color=0x2ECC71,
        )
        embed.set_image(url="attachment://streak_heatmap.png")
        await interaction.followup.send(embed=embed, file=file, ephemeral=True)

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

    # ─────────────────────────────────────────────────────────────────────────
    # Feature 30: Productivity RPG & Leveling Progression (/level & /rpg)
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="level",
        description="⚔️ ดูเลเวลและฉายา Productivity RPG / View your Productivity RPG Level & Title",
    )
    @app_commands.describe(member="สมาชิกที่ต้องการดูสถิติ (Target member, default: you)")
    async def level(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        target = member or interaction.user
        uid = str(target.id)
        await ensure_user(uid, target.name)
        lang = await get_user_lang(str(interaction.user.id))

        profile = await rpg.get_user_rpg_profile(uid)
        embed = self._build_rpg_embed(profile, target.display_name, lang)
        await interaction.response.send_message(embed=embed)

    rpg_group = app_commands.Group(
        name="rpg",
        description="⚔️ Productivity RPG Leveling & Leaderboard (Gen 5.0)",
    )

    @rpg_group.command(
        name="status",
        description="📊 ดูสถานะเลเวล ฉายา และแต้ม EXP / View RPG status, level, and EXP",
    )
    @app_commands.describe(member="สมาชิกที่ต้องการดูสถิติ (Target member, default: you)")
    async def rpg_status(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        await self.level(interaction, member)

    @rpg_group.command(
        name="leaderboard",
        description="🏆 อันดับเลเวลและ EXP สูงสุดในเซิร์ฟเวอร์ / Server RPG Level & EXP Leaderboard",
    )
    async def rpg_leaderboard(self, interaction: discord.Interaction) -> None:
        lang = await get_user_lang(str(interaction.user.id))
        guild_id = str(interaction.guild_id) if interaction.guild_id else None

        leaders = await rpg.get_rpg_leaderboard(guild_id, limit=10)
        title = t("rpg_leaderboard_title", lang)
        embed = discord.Embed(title=title, color=discord.Color.gold())

        if leaders:
            lines = []
            for rank, u in enumerate(leaders, start=1):
                medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"`#{rank}`"
                lines.append(
                    f"{medal} <@{u['user_id']}> — **Lv.{u['level']}** {u['title']}\n"
                    f"   └ `{u['total_exp']:,} EXP` · 🔥 Streak: {u['streak_days']}d"
                )
            embed.description = "\n".join(lines)
        else:
            embed.description = t("leaderboard_empty", lang)

        await interaction.response.send_message(embed=embed)

    def _build_rpg_embed(self, profile: dict, name: str, lang: str) -> discord.Embed:
        title = t("rpg_status_title", lang, user=name)
        desc = (
            f"**{profile['title']}**\n"
            f"**Level {profile['level']}** · `{profile['total_exp']:,}` Total EXP\n"
            f"Progress: `{profile['current_level_exp']:,} / {profile['next_level_exp']:,} EXP` ({profile['progress_pct']}%)\n"
            f"`{profile['progress_bar']}`"
        )
        embed = discord.Embed(title=title, description=desc, color=discord.Color.gold())

        v_until = profile.get("vacation_until")
        v_str = f"🌴 Active (until {v_until})" if v_until else "💼 Normal"
        embed.add_field(
            name="🔥 Streak & Balance",
            value=(
                f"• Streak: **{profile['streak_days']}** days\n"
                f"• Freeze Tokens: **{profile['streak_freeze_tokens']} / 3** 🧊\n"
                f"• Vacation: **{v_str}**"
            ),
            inline=True,
        )

        embed.add_field(
            name="📊 Cleared Tasks",
            value=(
                f"• Total: **{profile['total_completed']}** tasks\n"
                f"• P7 (Critical): **{profile['p7_count']}**\n"
                f"• P5-P6 (High): **{profile['p5_p6_count']}**\n"
                f"• P0-P4: **{profile['p3_p4_count'] + profile['p0_p2_count']}**"
            ),
            inline=True,
        )
        return embed

    # ─────────────────────────────────────────────────────────────────────────
    # Feature 32: Vacation Mode & Streak Freeze Tokens (/vacation)
    # ─────────────────────────────────────────────────────────────────────────

    vacation_group = app_commands.Group(
        name="vacation",
        description="🌴 Vacation Mode & Streak Protection (Gen 5.0)",
    )

    @vacation_group.command(
        name="start",
        description="🌴 เปิดโหมดพักร้อนเพื่อรักษาสถิติ Streak ชั่วคราว / Start Vacation Mode to freeze streak",
    )
    @app_commands.describe(
        days="จำนวนวันที่ต้องการพักร้อน (1 - 90 วัน)",
        reason="เหตุผลการลา เช่น ไปต่างจังหวัด / พักฟื้น (Optional)",
    )
    async def vacation_start(
        self,
        interaction: discord.Interaction,
        days: int,
        reason: Optional[str] = None,
    ) -> None:
        uid = str(interaction.user.id)
        await ensure_user(uid, interaction.user.name)
        lang = await get_user_lang(uid)

        res = await vacation.start_vacation(uid, days, reason)
        msg = t(
            "vacation_started_msg",
            lang,
            days=res["days"],
            until=res["vacation_until"].strftime("%Y-%m-%d"),
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @vacation_group.command(
        name="stop",
        description="💼 ยกเลิกโหมดพักร้อนและกลับมาทำงานตามปกติ / End vacation mode early",
    )
    async def vacation_stop(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        await ensure_user(uid, interaction.user.name)
        lang = await get_user_lang(uid)

        await vacation.stop_vacation(uid)
        msg = t("vacation_stopped_msg", lang)
        await interaction.response.send_message(msg, ephemeral=True)

    @vacation_group.command(
        name="status",
        description="🧊 ตรวจสอบสถานะวันลาและ Streak Freeze Tokens / View vacation status & freeze tokens",
    )
    async def vacation_status(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        await ensure_user(uid, interaction.user.name)
        lang = await get_user_lang(uid)

        st = await vacation.get_vacation_status(uid)
        title = t("vacation_status_title", lang)
        embed = discord.Embed(title=title, color=discord.Color.teal())

        v_text = (
            f"🌴 **โหมดพักร้อนกำลังทำงาน (Active)**\n"
            f"• วันที่สิ้นสุด: `{st['vacation_until']}` (เหลืออีก {st['days_remaining']} วัน)\n"
            f"• เหตุผล: {st['reason'] or '-'}"
            if st["is_on_vacation"] else
            "💼 **สถานะปกติ (Active Working)**\n• คุณไม่ได้เปิดโหมดพักร้อนอยู่ในขณะนี้"
        )
        embed.add_field(name="🌴 Vacation Status", value=v_text, inline=False)
        embed.add_field(
            name="🧊 Streak Freeze Tokens",
            value=(
                f"• คุณมีโทเคน: **{st['freeze_tokens']} / 3** ชิ้น 🧊\n"
                f"• ระบบจะใช้โทเคนอัตโนมัติหากคุณลืมเคลียร์งาน 1 วัน\n"
                f"• สะสมเพิ่มได้ทุกๆ สถิติ Streak ต่อเนื่อง 14 วัน"
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
