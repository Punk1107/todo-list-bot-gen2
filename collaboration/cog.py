"""
collaboration/cog.py — Slash Command Group /project for Shared Projects

Slash commands:
  /project create            — สร้างโปรเจกต์ใหม่ในเซิร์ฟเวอร์
  /project list              — รายชื่อโปรเจกต์ทั้งหมดในเซิร์ฟเวอร์
  /project view [id]         — ดู Dashboard รายละเอียดโปรเจกต์
  /project board [id]        — ดูกระดาน Kanban แบบ Interactive
  /project add-task [id]     — เพิ่ม Task เข้าโปรเจกต์
  /project my-tasks          — ดูงานที่ตนเองได้รับมอบหมายในเซิร์ฟเวอร์นี้
  /project members [id]      — ดูและจัดการสมาชิก
  /project activity [id]     — ดูกิจกรรมล่าสุด
  /project archive [id]      — ปิดเก็บโปรเจกต์เข้ากรุ

All commands enforce:
  - Guild-only check (DM scope guard)
  - guild_id isolation via service layer
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from collaboration import service
from collaboration.views import (
    CreateProjectModal,
    ProjectDashboardView,
    ProjectBoardView,
    build_project_list_embed,
    ProjectListView,
    build_project_dashboard_embed,
    build_board_embed,
    build_members_embed,
    build_activity_embed,
    build_my_tasks_embed,
)
from core.security import rate_limit_check
from locales.i18n import t
from utils.helpers import get_user_lang, ensure_user

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: guild-only guard
# ─────────────────────────────────────────────────────────────────────────────

async def _guild_only(interaction: discord.Interaction, lang: str) -> bool:
    """Return True if we're in a guild, False + send error if in DMs."""
    if not interaction.guild:
        await interaction.response.send_message(t("proj_guild_only", lang), ephemeral=True)
        return False
    return True


def _is_admin(interaction: discord.Interaction) -> bool:
    """Check if the interacting member has Administrator permission."""
    if isinstance(interaction.user, discord.Member):
        return interaction.user.guild_permissions.administrator
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────────────────────────

class CollaborationCog(commands.Cog, name="Collaboration"):
    """Shared Projects collaboration commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    project = app_commands.Group(
        name="project",
        description="🤝 ระบบโปรเจกต์ร่วมกัน / Shared project collaboration",
    )

    # ─────────────────────────────────────────────────────────────────────────
    # /project create
    # ─────────────────────────────────────────────────────────────────────────

    @project.command(name="create", description="🎉 สร้างโปรเจกต์ร่วมใหม่ในเซิร์ฟเวอร์ / Create a new shared project")
    @app_commands.describe(priority="ระดับความสำคัญ / Priority level (0-7, default: 0)")
    @app_commands.choices(priority=[
        app_commands.Choice(name="⬜ 0: Normal / ปกติ",     value=0),
        app_commands.Choice(name="🟦 1: Low / ต่ำ",          value=1),
        app_commands.Choice(name="🟩 2: Medium / ปานกลาง",   value=2),
        app_commands.Choice(name="🟨 3: High / สูง",         value=3),
        app_commands.Choice(name="🟧 4: Urgent / ด่วน",      value=4),
        app_commands.Choice(name="🟥 5: Immediate / ด่วนมาก", value=5),
        app_commands.Choice(name="🔴 6: Critical / วิกฤต",   value=6),
        app_commands.Choice(name="🆘 7: Emergency / ฉุกเฉิน", value=7),
    ])
    @rate_limit_check("command")
    async def project_create(self, interaction: discord.Interaction, priority: Optional[int] = 0) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await ensure_user(uid, lang)
        modal = CreateProjectModal(lang, priority=priority or 0)
        await interaction.response.send_modal(modal)

    # ─────────────────────────────────────────────────────────────────────────
    # /project list
    # ─────────────────────────────────────────────────────────────────────────

    @project.command(name="list", description="📋 ดูโปรเจกต์ทั้งหมดในเซิร์ฟเวอร์ / List all projects in this server")
    @app_commands.describe(status="Filter by status (default: active)")
    @app_commands.choices(status=[
        app_commands.Choice(name="🟢 Active / กำลังดำเนินการ",   value="active"),
        app_commands.Choice(name="✅ Completed / เสร็จแล้ว",       value="completed"),
        app_commands.Choice(name="📦 Archived / เก็บเข้ากรุ",     value="archived"),
        app_commands.Choice(name="🔍 All / ทั้งหมด",              value="all"),
    ])
    @rate_limit_check("command")
    async def project_list(self, interaction: discord.Interaction, status: str = "active") -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer()

        guild_id    = str(interaction.guild.id)
        status_arg  = None if status == "all" else status
        projects    = await service.get_guild_projects(guild_id, status=status_arg)
        guild_name  = interaction.guild.name
        embed       = build_project_list_embed(projects, guild_name, lang)
        if projects:
            view = ProjectListView(projects, uid, lang)
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # /project view
    # ─────────────────────────────────────────────────────────────────────────

    @project.command(name="view", description="📊 ดู Dashboard โปรเจกต์ / View project dashboard")
    @app_commands.describe(project_id="Project ID number")
    @rate_limit_check("command")
    async def project_view(self, interaction: discord.Interaction, project_id: int) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        try:
            stats = await service.get_project_stats(project_id, guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(
                t("proj_not_found", lang, project_id=project_id), ephemeral=True
            )
            return

        embed = build_project_dashboard_embed(stats, lang)
        view  = ProjectDashboardView(project_id, guild_id, lang, interaction.user)
        msg   = await interaction.followup.send(embed=embed, view=view)
        view._message = msg

    # ─────────────────────────────────────────────────────────────────────────
    # /project board
    # ─────────────────────────────────────────────────────────────────────────

    @project.command(name="board", description="📋 ดูกระดาน Kanban ของโปรเจกต์ / View project kanban board")
    @app_commands.describe(project_id="Project ID number")
    @rate_limit_check("command")
    async def project_board(self, interaction: discord.Interaction, project_id: int) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        try:
            board = await service.get_project_board(project_id, guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(
                t("proj_not_found", lang, project_id=project_id), ephemeral=True
            )
            return

        embed = build_board_embed(board, lang, "pending")
        view  = ProjectBoardView(project_id, guild_id, lang, interaction.user, board)
        await interaction.followup.send(embed=embed, view=view)
        view._message = await interaction.original_response()

    # ─────────────────────────────────────────────────────────────────────────
    # /project add-task
    # ─────────────────────────────────────────────────────────────────────────

    @project.command(name="add-task", description="➕ เพิ่ม Task เข้าโปรเจกต์ / Add a task to a project")
    @app_commands.describe(
        project_id="Project ID number",
        priority="ระดับความสำคัญ / Priority level (0-7, default: 0)",
    )
    @app_commands.choices(priority=[
        app_commands.Choice(name="⬜ 0: Normal / ปกติ",     value=0),
        app_commands.Choice(name="🟦 1: Low / ต่ำ",          value=1),
        app_commands.Choice(name="🟩 2: Medium / ปานกลาง",   value=2),
        app_commands.Choice(name="🟨 3: High / สูง",         value=3),
        app_commands.Choice(name="🟧 4: Urgent / ด่วน",      value=4),
        app_commands.Choice(name="🟥 5: Immediate / ด่วนมาก", value=5),
        app_commands.Choice(name="🔴 6: Critical / วิกฤต",   value=6),
        app_commands.Choice(name="🆘 7: Emergency / ฉุกเฉิน", value=7),
    ])
    @rate_limit_check("command")
    async def project_add_task(
        self, interaction: discord.Interaction, project_id: int, priority: Optional[int] = 0
    ) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await ensure_user(uid, lang)

        guild_id = str(interaction.guild.id)
        try:
            project = await service.get_project(project_id, guild_id)
        except service.ProjectNotFound:
            await interaction.response.send_message(
                t("proj_not_found", lang, project_id=project_id), ephemeral=True
            )
            return

        if project.status != "active":
            await interaction.response.send_message(
                t("proj_not_active", lang, status=project.status), ephemeral=True
            )
            return

        from collaboration.views import AddProjectTaskModal
        modal = AddProjectTaskModal(project, lang, priority=priority or 0)
        await interaction.response.send_modal(modal)

    # ─────────────────────────────────────────────────────────────────────────
    # /project set-priority
    # ─────────────────────────────────────────────────────────────────────────

    @project.command(name="set-priority", description="🎯 ตั้งระดับความสำคัญของโปรเจกต์ / Set project priority")
    @app_commands.describe(
        project_id="Project ID number",
        priority="Priority level (0-7)",
    )
    @app_commands.choices(priority=[
        app_commands.Choice(name="⬜ 0: Normal / ปกติ",     value=0),
        app_commands.Choice(name="🟦 1: Low / ต่ำ",          value=1),
        app_commands.Choice(name="🟩 2: Medium / ปานกลาง",   value=2),
        app_commands.Choice(name="🟨 3: High / สูง",         value=3),
        app_commands.Choice(name="🟧 4: Urgent / ด่วน",      value=4),
        app_commands.Choice(name="🟥 5: Immediate / ด่วนมาก", value=5),
        app_commands.Choice(name="🔴 6: Critical / วิกฤต",   value=6),
        app_commands.Choice(name="🆘 7: Emergency / ฉุกเฉิน", value=7),
    ])
    @rate_limit_check("command")
    async def project_set_priority(
        self, interaction: discord.Interaction, project_id: int, priority: int
    ) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)
        is_admin = _is_admin(interaction)

        try:
            updated = await service.update_project_priority(
                project_id, guild_id, priority, uid, is_guild_admin=is_admin
            )
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=project_id), ephemeral=True)
            return
        except service.ProjectPermissionError:
            await interaction.followup.send(t("proj_no_permission", lang), ephemeral=True)
            return
        except Exception as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        prio_text = f"{updated.priority_emoji} {t(f'priority_{updated.priority}', lang)} (P{updated.priority})"
        await interaction.followup.send(
            t("proj_priority_updated", lang, priority=prio_text),
            ephemeral=True,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # /project complete-task
    # ─────────────────────────────────────────────────────────────────────────

    @project.command(name="complete-task", description="✅ ปิดงานในโปรเจกต์ / Mark a project task as completed")
    @app_commands.describe(
        project_id="Project ID number",
        task_id="Task ID number to complete",
    )
    @rate_limit_check("command")
    async def project_complete_task(
        self,
        interaction: discord.Interaction,
        project_id: int,
        task_id: int,
    ) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        is_admin = _is_admin(interaction)

        try:
            task = await service.update_task_status(
                task_id, project_id, guild_id,
                "Completed", uid, is_guild_admin=is_admin
            )
            project = await service.get_project(project_id, guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(
                t("proj_not_found", lang, project_id=project_id), ephemeral=True
            )
            return
        except service.TaskNotFound:
            await interaction.followup.send(
                t("proj_task_not_found", lang, task_id=task_id), ephemeral=True
            )
            return
        except service.ProjectPermissionError:
            await interaction.followup.send(t("proj_no_permission", lang), ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🎉 {t('proj_task_completed_title', lang)}",
            description=t(
                "proj_task_completed_desc", lang,
                user=interaction.user.mention, task_id=task.task_id, name=task.task
            ),
            color=0x57F287,
        )
        embed.set_footer(text=f"{project.emoji} {project.name} · #{project.project_id}")
        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # /project my-tasks
    # ─────────────────────────────────────────────────────────────────────────

    @project.command(name="my-tasks", description="🙋 ดู Task ที่คุณได้รับมอบหมายในเซิร์ฟเวอร์ / Your assigned tasks")
    @rate_limit_check("command")
    async def project_my_tasks(self, interaction: discord.Interaction) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        tasks    = await service.get_user_assigned_tasks(guild_id, uid)
        embed    = build_my_tasks_embed(tasks, lang, interaction.user.display_name)
        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # /project members
    # ─────────────────────────────────────────────────────────────────────────

    @project.command(name="members", description="👥 ดูและจัดการสมาชิกโปรเจกต์ / View and manage project members")
    @app_commands.describe(project_id="Project ID number")
    @rate_limit_check("command")
    async def project_members(self, interaction: discord.Interaction, project_id: int) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        try:
            project = await service.get_project(project_id, guild_id)
            members = await service.get_project_members(project_id, guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(
                t("proj_not_found", lang, project_id=project_id), ephemeral=True
            )
            return

        embed = build_members_embed(members, project, lang)
        from collaboration.views import MembersView
        view  = MembersView(project, lang, interaction.user, members)
        await interaction.followup.send(embed=embed, view=view)
        view._message = await interaction.original_response()

    # ─────────────────────────────────────────────────────────────────────────
    # /project add-member
    # ─────────────────────────────────────────────────────────────────────────

    @project.command(name="add-member", description="➕ เพิ่มสมาชิกเข้าโปรเจกต์ / Add a member to a project")
    @app_commands.describe(
        project_id="Project ID number",
        user="Member to add to the project",
        role="Role in the project (member or lead)",
    )
    @app_commands.choices(role=[
        app_commands.Choice(name="👤 Member / สมาชิกทั่วไป", value="member"),
        app_commands.Choice(name="👑 Lead / หัวหน้าโปรเจกต์", value="lead"),
    ])
    @rate_limit_check("command")
    async def project_add_member(
        self,
        interaction: discord.Interaction,
        project_id: int,
        user: discord.Member,
        role: str = "member",
    ) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer()

        if user.bot:
            await interaction.followup.send(t("proj_member_bot_error", lang), ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        is_admin = _is_admin(interaction)

        try:
            project = await service.add_member(
                project_id, guild_id,
                str(user.id), role,
                uid, is_guild_admin=is_admin,
            )
        except service.ProjectNotFound:
            await interaction.followup.send(
                t("proj_not_found", lang, project_id=project_id), ephemeral=True
            )
            return
        except service.ProjectPermissionError:
            await interaction.followup.send(t("proj_no_permission", lang), ephemeral=True)
            return

        # Send DM notification to the invited user
        guild_name = interaction.guild.name if interaction.guild else "Server"
        dm_sent = await service.send_project_invite_dm(
            user, project, guild_name, interaction.user, role
        )
        dm_status = t("proj_member_dm_sent", lang) if dm_sent else t("proj_member_dm_failed", lang)

        role_label = t(f"proj_role_{role}", lang) if role in ("lead", "member", "viewer") else role.capitalize()
        desc = t(
            "proj_member_added_desc", lang,
            user=user.mention,
            project=f"{project.emoji} {project.name}",
            role=role_label,
            dm_status=dm_status,
        )
        embed = discord.Embed(
            title=f"🎉 {t('proj_member_added_title', lang)}",
            description=desc,
            color=int(project.color.lstrip("#"), 16) if project.color.startswith("#") else 0x57F287,
        )
        embed.set_footer(text=t("proj_footer_id", lang, project_id=project.project_id))
        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # /project activity
    # ─────────────────────────────────────────────────────────────────────────

    @project.command(name="activity", description="📜 ดูกิจกรรมล่าสุดของโปรเจกต์ / View project activity feed")
    @app_commands.describe(project_id="Project ID number")
    @rate_limit_check("command")
    async def project_activity(self, interaction: discord.Interaction, project_id: int) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        try:
            project    = await service.get_project(project_id, guild_id)
            activities = await service.get_project_activity(project_id, guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(
                t("proj_not_found", lang, project_id=project_id), ephemeral=True
            )
            return

        embed = build_activity_embed(activities, project, lang)
        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # /project archive
    # ─────────────────────────────────────────────────────────────────────────

    @project.command(name="archive", description="📦 ปิดหรือเก็บโปรเจกต์เข้ากรุ / Archive a project")
    @app_commands.describe(
        project_id="Project ID to archive",
        action="Archive or mark as completed",
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="📦 Archive / เก็บเข้ากรุ",        value="archived"),
        app_commands.Choice(name="✅ Mark Completed / ปิดสำเร็จ",   value="completed"),
    ])
    @rate_limit_check("command")
    async def project_archive(
        self, interaction: discord.Interaction, project_id: int, action: str = "archived"
    ) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer(ephemeral=True)

        guild_id    = str(interaction.guild.id)
        is_admin    = _is_admin(interaction)
        try:
            project = await service.update_project_status(
                project_id, guild_id, action, uid, is_guild_admin=is_admin
            )
        except service.ProjectNotFound:
            await interaction.followup.send(
                t("proj_not_found", lang, project_id=project_id), ephemeral=True
            )
            return
        except service.ProjectPermissionError:
            await interaction.followup.send(t("proj_no_permission", lang), ephemeral=True)
            return

        action_key = "proj_archived_success" if action == "archived" else "proj_completed_success"
        embed = discord.Embed(
            title  = t(action_key, lang, name=project.name),
            color  = 0x95A5A6 if action == "archived" else 0x57F287,
        )
        embed.set_footer(text=t("proj_footer_id", lang, project_id=project.project_id))
        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # /project set-channel
    # ─────────────────────────────────────────────────────────────────────────

    @project.command(
        name="set-channel",
        description="🔔 ตั้งช่องสำหรับรับแจ้งเตือน Realtime / Set the notification channel for a project",
    )
    @app_commands.describe(
        project_id="Project ID to configure",
        channel="Discord channel to receive task completion announcements",
    )
    @rate_limit_check("command")
    async def project_set_channel(
        self,
        interaction: discord.Interaction,
        project_id: int,
        channel: discord.TextChannel,
    ) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)
        is_admin = _is_admin(interaction)
        try:
            project = await service.get_project(project_id, guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(
                t("proj_not_found", lang, project_id=project_id), ephemeral=True
            )
            return

        # Only lead/owner/admin can configure notification channel
        try:
            await service.require_role(project, uid, "lead", is_guild_admin=is_admin)
        except service.ProjectPermissionError:
            await interaction.followup.send(t("proj_no_permission", lang), ephemeral=True)
            return

        # Persist to DB
        from core.database import db
        await db.execute(
            "UPDATE projects SET notification_channel_id=$1 WHERE project_id=$2 AND guild_id=$3",
            (channel.id, project_id, guild_id),
        )
        db.query_cache.invalidate_all()

        embed = discord.Embed(
            title=t("proj_channel_set_title", lang),
            description=t(
                "proj_channel_set_body", lang,
                project_emoji=project.emoji,
                project_name=project.name,
                channel=channel.mention,
            ),
            color=0x57F287,
        )
        embed.set_footer(text=t("proj_footer_id", lang, project_id=project_id))
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CollaborationCog(bot))
