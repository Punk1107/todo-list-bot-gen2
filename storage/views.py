"""
storage/views.py — Discord UI Components for Task File Attachments

Components:
  - build_attachments_embed : Embed listing all attachments for a task
  - TaskAttachmentsView     : Interactive view with delete buttons per attachment
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import ui

from storage.models import TaskAttachment
from locales.i18n import t

log = logging.getLogger(__name__)

_MAX_FILES_SHOWN = 10   # Discord embed field limit


def build_attachments_embed(
    task_id: int,
    task_name: str,
    attachments: list[TaskAttachment],
    lang: str = "en",
) -> discord.Embed:
    """Build a rich embed listing all attachments for a task."""
    embed = discord.Embed(
        title=t("storage_attachments_title", lang, task_id=task_id),
        description=f"**#{task_id}** — {task_name[:70]}",
        color=0x5865F2,
    )

    if not attachments:
        embed.add_field(
            name="\u200b",
            value=f"> *{t('storage_no_attachments', lang)}*",
            inline=False,
        )
        embed.set_footer(text="To-Do List Bot Gen 2")
        return embed

    for att in attachments[:_MAX_FILES_SHOWN]:
        value_lines = [
            f"📦 {att.size_human}  |  🗓️ <t:{int(att.created_at.timestamp())}:d>",
            f"👤 <@{att.uploader_id}>",
        ]
        if att.is_image:
            value_lines.append(f"[🔗 View]({att.public_url})")
        else:
            value_lines.append(f"[⬇️ Download]({att.public_url})")

        embed.add_field(
            name=f"{att.icon_emoji} `{att.display_name}`",
            value="\n".join(value_lines),
            inline=True,
        )

    if len(attachments) > _MAX_FILES_SHOWN:
        embed.set_footer(
            text=t("storage_more_files", lang, count=len(attachments) - _MAX_FILES_SHOWN)
        )
    else:
        embed.set_footer(
            text=t("storage_file_count", lang, count=len(attachments))
        )

    # Show first image as thumbnail if any
    image_att = next((a for a in attachments if a.is_image), None)
    if image_att:
        embed.set_thumbnail(url=image_att.public_url)

    return embed


class AttachmentDeleteButton(ui.Button):
    """
    A single 🗑️ Delete button for one attachment.
    Only the uploader or a guild admin can use it.
    """

    def __init__(
        self,
        attachment: TaskAttachment,
        task_id: int,
        uid: str,
        lang: str,
        row_index: int,
    ) -> None:
        super().__init__(
            label=f"🗑️ {attachment.display_name[:40]}",
            style=discord.ButtonStyle.danger,
            custom_id=f"del_att_{attachment.attachment_id}",
            row=row_index,
        )
        self.attachment = attachment
        self.task_id    = task_id
        self.uid        = uid
        self.lang       = lang

    async def callback(self, interaction: discord.Interaction) -> None:
        lang     = self.lang
        actor_id = str(interaction.user.id)
        is_admin = (
            isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.administrator
        )

        await interaction.response.defer(ephemeral=True)

        from storage.service import delete_attachment, get_attachments
        from storage.service import AttachmentPermissionError, AttachmentNotFoundError

        try:
            await delete_attachment(
                self.attachment.attachment_id,
                actor_id,
                is_guild_admin=is_admin,
            )
        except AttachmentPermissionError:
            await interaction.followup.send(
                t("storage_delete_no_permission", lang), ephemeral=True
            )
            return
        except AttachmentNotFoundError:
            await interaction.followup.send(
                t("storage_not_found", lang), ephemeral=True
            )
            return
        except Exception as exc:
            log.error("Attachment delete failed: %s", exc, exc_info=True)
            await interaction.followup.send(t("err_db", lang), ephemeral=True)
            return

        # Refresh the attachments view
        remaining = await get_attachments(self.task_id)
        task_row  = await _fetch_task_name(self.task_id)
        task_name = task_row.get("task", f"Task #{self.task_id}") if task_row else f"Task #{self.task_id}"
        embed     = build_attachments_embed(self.task_id, task_name, remaining, lang)
        view      = TaskAttachmentsView(self.task_id, task_name, remaining, actor_id, lang)

        await interaction.followup.send(t("storage_deleted_success", lang), ephemeral=True)
        try:
            await interaction.message.edit(embed=embed, view=view)  # type: ignore[union-attr]
        except Exception:
            pass


async def _fetch_task_name(task_id: int) -> Optional[dict]:
    from core.database import db
    return await db.fetchone("SELECT task FROM tasks WHERE task_id=$1", (task_id,))


class AttachmentDeleteSelect(ui.Select):
    """Dropdown to delete an attachment (supports up to 25 files)."""

    def __init__(
        self,
        attachments: list[TaskAttachment],
        task_id: int,
        uid: str,
        lang: str,
        row: int = 0,
    ) -> None:
        self.task_id = task_id
        self.uid = uid
        self.lang = lang

        options = [
            discord.SelectOption(
                label=f"{a.icon_emoji} {a.display_name[:40]}",
                value=str(a.attachment_id),
                description=f"{a.size_human} · {a.created_at.strftime('%d/%m/%Y')}",
            )
            for a in attachments[:25]
        ]
        if not options:
            options = [discord.SelectOption(label=t("quickaction_none", lang), value="0")]

        super().__init__(
            placeholder=t("storage_delete_select_placeholder", lang),
            options=options,
            min_values=1, max_values=1,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        val = self.values[0]
        if val == "0":
            return
        att_id = int(val)
        actor_id = str(interaction.user.id)
        is_admin = (
            isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.administrator
        )
        await interaction.response.defer(ephemeral=True)

        from storage.service import delete_attachment, get_attachments
        from storage.service import AttachmentPermissionError, AttachmentNotFoundError

        try:
            await delete_attachment(att_id, actor_id, is_guild_admin=is_admin)
        except AttachmentPermissionError:
            await interaction.followup.send(
                t("storage_delete_no_permission", self.lang), ephemeral=True
            )
            return
        except AttachmentNotFoundError:
            await interaction.followup.send(
                t("storage_not_found", self.lang), ephemeral=True
            )
            return
        except Exception as exc:
            log.error("Attachment delete failed: %s", exc, exc_info=True)
            await interaction.followup.send(t("err_db", self.lang), ephemeral=True)
            return

        remaining = await get_attachments(self.task_id)
        task_row  = await _fetch_task_name(self.task_id)
        task_name = task_row.get("task", f"Task #{self.task_id}") if task_row else f"Task #{self.task_id}"
        embed     = build_attachments_embed(self.task_id, task_name, remaining, self.lang)
        view      = TaskAttachmentsView(self.task_id, task_name, remaining, actor_id, self.lang)

        await interaction.followup.send(t("storage_deleted_success", self.lang), ephemeral=True)
        try:
            await interaction.message.edit(embed=embed, view=view)
        except Exception:
            pass


class TaskAttachmentsView(ui.View):
    """
    Interactive view for managing task attachments.
    Uses AttachmentDeleteSelect dropdown for up to 25 files + Close button.
    """

    def __init__(
        self,
        task_id: int,
        task_name: str,
        attachments: list[TaskAttachment],
        uid: str,
        lang: str,
    ) -> None:
        super().__init__(timeout=180)
        self.task_id    = task_id
        self.task_name  = task_name
        self.lang       = lang
        self.uid        = uid

        if attachments:
            self.add_item(AttachmentDeleteSelect(attachments, task_id, uid, lang, row=0))

    @ui.button(label="✖ Close", style=discord.ButtonStyle.secondary, custom_id="att_close", row=1)
    async def close_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.stop()
        try:
            await interaction.response.edit_message(
                content=t("cancel", self.lang), embed=None, view=None,
            )
        except Exception:
            await interaction.response.defer()
