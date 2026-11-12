"""
changelog/views.py — Interactive Release Notes Preview, #releases Publisher & CHANGELOG.md Downloader.
"""
from __future__ import annotations

import io
import logging
from typing import Optional

import discord
from discord import ui

from changelog import service as cl_service
from changelog.models import GeneratedChangelog
from locales.i18n import t
from utils.helpers import get_user_lang

log = logging.getLogger(__name__)


class ChangelogPreviewView(ui.View):
    """Interactive Release Notes preview with Publish to #releases and CHANGELOG.md download."""

    def __init__(
        self,
        changelog: GeneratedChangelog,
        user_id: str,
        lang: str = "th",
        can_publish: bool = True,
    ) -> None:
        super().__init__(timeout=300)
        self.changelog = changelog
        self.user_id = user_id
        self.lang = lang
        self.can_publish = can_publish
        self.publish_btn.disabled = (not can_publish or changelog.total_tasks == 0)

    def make_embed(self) -> discord.Embed:
        return cl_service.render_release_embed(self.changelog, lang=self.lang)

    @ui.button(label="📢 Publish to #releases", style=discord.ButtonStyle.success, row=0)
    async def publish_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not interaction.guild:
            await interaction.response.send_message(t("proj_guild_only", lang), ephemeral=True)
            return

        is_admin = bool(
            hasattr(interaction.user, "guild_permissions")
            and interaction.user.guild_permissions.administrator
        )
        from collaboration import service as collab_service
        try:
            proj = await collab_service.get_project(self.changelog.project_id, self.changelog.guild_id)
            await collab_service.require_role(proj, uid, "member", is_guild_admin=is_admin)
        except collab_service.ProjectPermissionError:
            await interaction.response.send_message(t("proj_no_permission", lang), ephemeral=True)
            return

        target_ch = await cl_service.resolve_releases_channel(interaction.guild, self.changelog.project_id)
        if not target_ch:
            await interaction.response.send_message(t("changelog_no_channel", lang), ephemeral=True)
            return

        me = interaction.guild.me
        if me:
            perms = target_ch.permissions_for(me)
            if not perms.send_messages or not perms.embed_links:
                await interaction.response.send_message(
                    t("changelog_channel_no_perm", lang, channel=target_ch.mention),
                    ephemeral=True,
                )
                return

        await interaction.response.defer(ephemeral=True)
        embed = self.make_embed()
        md_bytes = cl_service.render_markdown_changelog(self.changelog)
        file_obj = discord.File(io.BytesIO(md_bytes), filename="CHANGELOG.md")
        try:
            await target_ch.send(embed=embed, file=file_obj)
        except Exception as exc:
            log.error("Failed publishing changelog to #%s: %s", target_ch.id, exc, exc_info=True)
            await interaction.followup.send(t("err_generic", lang), ephemeral=True)
            return

        await collab_service.log_activity(
            self.changelog.project_id,
            self.changelog.guild_id,
            uid,
            "changelog_published",
            f"{self.changelog.version_label} -> #{target_ch.name}",
        )
        button.disabled = True
        try:
            await interaction.edit_original_response(view=self)
        except Exception:
            pass
        await interaction.followup.send(
            t("changelog_published_msg", lang, channel=target_ch.mention),
            ephemeral=True,
        )

    @ui.button(label="📄 Export CHANGELOG.md", style=discord.ButtonStyle.secondary, row=0)
    async def export_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        md_bytes = cl_service.render_markdown_changelog(self.changelog)
        await interaction.response.send_message(
            file=discord.File(io.BytesIO(md_bytes), filename="CHANGELOG.md"),
            ephemeral=True,
        )

