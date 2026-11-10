"""
kudos/cog.py — Discord Slash Command Cog for Peer Kudos & Team Gratitude (Gen 5.0).
"""
from __future__ import annotations

import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from kudos import service
from kudos.views import build_kudos_leaderboard_embed, build_kudos_sent_embed
from locales.i18n import t
from utils.helpers import ensure_user, get_user_lang

log = logging.getLogger(__name__)


class KudosCog(commands.Cog, name="Kudos"):
    """Cog for Peer Kudos & Team Gratitude (Gen 5.0)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    kudos = app_commands.Group(
        name="kudos",
        description="💖 Peer Kudos & Team Gratitude (Gen 5.0)",
    )

    @kudos.command(
        name="send",
        description="💖 ส่งคำขอบคุณและมอบแต้ม Kudos ให้เพื่อนร่วมทีม / Send kudos and gratitude to a teammate",
    )
    @app_commands.describe(
        to="เพื่อนร่วมทีมที่ต้องการขอบคุณ (Teammate to thank)",
        reason="เหตุผลหรือคำชื่นชม เช่น ขอบคุณที่ช่วยแก้บั๊กเร่งด่วนเมื่อวาน",
        task_id="รหัสงานที่เกี่ยวข้อง (Optional task ID)",
    )
    async def kudos_send(
        self,
        interaction: discord.Interaction,
        to: discord.Member,
        reason: str,
        task_id: Optional[int] = None,
    ) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message(
                "❌ คำสั่งนี้ใช้งานได้เฉพาะในเซิร์ฟเวอร์เท่านั้น / Server only.",
                ephemeral=True,
            )
            return

        from_uid = str(interaction.user.id)
        to_uid = str(to.id)
        guild_id = str(interaction.guild_id)

        await ensure_user(from_uid, interaction.user.name)
        await ensure_user(to_uid, to.name)
        lang = await get_user_lang(from_uid)

        if from_uid == to_uid:
            err = t("kudos_self_error", lang)
            await interaction.response.send_message(err, ephemeral=True)
            return

        try:
            kudos_entry = await service.send_kudos(
                guild_id=guild_id,
                from_user_id=from_uid,
                to_user_id=to_uid,
                reason=reason,
                task_id=task_id,
            )
        except ValueError as val_err:
            await interaction.response.send_message(f"❌ {val_err}", ephemeral=True)
            return

        embed = build_kudos_sent_embed(
            kudos=kudos_entry,
            from_name=interaction.user.mention,
            to_name=to.mention,
        )
        await interaction.response.send_message(
            content=f"🎉 {to.mention} ได้รับคำขอบคุณจาก {interaction.user.mention}!",
            embed=embed,
        )

    @kudos.command(
        name="leaderboard",
        description="🏆 ตารางเกียรติยศผู้ช่วยเหลือยอดเยี่ยม / Gratitude & Kudos Leaderboard",
    )
    @app_commands.describe(period="ช่วงเวลาการจัดอันดับ (เดือนนี้ หรือ ตลอดกาล)")
    @app_commands.choices(period=[
        app_commands.Choice(name="เดือนนี้ (This Month)", value="month"),
        app_commands.Choice(name="ตลอดกาล (All Time)", value="all_time"),
    ])
    async def kudos_leaderboard(
        self,
        interaction: discord.Interaction,
        period: app_commands.Choice[str],
    ) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message(
                "❌ คำสั่งนี้ใช้งานได้เฉพาะในเซิร์ฟเวอร์เท่านั้น / Server only.",
                ephemeral=True,
            )
            return

        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        guild_id = str(interaction.guild_id)

        leaders = await service.get_kudos_leaderboard(guild_id, period=period.value, limit=10)
        embed = build_kudos_leaderboard_embed(leaders, period=period.value, lang=lang)
        await interaction.response.send_message(embed=embed)

    @kudos.command(
        name="history",
        description="📜 ดูคำขอบคุณที่ได้รับล่าสุด / View recent kudos received",
    )
    @app_commands.describe(member="สมาชิกที่ต้องการดู (Target member, default: you)")
    async def kudos_history(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        target = member or interaction.user
        uid = str(target.id)
        await ensure_user(uid, target.name)

        recent = await service.get_user_recent_kudos(uid, days=30, limit=10)
        if not recent:
            await interaction.response.send_message(
                f"📭 ยังไม่มีประวัติคำขอบคุณสำหรับ {target.mention} ในช่วง 30 วันที่ผ่านมา",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"💖 ประวัติคำขอบคุณของ {target.display_name}",
            color=discord.Color.from_rgb(255, 105, 180),
        )
        for k in recent:
            date_str = k["created_at"].strftime("%Y-%m-%d")
            task_info = f" (งาน #{k['task_id']})" if k.get("task_id") else ""
            embed.add_field(
                name=f"จาก <@{k['from_user_id']}> ({date_str}){task_info}",
                value=f"• *\"{k['reason']}\"* (`+{k['points']} EXP`)",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(KudosCog(bot))

