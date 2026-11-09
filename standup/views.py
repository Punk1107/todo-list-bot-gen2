"""
standup/views.py — Discord UI Views, Modals & Embeds for Daily Standup.
"""
from __future__ import annotations

from datetime import date
import logging
from typing import List

import discord
from discord import ui

from locales.i18n import t
from standup import service
from standup.models import DailyStandupEntry

log = logging.getLogger(__name__)


def build_standup_digest_embed(
    guild_name: str,
    standup_date: date,
    entries: List[DailyStandupEntry],
    lang: str = "th",
) -> discord.Embed:
    """Build the daily standup team digest embed."""
    embed = discord.Embed(
        title=f"📋 Daily Standup Digest: {guild_name}",
        description=f"📅 วันที่: **{standup_date.strftime('%Y-%m-%d')}** · ผู้ส่งสรุปทั้งหมด: `{len(entries)}` คน",
        color=0x5865F2,
    )

    if not entries:
        embed.description += f"\n\n*{t('standup_no_entries', lang)}*"
        return embed

    for item in entries:
        user_mention = f"<@{item.user_id}>"
        yesterday_fmt = service.format_standup_text_with_tasks(item.yesterday_text)
        today_fmt = service.format_standup_text_with_tasks(item.today_text)
        blocker_fmt = service.format_standup_text_with_tasks(item.blockers_text) if item.blockers_text else "— ไม่มี / None"

        lines = [
            f"**✅ เมื่อวานนี้ (Yesterday):**\n> {yesterday_fmt}",
            f"**🎯 วันนี้ (Today):**\n> {today_fmt}",
            f"**⚠️ อุปสรรค/ปัญหา (Blockers):**\n> {blocker_fmt}",
        ]
        embed.add_field(
            name=f"👤 สมาชิก: {user_mention}",
            value="\n".join(lines),
            inline=False,
        )

    embed.set_footer(text="Daily Standup · ตอบแบบฟอร์มได้ด้วยคำสั่ง /standup submit")
    return embed


class StandupSubmitModal(ui.Modal):
    """Interactive Modal with 3 standard Agile Standup questions."""

    def __init__(self, guild_id: str, lang: str = "th") -> None:
        super().__init__(title="📝 Daily Standup Check-in")
        self.guild_id = guild_id
        self.lang = lang

        self.yesterday_input = ui.TextInput(
            label="1. เมื่อวานทำอะไรสำเร็จไปบ้าง? (Yesterday)",
            style=discord.TextStyle.paragraph,
            placeholder="เช่น เคลียร์งาน #42, ออกแบบ UI, ตรวจสอบ Code Review...",
            max_length=500,
            required=True,
        )
        self.today_input = ui.TextInput(
            label="2. วันนี้วางแผนจะทำอะไรต่อไป? (Today)",
            style=discord.TextStyle.paragraph,
            placeholder="เช่น พัฒนาระบบ #45, ทดสอบ API, ประชุมทีม...",
            max_length=500,
            required=True,
        )
        self.blockers_input = ui.TextInput(
            label="3. มีอุปสรรคติดขัดตรงไหนไหม? (Blockers)",
            style=discord.TextStyle.paragraph,
            placeholder="ระบุปัญหาที่ต้องการให้เพื่อนร่วมทีมหรือ Lead ช่วยเหลือ (หรือเว้นว่างถ้าไม่มี)",
            max_length=400,
            required=False,
        )
        self.add_item(self.yesterday_input)
        self.add_item(self.today_input)
        self.add_item(self.blockers_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        y_text = self.yesterday_input.value.strip()
        t_text = self.today_input.value.strip()
        b_text = self.blockers_input.value.strip()

        try:
            await service.submit_standup(
                guild_id=self.guild_id,
                user_id=uid,
                yesterday=y_text,
                today=t_text,
                blockers=b_text or None,
            )
            await interaction.response.send_message(
                t("standup_submitted_success", self.lang),
                ephemeral=True,
            )
        except Exception as exc:
            log.error("StandupSubmitModal error: %s", exc)
            await interaction.response.send_message(f"❌ Error: {exc}", ephemeral=True)


class StandupButtonView(ui.View):
    """View with a single button allowing team members to launch the Standup modal."""

    def __init__(self, guild_id: str, lang: str = "th") -> None:
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.lang = lang

    @ui.button(
        label="📝 Submit Daily Standup",
        style=discord.ButtonStyle.primary,
        custom_id="btn_submit_standup",
    )
    async def btn_submit(self, interaction: discord.Interaction, button: ui.Button) -> None:
        modal = StandupSubmitModal(guild_id=self.guild_id, lang=self.lang)
        await interaction.response.send_modal(modal)

