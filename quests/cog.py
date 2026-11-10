"""
quests/cog.py — Discord Slash Command Cog for Server Co-op Quests and Guild Raids.
"""
from __future__ import annotations

import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from locales.i18n import t
from quests import service
from quests.views import build_quest_embed
from utils.helpers import ensure_user, get_user_lang

log = logging.getLogger(__name__)


class QuestsCog(commands.Cog, name="Quests"):
    """Cog for Server Co-op Quests and Guild Raids (Gen 5.0)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    quest = app_commands.Group(
        name="quest",
        description="⚔️ Server Co-op Quests & Guild Raids (Gen 5.0)",
    )

    @quest.command(
        name="view",
        description="⚔️ ดูความคืบหน้าของภารกิจ Co-op ประจำเซิร์ฟเวอร์ / View current server quest",
    )
    async def quest_view(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message(
                "❌ คำสั่งนี้ใช้งานได้เฉพาะในเซิร์ฟเวอร์เท่านั้น / Server only.",
                ephemeral=True,
            )
            return

        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        guild_id = str(interaction.guild_id)

        active = await service.get_active_quest(guild_id)
        if not active:
            msg = t("quest_no_active", lang)
            await interaction.response.send_message(msg, ephemeral=True)
            return

        participants = await service.get_quest_participants(active.quest_id, limit=10)
        embed = build_quest_embed(active, participants, lang=lang)
        await interaction.response.send_message(embed=embed)

    @quest.command(
        name="create",
        description="👑 สร้างภารกิจ Co-op Raid Quest ใหม่สำหรับกิลด์ / Create a new guild quest",
    )
    @app_commands.describe(
        title="ชื่อภารกิจ เช่น เคลียร์งานสปรินต์ร่วมกัน 150 งาน",
        target_tasks="จำนวนงานเป้าหมายทั้งหมด เช่น 150",
        days="ระยะเวลาเควส (วัน) เช่น 7",
        min_tasks="เกณฑ์ขั้นต่ำต่อคนเพื่อรับรางวัล เช่น 3",
        exp_reward="โบนัส EXP เมื่อทำสำเร็จ เช่น 500",
        badge_reward="ชื่อเหรียญตราพิเศษ เช่น Guild Raid Hero",
        description="คำอธิบายรายละเอียดภารกิจ (Optional)",
    )
    async def quest_create(
        self,
        interaction: discord.Interaction,
        title: str,
        target_tasks: int,
        days: Optional[int] = 7,
        min_tasks: Optional[int] = 3,
        exp_reward: Optional[int] = 500,
        badge_reward: Optional[str] = "Guild Raid Hero",
        description: Optional[str] = None,
    ) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message(
                "❌ คำสั่งนี้ใช้งานได้เฉพาะในเซิร์ฟเวอร์เท่านั้น / Server only.",
                ephemeral=True,
            )
            return

        # Check permissions: Admin or Manage Guild
        perms = interaction.permissions if interaction.permissions else None
        is_admin = perms and (perms.administrator or perms.manage_guild)
        if not is_admin:
            await interaction.response.send_message(
                "❌ คุณต้องมีสิทธิ์ Administrator หรือ Manage Server เพื่อสร้างภารกิจ Co-op Quest",
                ephemeral=True,
            )
            return

        uid = str(interaction.user.id)
        await ensure_user(uid, interaction.user.name)
        lang = await get_user_lang(uid)
        guild_id = str(interaction.guild_id)

        new_quest = await service.create_quest(
            guild_id=guild_id,
            creator_id=uid,
            title=title,
            target_tasks=target_tasks,
            days=days or 7,
            min_tasks_per_member=min_tasks or 3,
            exp_reward=exp_reward or 500,
            badge_reward=badge_reward or "Guild Raid Hero",
            description=description,
        )

        embed = build_quest_embed(new_quest, [], lang=lang)
        created_msg = t("quest_created_msg", lang, title=new_quest.title)
        await interaction.response.send_message(content=created_msg, embed=embed)

    @quest.command(
        name="list",
        description="📜 ดูประวัติภารกิจ Co-op Quest ทั้งหมดของเซิร์ฟเวอร์ / List guild quests",
    )
    async def quest_list(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message(
                "❌ คำสั่งนี้ใช้งานได้เฉพาะในเซิร์ฟเวอร์เท่านั้น / Server only.",
                ephemeral=True,
            )
            return

        guild_id = str(interaction.guild_id)
        quests = await service.list_guild_quests(guild_id, limit=5)

        if not quests:
            await interaction.response.send_message("📭 ยังไม่มีประวัติเควสในเซิร์ฟเวอร์นี้", ephemeral=True)
            return

        embed = discord.Embed(
            title="📜 ประวัติภารกิจ Server Co-op Quests",
            color=discord.Color.purple(),
        )
        for q in quests:
            status_icon = "✅ สำเร็จแล้ว" if q.is_completed else ("⏳ กำลังดำเนินอยู่" if q.status == "active" else "❌ หมดเวลา")
            embed.add_field(
                name=f"#{q.quest_id} {q.title}",
                value=(
                    f"• สถานะ: **{status_icon}**\n"
                    f"• ความคืบหน้า: `{q.completed_tasks:,}/{q.target_tasks:,}` ({q.progress_pct}%)\n"
                    f"• รางวัล: `+{q.exp_reward:,} EXP` · 🏅 {q.badge_reward}"
                ),
                inline=False,
            )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(QuestsCog(bot))

