"""
storage/cog.py — Slash Commands for Task File Attachments

Slash commands:
  /attach [task_id] [file]        — Upload a file attachment to a task
  /attachments [task_id]          — View and manage attachments for a task
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.security import rate_limit_check
from locales.i18n import t
from utils.helpers import get_user_lang, ensure_user
from storage import service as storage_service
from storage.service import (
    StorageDisabledError,
    FileTooLargeError,
    InvalidFileTypeError,
)
from storage.views import build_attachments_embed, TaskAttachmentsView
from core.config import config

log = logging.getLogger(__name__)


class StorageCog(commands.Cog, name="Storage"):
    """Task file attachment slash commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ─────────────────────────────────────────────────────────────────────────
    # /attach
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="attach",
        description="📎 อัปโหลดไฟล์แนบสำหรับ Task / Upload a file attachment to a task",
    )
    @app_commands.describe(
        task_id="Task ID to attach the file to",
        file="File to upload (max {max_mb} MB)".format(max_mb=config.storage.max_file_size_mb),
    )
    @rate_limit_check("command")
    async def attach(
        self,
        interaction: discord.Interaction,
        task_id: int,
        file: discord.Attachment,
    ) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer()

        # Verify task exists and user has access to it
        from core.database import db
        task_row = await db.fetchone(
            "SELECT task_id, task, project_id, guild_id, owner_id FROM tasks WHERE task_id=$1",
            (task_id,),
        )
        if not task_row:
            await interaction.followup.send(
                t("task_not_found", lang, task_id=task_id), ephemeral=True
            )
            return

        # For shared tasks: check project membership
        project_id = task_row.get("project_id")
        if project_id and interaction.guild:
            guild_id = str(interaction.guild.id)
            if str(task_row.get("guild_id", "")) != guild_id:
                await interaction.followup.send(t("permission_denied", lang), ephemeral=True)
                return
            # Any guild member may attach files (membership not strictly required)

        try:
            attachment = await storage_service.upload_attachment(
                task_id=task_id,
                discord_attachment=file,
                uploader_id=uid,
                project_id=int(project_id) if project_id else None,
            )
        except StorageDisabledError:
            await interaction.followup.send(t("storage_disabled", lang), ephemeral=True)
            return
        except FileTooLargeError as exc:
            await interaction.followup.send(
                t("storage_file_too_large", lang, max_mb=exc.max_mb), ephemeral=True
            )
            return
        except InvalidFileTypeError as exc:
            allowed_str = ", ".join(f"`.{e}`" for e in exc.allowed[:10])
            await interaction.followup.send(
                t("storage_invalid_extension", lang, allowed=allowed_str), ephemeral=True
            )
            return
        except Exception as exc:
            log.error("attach command error: %s", exc, exc_info=True)
            await interaction.followup.send(t("err_db", lang), ephemeral=True)
            return

        # Success embed
        embed = discord.Embed(
            title=t("storage_upload_success_title", lang),
            description=t(
                "storage_upload_success", lang,
                filename=attachment.file_name,
                filesize=attachment.size_human,
                task_id=task_id,
            ),
            color=0x57F287,
        )
        embed.set_footer(text="To-Do List Bot Gen 2")
        if attachment.is_image:
            embed.set_image(url=attachment.public_url)
        else:
            embed.add_field(
                name="🔗 Link",
                value=f"[{attachment.display_name}]({attachment.public_url})",
                inline=False,
            )

        await interaction.followup.send(embed=embed)

        # Notify project channel if this is a shared project task
        if project_id and interaction.guild:
            await self._notify_project_attachment(
                attachment=attachment,
                task_name=task_row["task"],
                project_id=int(project_id),
                guild_id=str(interaction.guild.id),
                lang=lang,
            )

    # ─────────────────────────────────────────────────────────────────────────
    # /attachments
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="attachments",
        description="📂 ดูและจัดการไฟล์แนบของ Task / View and manage task attachments",
    )
    @app_commands.describe(task_id="Task ID to view attachments for")
    @rate_limit_check("command")
    async def attachments_list(
        self,
        interaction: discord.Interaction,
        task_id: int,
    ) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await interaction.response.defer()

        # Verify task exists
        from core.database import db
        task_row = await db.fetchone(
            "SELECT task_id, task FROM tasks WHERE task_id=$1",
            (task_id,),
        )
        if not task_row:
            await interaction.followup.send(
                t("task_not_found", lang, task_id=task_id), ephemeral=True
            )
            return

        if not config.storage.enabled:
            await interaction.followup.send(t("storage_disabled", lang), ephemeral=True)
            return

        task_name = task_row["task"]
        files     = await storage_service.get_attachments(task_id)
        embed     = build_attachments_embed(task_id, task_name, files, lang)
        view      = TaskAttachmentsView(task_id, task_name, files, uid, lang)
        await interaction.followup.send(embed=embed, view=view)

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _notify_project_attachment(
        self,
        *,
        attachment,
        task_name: str,
        project_id: int,
        guild_id: str,
        lang: str,
    ) -> None:
        """Post an attachment-uploaded notification to the project's Discord channel."""
        from core.database import db
        row = await db.fetchone(
            "SELECT notification_channel_id, channel_id FROM projects WHERE project_id=$1 AND guild_id=$2",
            (project_id, guild_id),
        )
        if not row:
            return
        channel_id = row.get("notification_channel_id") or row.get("channel_id")
        if not channel_id:
            return

        from realtime.notifications import build_attachment_uploaded_embed
        embed = build_attachment_uploaded_embed(
            task_id=attachment.task_id,
            task_name=task_name,
            file_name=attachment.file_name,
            file_size_human=attachment.size_human,
            public_url=attachment.public_url,
            uploader_id=attachment.uploader_id,
            is_image=attachment.is_image,
            lang=lang,
        )
        try:
            channel = self.bot.get_channel(int(channel_id))
            if channel is None:
                channel = await self.bot.fetch_channel(int(channel_id))
            await channel.send(embed=embed)  # type: ignore[union-attr]
        except Exception as exc:
            log.warning("Could not notify project channel %s: %s", channel_id, exc)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StorageCog(bot))
