"""
changelog/cog.py — Slash commands /changelog generate and /changelog set-channel.
"""
from __future__ import annotations

import io
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from changelog import service as cl_service
from changelog.views import ChangelogPreviewView
from core.database import db
from core.security import rate_limit_check
from locales.i18n import t
from utils.helpers import ensure_user, get_user_lang

log = logging.getLogger(__name__)


async def _sprint_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[int]]:
    if not interaction.guild:
        return []
    ns = getattr(interaction, "namespace", None)
    proj_id = getattr(ns, "project_id", None) if ns else None
    try:
        if proj_id is not None:
            rows = await db.afetchall(
                """SELECT sprint_id, name, status
                   FROM sprints
                   WHERE project_id = $1 AND (name ILIKE $2 OR CAST(sprint_id AS TEXT) ILIKE $2)
                   ORDER BY sprint_id DESC LIMIT 25""",
                (int(proj_id), f"%{current}%"),
            )
        else:
            rows = await db.afetchall(
                """SELECT s.sprint_id, s.name, s.status
                   FROM sprints s
                   JOIN projects p ON p.project_id = s.project_id
                   WHERE p.guild_id = $1 AND (s.name ILIKE $2 OR CAST(s.sprint_id AS TEXT) ILIKE $2)
                   ORDER BY s.sprint_id DESC LIMIT 25""",
                (str(interaction.guild.id), f"%{current}%"),
            )
        return [
            app_commands.Choice(
                name=f"#{r['sprint_id']} — {str(r['name'])[:65]} ({r['status']})"[:100],
                value=int(r["sprint_id"]),
            )
            for r in (rows or [])
        ]
    except Exception:
        return []


class ChangelogCog(commands.Cog, name="Changelog"):
    """Automated Semantic Release Notes & CHANGELOG.md Generator (/changelog)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    changelog = app_commands.Group(
        name="changelog",
        description="📰 สร้าง Release Notes & CHANGELOG.md อัตโนมัติ / Semantic Release Notes generator",
        guild_only=True,
    )

    @changelog.command(
        name="generate",
        description="📰 สรุปงานที่เสร็จสิ้นเป็น Release Notes (Conventional Commits) / Generate release notes",
    )
    @app_commands.describe(
        project_id="รหัสโปรเจกต์ / Project ID",
        sprint_id="รหัส Sprint ที่ต้องการสรุป (ไม่ระบุ = ช่วงวันที่) / Sprint ID (optional)",
        start_date="วันเริ่มต้น YYYY-MM-DD (ค่าเริ่มต้น: ย้อนหลัง 14 วัน) / Start date",
        end_date="วันสิ้นสุด YYYY-MM-DD (ค่าเริ่มต้น: วันนี้) / End date",
        version="ป้ายเวอร์ชัน (เช่น v2.5.0) / Version tag override",
        export_file="แนบไฟล์ CHANGELOG.md มาด้วยทันที / Also attach CHANGELOG.md immediately",
    )
    @app_commands.autocomplete(sprint_id=_sprint_autocomplete)
    @rate_limit_check("command")
    async def changelog_generate(
        self,
        interaction: discord.Interaction,
        project_id: int,
        sprint_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        version: Optional[str] = None,
        export_file: Optional[bool] = False,
    ) -> None:
        uid = str(interaction.user.id)
        gid = str(interaction.guild.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)
        is_admin = bool(
            hasattr(interaction.user, "guild_permissions")
            and interaction.user.guild_permissions.administrator
        )

        try:
            gen = await cl_service.generate_changelog(
                project_id=project_id,
                guild_id=gid,
                sprint_id=sprint_id,
                start_date=start_date,
                end_date=end_date,
                version=version,
                actor_id=uid,
                is_guild_admin=is_admin,
            )
        except cl_service.ChangelogError as exc:
            await interaction.followup.send(t(str(exc), lang), ephemeral=True)
            return
        except Exception as exc:
            from collaboration.service import ProjectNotFound
            if isinstance(exc, ProjectNotFound):
                await interaction.followup.send(t("proj_not_found", lang, project_id=project_id), ephemeral=True)
                return
            log.error("changelog_generate error: %s", exc, exc_info=True)
            await interaction.followup.send(t("err_db", lang), ephemeral=True)
            return

        view = ChangelogPreviewView(changelog=gen, user_id=uid, lang=lang)
        files = []
        if export_file:
            md_bytes = cl_service.render_markdown_changelog(gen)
            files.append(discord.File(io.BytesIO(md_bytes), filename="CHANGELOG.md"))

        await interaction.followup.send(
            embed=view.make_embed(),
            view=view,
            files=files,
            ephemeral=True,
        )

    @changelog.command(
        name="set-channel",
        description="📢 ตั้งค่าห้องประกาศ #releases สำหรับโปรเจกต์ / Configure #releases channel",
    )
    @app_commands.describe(
        project_id="รหัสโปรเจกต์ / Project ID",
        channel="ห้องข้อความที่จะใช้ประกาศ Release Notes / Target announcement channel",
    )
    @rate_limit_check("command")
    async def changelog_set_channel(
        self,
        interaction: discord.Interaction,
        project_id: int,
        channel: discord.TextChannel,
    ) -> None:
        uid = str(interaction.user.id)
        gid = str(interaction.guild.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)
        is_admin = bool(
            hasattr(interaction.user, "guild_permissions")
            and interaction.user.guild_permissions.administrator
        )
        try:
            await cl_service.set_release_channel(
                project_id=project_id,
                guild_id=gid,
                channel_id=channel.id,
                actor_id=uid,
                is_guild_admin=is_admin,
            )
        except cl_service.ChangelogError as exc:
            await interaction.followup.send(t(str(exc), lang), ephemeral=True)
            return
        except Exception as exc:
            from collaboration.service import ProjectNotFound
            if isinstance(exc, ProjectNotFound):
                await interaction.followup.send(t("proj_not_found", lang, project_id=project_id), ephemeral=True)
                return
            log.error("changelog_set_channel error: %s", exc, exc_info=True)
            await interaction.followup.send(t("err_db", lang), ephemeral=True)
            return

        await interaction.followup.send(
            t("changelog_channel_set", lang, channel=channel.mention, project_id=project_id),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChangelogCog(bot))

