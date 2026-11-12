"""
custom_fields/cog.py — Slash commands /field (create, list, set, filter, delete) for JSONB EAV.
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.security import rate_limit_check
from custom_fields import service as field_service
from custom_fields.models import parse_custom_fields_json
from custom_fields.views import TaskCustomFieldsView, build_fields_list_embed
from locales.i18n import t
from utils.helpers import ensure_user, get_user_lang

log = logging.getLogger(__name__)

_FIELD_TYPE_CHOICES = [
    app_commands.Choice(name="🔽 Dropdown / Single Select", value="select"),
    app_commands.Choice(name="📝 Text Input (Link/Text)", value="text"),
    app_commands.Choice(name="🔢 Numeric Value", value="number"),
    app_commands.Choice(name="📅 Date Picker (YYYY-MM-DD)", value="date"),
]


async def _project_task_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[int]]:
    if not interaction.guild:
        return []
    gid = str(interaction.guild.id)
    try:
        if current:
            rows = await db.afetchall(
                """SELECT task_id, task, project_id
                   FROM tasks
                   WHERE guild_id = $1 AND project_id IS NOT NULL AND is_deleted = FALSE
                     AND (task ILIKE $2 OR CAST(task_id AS TEXT) ILIKE $2)
                   ORDER BY updated_at DESC LIMIT 25""",
                (gid, f"%{current}%"),
            )
        else:
            rows = await db.afetchall(
                """SELECT task_id, task, project_id
                   FROM tasks
                   WHERE guild_id = $1 AND project_id IS NOT NULL AND is_deleted = FALSE
                   ORDER BY updated_at DESC LIMIT 25""",
                (gid,),
            )
        return [
            app_commands.Choice(
                name=f"#{r['task_id']} [P#{r['project_id']}] {str(r['task'])[:60]}"[:100],
                value=int(r["task_id"]),
            )
            for r in (rows or [])
        ]
    except Exception:
        return []


async def _field_key_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    if not interaction.guild:
        return []
    gid = str(interaction.guild.id)
    ns = getattr(interaction, "namespace", None)
    proj_id = getattr(ns, "project_id", None) if ns else None
    try:
        if proj_id is not None:
            rows = await db.afetchall(
                """SELECT field_key, field_label, field_type
                   FROM project_custom_fields
                   WHERE guild_id = $1 AND project_id = $2
                     AND (field_key ILIKE $3 OR field_label ILIKE $3)
                   ORDER BY field_id ASC LIMIT 25""",
                (gid, int(proj_id), f"%{current}%"),
            )
        else:
            rows = await db.afetchall(
                """SELECT DISTINCT field_key, field_label, field_type
                   FROM project_custom_fields
                   WHERE guild_id = $1 AND (field_key ILIKE $2 OR field_label ILIKE $2)
                   ORDER BY field_key ASC LIMIT 25""",
                (gid, f"%{current}%"),
            )
        return [
            app_commands.Choice(
                name=f"{r['field_label']} ({r['field_key']} · {r['field_type']})"[:100],
                value=str(r["field_key"]),
            )
            for r in (rows or [])
        ]
    except Exception:
        return []


class CustomFieldsCog(commands.Cog, name="CustomFields"):
    """Custom Dynamic Meta-Fields Engine (JSONB EAV + GIN Filter)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    field = app_commands.Group(
        name="field",
        description="🧩 ฟิลด์ข้อมูลเฉพาะของโปรเจกต์ (JSONB EAV) / Project custom meta-fields",
        guild_only=True,
    )

    @field.command(name="create", description="➕ สร้างฟิลด์ข้อมูลใหม่ให้โปรเจกต์ / Create a custom project field")
    @app_commands.describe(
        project_id="รหัสโปรเจกต์ / Project ID",
        label="ชื่อแสดงผลของฟิลด์ (เช่น Environment, PR Link) / Field display label",
        field_type="ชนิดข้อมูล / Field type",
        options="ตัวเลือกคั่นด้วยจุลภาค (สำหรับ Dropdown เช่น Staging,Production) / Select options CSV",
        key="รหัส key JSONB (ไม่ระบุ = สร้างจาก label อัตโนมัติ) / Custom JSONB key (optional)",
        required="บังคับกรอกหรือไม่ / Whether value is required when editing",
    )
    @app_commands.choices(field_type=_FIELD_TYPE_CHOICES)
    @rate_limit_check("command")
    async def field_create(
        self,
        interaction: discord.Interaction,
        project_id: int,
        label: str,
        field_type: str,
        options: Optional[str] = None,
        key: Optional[str] = None,
        required: Optional[bool] = False,
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
            fd = await field_service.create_field_definition(
                project_id=project_id,
                guild_id=gid,
                actor_id=uid,
                label=label,
                field_type=field_type,
                options_csv=options,
                field_key=key,
                is_required=bool(required),
                is_guild_admin=is_admin,
            )
        except field_service.CustomFieldError as exc:
            await interaction.followup.send(t(str(exc), lang), ephemeral=True)
            return
        except Exception as exc:
            from collaboration.service import ProjectNotFound
            if isinstance(exc, ProjectNotFound):
                await interaction.followup.send(t("proj_not_found", lang, project_id=project_id), ephemeral=True)
                return
            log.error("field_create error: %s", exc, exc_info=True)
            await interaction.followup.send(t("err_db", lang), ephemeral=True)
            return

        await interaction.followup.send(
            t(
                "field_created_msg",
                lang,
                label=fd.field_label,
                field_key=fd.field_key,
                field_type=fd.field_type,
            ),
            ephemeral=True,
        )

    @field.command(name="list", description="📋 ดูรายการ Custom Fields ของโปรเจกต์ / List project custom fields")
    @app_commands.describe(project_id="รหัสโปรเจกต์ / Project ID")
    @rate_limit_check("command")
    async def field_list(self, interaction: discord.Interaction, project_id: int) -> None:
        uid = str(interaction.user.id)
        gid = str(interaction.guild.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)

        from collaboration import service as collab_service
        try:
            proj = await collab_service.get_project(project_id, gid)
        except collab_service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=project_id), ephemeral=True)
            return

        defs = await field_service.list_field_definitions(project_id, gid)
        embed = build_fields_list_embed(proj.name, defs, lang)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @field.command(name="set", description="🏷️ กรอกหรือแก้ไขค่า Custom Fields ของงาน / Set custom fields on a task")
    @app_commands.describe(
        task_id="รหัสงานในโปรเจกต์ / Project Task ID",
        field_key="รหัสฟิลด์ (ไม่ระบุ = เปิดแผง UI แบบ Dropdown & Modal) / Field key (optional)",
        value="ค่าที่ต้องการตั้ง (หรือเว้นว่างเพื่อเปิด UI) / Value to set",
    )
    @app_commands.autocomplete(task_id=_project_task_autocomplete, field_key=_field_key_autocomplete)
    @rate_limit_check("command")
    async def field_set(
        self,
        interaction: discord.Interaction,
        task_id: int,
        field_key: Optional[str] = None,
        value: Optional[str] = None,
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

        if field_key and value is not None:
            try:
                await field_service.set_task_custom_fields_batch(
                    task_id=task_id,
                    guild_id=gid,
                    updates={field_key: value},
                    actor_id=uid,
                    is_guild_admin=is_admin,
                )
            except field_service.CustomFieldError as exc:
                await interaction.followup.send(t(str(exc), lang), ephemeral=True)
                return

        row = await db.afetchone(
            "SELECT task_id, task, project_id, guild_id, custom_fields, is_deleted FROM tasks WHERE task_id = $1",
            (task_id,),
        )
        if not row or row.get("is_deleted"):
            await interaction.followup.send(t("task_not_found", lang, task_id=task_id), ephemeral=True)
            return
        if not row.get("project_id") or str(row.get("guild_id") or "") != gid:
            await interaction.followup.send(t("field_project_task_required", lang), ephemeral=True)
            return

        proj_id = int(row["project_id"])
        defs = await field_service.list_field_definitions(proj_id, gid)
        cur_vals = parse_custom_fields_json(row.get("custom_fields"))
        panel = TaskCustomFieldsView(
            task_id=task_id,
            task_title=str(row["task"]),
            project_id=proj_id,
            guild_id=gid,
            field_defs=defs,
            current_values=cur_vals,
            lang=lang,
        )
        await interaction.followup.send(embed=panel.make_embed(), view=panel, ephemeral=True)

    @field.command(
        name="filter",
        description="🔎 ค้นหางานด้วยค่า Custom Field (JSONB GIN) / Filter tasks by custom field",
    )
    @app_commands.describe(
        project_id="รหัสโปรเจกต์ / Project ID",
        field_key="รหัสฟิลด์ที่ต้องการกรอง / Field key",
        value="ค่าที่ต้องการค้นหา / Value to match",
    )
    @app_commands.autocomplete(field_key=_field_key_autocomplete)
    @rate_limit_check("search")
    async def field_filter(
        self,
        interaction: discord.Interaction,
        project_id: int,
        field_key: str,
        value: str,
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
            field_def, rows = await field_service.filter_tasks_by_custom_field(
                project_id=project_id,
                guild_id=gid,
                field_key=field_key,
                raw_value=value,
                actor_id=uid,
                is_guild_admin=is_admin,
            )
        except field_service.CustomFieldError as exc:
            await interaction.followup.send(t(str(exc), lang), ephemeral=True)
            return
        except Exception as exc:
            from collaboration.service import ProjectNotFound
            if isinstance(exc, ProjectNotFound):
                await interaction.followup.send(t("proj_not_found", lang, project_id=project_id), ephemeral=True)
                return
            log.error("field_filter error: %s", exc, exc_info=True)
            await interaction.followup.send(t("err_db", lang), ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🔎 {field_def.type_emoji} {field_def.field_label} = `{value}`",
            color=0x8B5CF6,
        )
        if not rows:
            embed.description = f"> {t('field_filter_empty', lang)}"
        else:
            lines = [
                f"• **#{r['task_id']}** [P{r['priority']}] {r['task']} (`{r['status']}`)"
                for r in rows[:20]
            ]
            embed.description = "\n".join(lines)[:4090]
        embed.set_footer(text=t("footer_text", lang))
        await interaction.followup.send(embed=embed, ephemeral=True)

    @field.command(name="delete", description="🗑️ ลบนิยาม Custom Field ของโปรเจกต์ / Delete a project custom field")
    @app_commands.describe(
        project_id="รหัสโปรเจกต์ / Project ID",
        field_key="รหัสฟิลด์ที่จะลบ / Field key to delete",
    )
    @app_commands.autocomplete(field_key=_field_key_autocomplete)
    @rate_limit_check("command")
    async def field_delete(
        self,
        interaction: discord.Interaction,
        project_id: int,
        field_key: str,
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
            await field_service.delete_field_definition(
                project_id=project_id,
                guild_id=gid,
                field_key=field_key,
                actor_id=uid,
                is_guild_admin=is_admin,
            )
        except field_service.CustomFieldError as exc:
            await interaction.followup.send(t(str(exc), lang), ephemeral=True)
            return
        await interaction.followup.send(
            t("field_deleted_msg", lang, field_key=field_key),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CustomFieldsCog(bot))
