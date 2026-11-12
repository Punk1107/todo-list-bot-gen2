"""Discord Cog for Cross-Guild Project Federation (/federation)."""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.security import rate_limit_check
from federation import service
from locales.i18n import t
from utils.helpers import ensure_user, get_user_lang

log = logging.getLogger(__name__)


def _is_guild_admin(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    perms = interaction.user.guild_permissions
    return perms.administrator or perms.manage_guild


class FederationCog(commands.Cog, name="Federation"):
    """Manage cross-server shared projects with isolated per-guild RBAC."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    federation_group = app_commands.Group(
        name="federation",
        description="🌐 เชื่อมโยงโปรเจกต์ข้ามเซิร์ฟเวอร์ / Cross-guild project federation",
        guild_only=True,
    )

    @federation_group.command(
        name="link",
        description="🔗 สร้างรหัสเชิญเพื่อแชร์โปรเจกต์ไปยังเซิร์ฟเวอร์อื่น / Create federation invite for another server",
    )
    @app_commands.describe(
        project_id="รหัสโปรเจกต์ / Home project ID",
        target_guild_id="Discord Server ID ปลายทาง / Target Server ID",
        default_role="สิทธิ์เริ่มต้นของสมาชิกเซิร์ฟเวอร์ปลายทาง / Default role scope",
    )
    @app_commands.choices(default_role=[
        app_commands.Choice(name="✏️ Member (ร่วมสร้าง/อัปเดตงาน)", value="member"),
        app_commands.Choice(name="👀 Viewer (ดูอย่างเดียว)", value="viewer"),
        app_commands.Choice(name="👑 Lead (จัดการบอร์ด)", value="lead"),
    ])
    @rate_limit_check("command")
    async def federation_link(
        self,
        interaction: discord.Interaction,
        project_id: int,
        target_guild_id: str,
        default_role: str = "member",
    ) -> None:
        if not interaction.guild_id:
            return
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)

        try:
            invite = await service.create_federation_invite(
                project_id=project_id,
                home_guild_id=str(interaction.guild_id),
                target_guild_id=target_guild_id,
                actor_id=uid,
                default_role=default_role,
                is_guild_admin=_is_guild_admin(interaction),
            )
        except service.FederationPermissionError:
            await interaction.followup.send(t("proj_no_permission", lang), ephemeral=True)
            return
        except (service.FederationError, ValueError) as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
            return

        embed = discord.Embed(
            title=t("fed_invite_created_title", lang, project_id=project_id),
            description=t(
                "fed_invite_created_desc",
                lang,
                code=invite.invite_code,
                target_guild=invite.target_guild_id,
                role=invite.default_role,
            ),
            color=0x5865F2,
        )
        embed.set_footer(text=t("footer_text", lang))
        await interaction.followup.send(embed=embed, ephemeral=True)

    @federation_group.command(
        name="accept",
        description="🤝 ยอมรับรหัสเชิญเชื่อมโปรเจกต์ข้ามเซิร์ฟเวอร์ / Accept a project federation invite",
    )
    @app_commands.describe(
        code="รหัสเชิญ 8 หลัก / 8-character invite code",
        channel="ห้องแจ้งเตือนอัปเดตงานข้ามเซิร์ฟเวอร์ / Sync notification channel",
    )
    @rate_limit_check("command")
    async def federation_accept(
        self,
        interaction: discord.Interaction,
        code: str,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if not interaction.guild_id:
            return
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)

        try:
            link = await service.accept_federation_invite(
                invite_code=code,
                target_guild_id=str(interaction.guild_id),
                actor_id=uid,
                sync_channel_id=channel.id if channel else None,
                is_guild_admin=_is_guild_admin(interaction),
            )
        except service.FederationPermissionError:
            await interaction.followup.send(t("proj_no_permission", lang), ephemeral=True)
            return
        except service.FederationError as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
            return

        embed = discord.Embed(
            title=t("fed_accepted_title", lang, project_id=link.project_id),
            description=t(
                "fed_accepted_desc",
                lang,
                project_id=link.project_id,
                role=link.role_scope,
            ),
            color=0x57F287,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @federation_group.command(
        name="unlink",
        description="🔓 ยกเลิกการเชื่อมโยงโปรเจกต์ข้ามเซิร์ฟเวอร์ / Revoke or leave project federation",
    )
    @app_commands.describe(
        project_id="รหัสโปรเจกต์ / Project ID",
        target_guild_id="Server ID ที่ต้องการยกเลิก (เว้นว่างเพื่อยกเลิกเซิร์ฟเวอร์นี้)",
    )
    @rate_limit_check("command")
    async def federation_unlink(
        self,
        interaction: discord.Interaction,
        project_id: int,
        target_guild_id: Optional[str] = None,
    ) -> None:
        if not interaction.guild_id:
            return
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await interaction.response.defer(ephemeral=True)

        target = (target_guild_id or str(interaction.guild_id)).strip()
        try:
            removed = await service.unlink_project_guild(
                project_id=project_id,
                actor_guild_id=str(interaction.guild_id),
                target_guild_id=target,
                actor_id=uid,
                is_guild_admin=_is_guild_admin(interaction),
            )
        except service.FederationPermissionError:
            await interaction.followup.send(t("proj_no_permission", lang), ephemeral=True)
            return
        except (service.FederationError, ValueError) as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
            return

        if not removed:
            await interaction.followup.send(t("fed_link_not_found", lang), ephemeral=True)
            return
        await interaction.followup.send(
            f"✅ {t('fed_unlinked_ok', lang, project_id=project_id, guild_id=target)}",
            ephemeral=True,
        )

    @federation_group.command(
        name="list",
        description="🌐 ดูรายชื่อเซิร์ฟเวอร์ที่เชื่อมโยงกับโปรเจกต์ / List federated servers for a project",
    )
    @app_commands.describe(project_id="รหัสโปรเจกต์ / Project ID")
    @rate_limit_check("command")
    async def federation_list(self, interaction: discord.Interaction, project_id: int) -> None:
        if not interaction.guild_id:
            return
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await interaction.response.defer(ephemeral=True)

        has_access = await service.has_federated_access(project_id, str(interaction.guild_id))
        if not has_access:
            await interaction.followup.send(t("proj_not_found", lang, project_id=project_id), ephemeral=True)
            return

        links = await service.get_project_federation_links(project_id)
        embed = discord.Embed(
            title=t("fed_list_title", lang, project_id=project_id),
            color=0x5865F2,
        )
        if not links:
            embed.description = t("fed_list_empty", lang)
        else:
            lines = []
            for lk in links:
                ch = f"<#{lk.sync_channel_id}>" if lk.sync_channel_id else "—"
                lines.append(f"• **Guild `{lk.guild_id}`** (`{lk.role_scope}`) · 📢 {ch}")
            embed.description = "\n".join(lines)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @federation_group.command(
        name="set-channel",
        description="📢 ตั้งค่าห้องแจ้งเตือนแบบเรียลไทม์ของเซิร์ฟเวอร์นี้ / Set sync channel",
    )
    @app_commands.describe(project_id="รหัสโปรเจกต์ / Project ID", channel="Text channel")
    @rate_limit_check("command")
    async def federation_set_channel(
        self,
        interaction: discord.Interaction,
        project_id: int,
        channel: discord.TextChannel,
    ) -> None:
        if not interaction.guild_id:
            return
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await interaction.response.defer(ephemeral=True)

        try:
            ok = await service.update_sync_channel(
                project_id=project_id,
                guild_id=str(interaction.guild_id),
                channel_id=channel.id,
                actor_id=uid,
                is_guild_admin=_is_guild_admin(interaction),
            )
        except service.FederationPermissionError:
            await interaction.followup.send(t("proj_no_permission", lang), ephemeral=True)
            return
        except service.FederationError as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
            return

        if not ok:
            await interaction.followup.send(t("fed_link_not_found", lang), ephemeral=True)
            return
        await interaction.followup.send(
            f"✅ {t('fed_channel_updated', lang, channel=channel.mention)}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FederationCog(bot))

