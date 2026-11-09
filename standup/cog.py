"""
standup/cog.py — Discord Slash Commands for Asynchronous Daily Standup.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.security import rate_limit_check
from locales.i18n import t
from standup import service
from standup.views import StandupButtonView, StandupSubmitModal, build_standup_digest_embed
from utils.helpers import ensure_user, get_user_lang

log = logging.getLogger(__name__)


def _is_admin(interaction: discord.Interaction) -> bool:
    """Check if interaction caller is a guild admin."""
    if isinstance(interaction.user, discord.Member):
        return interaction.user.guild_permissions.administrator
    return False


class StandupCog(commands.Cog, name="Daily Standup"):
    """Asynchronous Daily Standup Cog for Discord teams."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._sent_dates: dict[str, date] = {}  # guild_id -> date prompt sent
        self.standup_schedule_loop.start()

    def cog_unload(self) -> None:
        self.standup_schedule_loop.cancel()

    standup = app_commands.Group(
        name="standup",
        description="📋 Asynchronous Daily Standup check-in & digest",
    )

    @standup.command(name="submit", description="ตอบแบบฟอร์มสรุปงาน Daily Standup ประจำวัน")
    @rate_limit_check("command")
    async def standup_submit(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)

        if not interaction.guild:
            await interaction.response.send_message(t("proj_guild_only", lang), ephemeral=True)
            return

        modal = StandupSubmitModal(guild_id=str(interaction.guild.id), lang=lang)
        await interaction.response.send_modal(modal)

    @standup.command(name="config", description="ตั้งค่าห้องทีมและเวลาแจ้งเตือน Daily Standup ประจำวัน")
    @app_commands.describe(
        channel="ห้อง Text Channel ที่ต้องการให้บอทส่งสรุปและแจ้งเตือน",
        time="เวลาที่ต้องการแจ้งเตือนในรูปแบบ HH:MM (เช่น 09:30)",
    )
    @rate_limit_check("command")
    async def standup_config(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        time: Optional[str] = "09:30",
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)

        if not interaction.guild:
            await interaction.response.send_message(t("proj_guild_only", lang), ephemeral=True)
            return

        if not _is_admin(interaction):
            await interaction.response.send_message(t("proj_no_permission", lang), ephemeral=True)
            return

        clean_time = time.strip() if time else "09:30"
        parts = clean_time.split(":")
        if len(parts) != 2 or not (parts[0].isdigit() and parts[1].isdigit()):
            await interaction.response.send_message(
                "❌ รูปแบบเวลาไม่ถูกต้อง กรุณาใช้รูปแบบ `HH:MM` เช่น `09:30` หรือ `10:00`",
                ephemeral=True,
            )
            return

        hh, mm = int(parts[0]), int(parts[1])
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            await interaction.response.send_message(
                "❌ เวลาต้องอยู่ระหว่าง `00:00` ถึง `23:59`",
                ephemeral=True,
            )
            return

        formatted_time = f"{hh:02d}:{mm:02d}"
        await service.save_standup_config(
            guild_id=str(interaction.guild.id),
            channel_id=str(channel.id),
            standup_time=formatted_time,
            user_id=uid,
        )

        await interaction.response.send_message(
            t("standup_config_saved", lang, channel=channel.mention, time=formatted_time),
            ephemeral=False,
        )

    @standup.command(name="digest", description="รวบรวมสรุป Daily Standup ของสมาชิกในทีมวันนี้ส่งลงห้อง")
    @rate_limit_check("command")
    async def standup_digest(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)

        if not interaction.guild:
            await interaction.response.send_message(t("proj_guild_only", lang), ephemeral=True)
            return

        await interaction.response.defer()
        guild_id = str(interaction.guild.id)
        entries = await service.get_daily_standups(guild_id, date.today())
        embed = build_standup_digest_embed(
            guild_name=interaction.guild.name,
            standup_date=date.today(),
            entries=entries,
            lang=lang,
        )
        await interaction.followup.send(embed=embed)

    @tasks.loop(minutes=1)
    async def standup_schedule_loop(self) -> None:
        """Periodic background loop that dispatches standup check-in prompt at configured time."""
        now = datetime.now(timezone.utc)
        current_hm = now.strftime("%H:%M")
        today_date = now.date()

        configs = await service.get_all_active_standup_configs()
        for cfg in configs:
            gid = cfg.guild_id
            if cfg.standup_time == current_hm and self._sent_dates.get(gid) != today_date:
                channel = self.bot.get_channel(int(cfg.channel_id))
                if isinstance(channel, discord.TextChannel):
                    self._sent_dates[gid] = today_date
                    embed = discord.Embed(
                        title="☀️ Daily Standup Time!",
                        description="ได้เวลาอัปเดตงานประจำวันของทีมแล้ว! กรุณากดปุ่มด้านล่างเพื่อตอบแบบฟอร์ม 3 ข้อ:",
                        color=0x5865F2,
                    )
                    view = StandupButtonView(guild_id=gid)
                    try:
                        await channel.send(embed=embed, view=view)
                    except Exception as exc:
                        log.warning("Could not dispatch standup prompt to channel %s: %s", channel.id, exc)

    @standup_schedule_loop.before_loop
    async def before_standup_schedule_loop(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    """Setup hook to register StandupCog."""
    await bot.add_cog(StandupCog(bot))

