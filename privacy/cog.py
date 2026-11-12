"""Discord Cog for GDPR Right to be Forgotten (/privacy)."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.security import rate_limit_check
from privacy import service
from privacy.views import PrivacyDeleteView
from utils.helpers import get_user_lang


class PrivacyCog(commands.Cog, name="Privacy"):
    """Self-service GDPR compliance commands (/privacy delete-my-data)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    privacy_group = app_commands.Group(
        name="privacy",
        description="🛡️ ความเป็นส่วนตัวและการลบข้อมูล GDPR / Privacy & GDPR data rights",
    )

    @privacy_group.command(
        name="delete-my-data",
        description="🗑️ ลบข้อมูลส่วนตัวถาวรและแปลงประวัติส่วนรวมเป็น [Deleted User] (GDPR)",
    )
    @rate_limit_check("command")
    async def privacy_delete_my_data(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await interaction.response.defer(ephemeral=True)

        impact = await service.get_gdpr_impact(uid)
        view = PrivacyDeleteView(user_id=uid, lang=lang, impact=impact)
        await interaction.followup.send(embed=view.make_embed(), view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PrivacyCog(bot))
