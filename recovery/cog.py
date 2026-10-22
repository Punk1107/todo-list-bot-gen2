"""
recovery/cog.py — Slash commands /trash and /restore for Safe Recovery & Recycle Bin
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.security import rate_limit_check
from locales.i18n import t
from recovery import service
from recovery.views import TrashPaginationView, build_trash_embed
from utils.helpers import get_user_lang, ensure_user

log = logging.getLogger(__name__)


class RecoveryCog(commands.Cog, name="Recovery"):
    """Recycle Bin and Soft Delete Safe Recovery commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="trash",
        description="🗑️ เปิดดูถังขยะและกู้คืนงานที่ถูกลบ / Open Recycle Bin to view and restore deleted tasks",
    )
    @rate_limit_check("command")
    async def trash_cmd(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id) if interaction.guild else None
        tasks = await service.list_trash(uid, guild_id)

        view = TrashPaginationView(tasks, uid, lang, page_size=5, guild_id=guild_id)
        embed = build_trash_embed(
            view._page_tasks(),
            view.current_page,
            view.total_pages,
            lang,
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(
        name="restore",
        description="♻️ กู้คืนงานที่ถูกลบออกจากถังขยะ / Restore a deleted task from Recycle Bin by ID",
    )
    @app_commands.describe(task_id="รหัสงานที่ต้องการกู้คืน / Task ID to restore")
    @rate_limit_check("command")
    async def restore_cmd(self, interaction: discord.Interaction, task_id: int) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)

        is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False
        guild_id = str(interaction.guild.id) if interaction.guild else None

        ok, msg_key, tid = await service.restore_task(
            task_id, uid, is_guild_admin=is_admin, guild_id=guild_id
        )
        if ok:
            await interaction.followup.send(
                f"✅ {t(msg_key, lang, task_id=tid)}", ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"❌ {t(msg_key, lang)}", ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RecoveryCog(bot))
