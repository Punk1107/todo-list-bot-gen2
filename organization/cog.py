"""
organization/cog.py — Slash commands for Eisenhower Matrix and Custom Saved Filters
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.security import rate_limit_check
from locales.i18n import t
from organization.models import SavedFilterCriteria
from organization import service
from organization.views import (
    EisenhowerMatrixView,
    build_filter_list_embed,
    build_matrix_embed,
    build_saved_filter_embed,
)
from utils.helpers import get_user_lang, get_user_theme_color

log = logging.getLogger(__name__)


class OrganizationCog(commands.Cog):
    """Cog providing Eisenhower Matrix View and Custom Saved Filters (Smart Lists)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ─────────────────────────────────────────────────────────────────────────
    # /matrix — Eisenhower 4D Matrix
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="matrix",
        description="🧭 Eisenhower Matrix (4 มิติ) — วิเคราะห์ความสำคัญและความเร่งด่วนของงาน",
    )
    @app_commands.describe(
        project_id="Project ID (ถ้าต้องการดูเฉพาะงานใน Shared Project)",
    )
    @rate_limit_check("command")
    async def matrix_cmd(
        self,
        interaction: discord.Interaction,
        project_id: Optional[int] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=False)

        uid = str(interaction.user.id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        lang = await get_user_lang(uid)
        theme_color = await get_user_theme_color(uid)

        is_admin = False
        if interaction.guild and hasattr(interaction.user, "guild_permissions"):
            is_admin = bool(interaction.user.guild_permissions.administrator) # type: ignore

        scope_name = None
        if project_id is not None and guild_id:
            try:
                from collaboration import service as collab_service
                proj = await collab_service.get_project(project_id, guild_id)
                scope_name = f"{proj.emoji} {proj.name}"
            except Exception:
                scope_name = f"Project #{project_id}"

        matrix = await service.get_eisenhower_matrix(
            user_id=uid,
            guild_id=guild_id,
            project_id=project_id,
            is_guild_admin=is_admin,
        )

        embed = build_matrix_embed(matrix, lang, theme_color, scope_name)
        view = EisenhowerMatrixView(
            user_id=uid,
            guild_id=guild_id,
            matrix=matrix,
            lang=lang,
            theme_color=theme_color,
            project_id=project_id,
            scope_name=scope_name,
        )
        await interaction.followup.send(embed=embed, view=view)

    # ─────────────────────────────────────────────────────────────────────────
    # /filter group — Custom Saved Filters & Smart Lists
    # ─────────────────────────────────────────────────────────────────────────

    filter_group = app_commands.Group(
        name="filter",
        description="🔖 จัดการมุมมองตัวกรองงานเฉพาะตัว (Custom Saved Filters / Smart Lists)",
    )

    @filter_group.command(
        name="save",
        description="💾 บันทึกตัวกรองงานเป็น Smart List ส่วนตัว / Save custom filter criteria",
    )
    @app_commands.describe(
        name="ชื่อตัวกรอง (เช่น '🚨 งานด่วนหน้างาน', 'VIP Clients')",
        tags="แท็กที่ต้องการกรอง (คั่นด้วยจุลภาค เช่น 'bug,urgent')",
        min_priority="ระดับความสำคัญต่ำสุด (0-7)",
        max_priority="ระดับความสำคัญสูงสุด (0-7)",
        status="สถานะงาน (Pending, In_Progress, Active, Completed)",
        project_id="กรองเฉพาะ Shared Project ID",
        due_within_days="มีกำหนดส่งภายในจำนวนวัน (เช่น 3 วัน)",
        sort_by="ลำดับการเรียง",
    )
    @app_commands.choices(
        status=[
            app_commands.Choice(name="⚡ Active (Pending + In_Progress)", value="Active"),
            app_commands.Choice(name="📋 Pending (รอดำเนินการ)", value="Pending"),
            app_commands.Choice(name="⏳ In_Progress (กำลังทำ)", value="In_Progress"),
            app_commands.Choice(name="✅ Completed (เสร็จแล้ว)", value="Completed"),
        ],
        sort_by=[
            app_commands.Choice(name="🔴 ความสำคัญสูงสุดก่อน (Priority DESC)", value="priority_desc"),
            app_commands.Choice(name="⏰ กำหนดส่งใกล้สุดก่อน (Deadline ASC)", value="deadline_asc"),
            app_commands.Choice(name="🆕 งานใหม่สุดก่อน (Created DESC)", value="created_desc"),
        ],
    )
    @rate_limit_check("command")
    async def filter_save_cmd(
        self,
        interaction: discord.Interaction,
        name: str,
        tags: Optional[str] = None,
        min_priority: Optional[int] = None,
        max_priority: Optional[int] = None,
        status: Optional[str] = None,
        project_id: Optional[int] = None,
        due_within_days: Optional[int] = None,
        sort_by: Optional[str] = "priority_desc",
    ) -> None:
        uid = str(interaction.user.id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        lang = await get_user_lang(uid)

        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        criteria = SavedFilterCriteria(
            tags=tag_list,
            min_priority=min_priority,
            max_priority=max_priority,
            status=status,
            project_id=project_id,
            due_within_days=due_within_days,
            sort_by=sort_by or "priority_desc",
        )

        try:
            saved = await service.create_saved_filter(
                owner_id=uid,
                name=name,
                criteria=criteria,
                guild_id=guild_id,
            )
            await interaction.response.send_message(
                f"✅ {t('filter_saved_success', lang, name=saved.name)}",
                ephemeral=True,
            )
        except ValueError as err:
            await interaction.response.send_message(f"❌ {err}", ephemeral=True)
        except Exception as exc:
            log.error("Failed to save filter for %s: %s", uid, exc)
            await interaction.response.send_message(f"❌ {t('error', lang)}", ephemeral=True)

    @filter_group.command(
        name="list",
        description="📋 ดูรายการตัวกรอง Smart Lists ทั้งหมดของคุณ / View all saved filters",
    )
    @rate_limit_check("command")
    async def filter_list_cmd(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        lang = await get_user_lang(uid)
        theme_color = await get_user_theme_color(uid)

        filters = await service.list_saved_filters(owner_id=uid, guild_id=guild_id)
        embed = build_filter_list_embed(filters, lang, theme_color)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @filter_group.command(
        name="use",
        description="🎯 เรียกดูชุดงานตามตัวกรองที่บันทึกไว้ / Apply and view saved filter tasks",
    )
    @app_commands.describe(name="ชื่อตัวกรองที่ต้องการเรียกดู / Saved filter name")
    @rate_limit_check("command")
    async def filter_use_cmd(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=False)

        uid = str(interaction.user.id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        lang = await get_user_lang(uid)
        theme_color = await get_user_theme_color(uid)

        saved = await service.get_saved_filter_by_name(owner_id=uid, name=name, guild_id=guild_id)
        if not saved:
            await interaction.followup.send(
                f"❌ {t('filter_not_found', lang, name=name)}", ephemeral=True
            )
            return

        tasks = await service.execute_saved_filter(saved, user_id=uid, guild_id=guild_id)
        embed = build_saved_filter_embed(saved, tasks, lang, theme_color)
        await interaction.followup.send(embed=embed)

    @filter_group.command(
        name="delete",
        description="🗑️ ลบตัวกรองที่บันทึกไว้ / Delete a saved filter",
    )
    @app_commands.describe(name="ชื่อตัวกรองที่ต้องการลบ / Saved filter name to delete")
    @rate_limit_check("command")
    async def filter_delete_cmd(self, interaction: discord.Interaction, name: str) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)

        deleted = await service.delete_saved_filter_by_name(owner_id=uid, name=name)
        if deleted:
            await interaction.response.send_message(
                f"🗑️ {t('filter_deleted_success', lang, name=name)}", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ {t('filter_not_found', lang, name=name)}", ephemeral=True
            )

    # ── Autocomplete for filter name ──────────────────────────────────────────

    @filter_use_cmd.autocomplete("name")
    @filter_delete_cmd.autocomplete("name")
    async def filter_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        uid = str(interaction.user.id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        try:
            filters = await service.list_saved_filters(owner_id=uid, guild_id=guild_id)
            choices = []
            for sf in filters:
                if not current or current.lower() in sf.name.lower():
                    choices.append(app_commands.Choice(name=sf.name, value=sf.name))
                if len(choices) >= 25:
                    break
            return choices
        except Exception:
            return []


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OrganizationCog(bot))
