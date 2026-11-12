"""Discord Cog for Multi-Assignees & Collective Sign-off (/assign)."""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from assignments import service
from core.security import rate_limit_check
from gamification import service as gamification_service
from locales.i18n import t
from utils.helpers import ensure_user, get_user_lang

log = logging.getLogger(__name__)


def _is_guild_admin(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    perms = interaction.user.guild_permissions
    return perms.administrator or perms.manage_guild


def _resolve_role_member_ids(guild: Optional[discord.Guild], role_ids: list[int]) -> list[str]:
    if not guild or not role_ids:
        return []
    members: set[str] = set()
    for rid in role_ids:
        role = guild.get_role(rid)
        if role:
            for member in role.members:
                if not member.bot:
                    members.add(str(member.id))
    return sorted(members)


class AssignmentsCog(commands.Cog, name="Assignments"):
    """Assign multiple users or Discord Roles to tasks with First-Wins or All-Sign-Off modes."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    assign_group = app_commands.Group(
        name="assign",
        description="👥 มอบหมายงานหลายคนหรือทั้ง Role / Multi-assignee & role assignment",
    )

    @assign_group.command(
        name="users",
        description="👥 มอบหมายงานให้สมาชิกหลายคนพร้อมกัน / Assign multiple users to a task",
    )
    @app_commands.describe(
        task_id="รหัสงาน / Task ID",
        users="แท็กผู้ใช้หลายคนหรือวาง User ID คั่นด้วยเว้นวรรค (@user1 @user2)",
        mode="เงื่อนไขการปิดงาน / Completion mode",
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="⚡ First Finisher Wins (ใครทำเสร็จคนแรกถือว่าเสร็จ)", value="first_wins"),
        app_commands.Choice(name="🤝 All-Must-Sign-Off (ทุกคนต้องกดยืนยันครบ)", value="all_signoff"),
    ])
    @rate_limit_check("command")
    async def assign_users_cmd(
        self,
        interaction: discord.Interaction,
        task_id: int,
        users: str,
        mode: Optional[str] = None,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)

        parsed_ids = service.parse_user_ids(users)
        if not parsed_ids:
            await interaction.followup.send(t("assign_no_valid_users", lang), ephemeral=True)
            return

        try:
            summary = await service.assign_users(
                task_id=task_id,
                user_ids=parsed_ids,
                actor_id=uid,
                guild_id=str(interaction.guild_id) if interaction.guild_id else None,
                mode=mode,
                is_guild_admin=_is_guild_admin(interaction),
            )
        except service.AssignmentPermissionError:
            await interaction.followup.send(t("permission_denied", lang), ephemeral=True)
            return
        except (service.AssignmentError, ValueError) as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
            return

        mentions = ", ".join(f"<@{u}>" for u in summary.user_ids) or "—"
        embed = discord.Embed(
            title=t("assign_updated_title", lang, task_id=task_id),
            description=t(
                "assign_users_summary",
                lang,
                users=mentions,
                mode=summary.assignment_mode,
            ),
            color=0x5865F2,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @assign_group.command(
        name="role",
        description="🎭 มอบหมายงานให้ Discord Role ทั้งทีม / Assign a Discord role to a task",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        task_id="รหัสงาน / Task ID",
        role="Discord Role ที่รับผิดชอบ / Discord Role",
        mode="เงื่อนไขการปิดงาน / Completion mode",
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="⚡ First Finisher Wins", value="first_wins"),
        app_commands.Choice(name="🤝 All-Must-Sign-Off", value="all_signoff"),
    ])
    @rate_limit_check("command")
    async def assign_role_cmd(
        self,
        interaction: discord.Interaction,
        task_id: int,
        role: discord.Role,
        mode: Optional[str] = None,
    ) -> None:
        if not interaction.guild_id:
            return
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)

        try:
            summary = await service.assign_role(
                task_id=task_id,
                role_id=role.id,
                actor_id=uid,
                guild_id=str(interaction.guild_id),
                mode=mode,
                is_guild_admin=_is_guild_admin(interaction),
            )
        except service.AssignmentPermissionError:
            await interaction.followup.send(t("permission_denied", lang), ephemeral=True)
            return
        except (service.AssignmentError, ValueError) as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
            return

        roles_str = ", ".join(f"<@&{rid}>" for rid in summary.role_ids) or "—"
        await interaction.followup.send(
            f"✅ {t('assign_role_ok', lang, task_id=task_id, roles=roles_str, mode=summary.assignment_mode)}",
            ephemeral=True,
        )

    @assign_group.command(
        name="remove",
        description="➖ ถอนชื่อผู้รับผิดชอบออกจากงาน / Remove an assignee from a task",
    )
    @app_commands.describe(task_id="รหัสงาน / Task ID", user="ผู้ใช้ / User to unassign")
    @rate_limit_check("command")
    async def assign_remove_cmd(
        self,
        interaction: discord.Interaction,
        task_id: int,
        user: discord.Member | discord.User,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await interaction.response.defer(ephemeral=True)

        try:
            await service.remove_assignee(
                task_id=task_id,
                target_user_id=str(user.id),
                actor_id=uid,
                guild_id=str(interaction.guild_id) if interaction.guild_id else None,
                is_guild_admin=_is_guild_admin(interaction),
            )
        except service.AssignmentPermissionError:
            await interaction.followup.send(t("permission_denied", lang), ephemeral=True)
            return
        except service.AssignmentError as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
            return

        await interaction.followup.send(
            f"✅ {t('assign_removed_ok', lang, user=user.mention, task_id=task_id)}",
            ephemeral=True,
        )

    @assign_group.command(
        name="mode",
        description="⚙️ ตั้งเงื่อนไขการปิดงานกลุ่ม / Set First-Wins vs All-Must-Sign-Off",
    )
    @app_commands.describe(task_id="รหัสงาน / Task ID", mode="Completion policy")
    @app_commands.choices(mode=[
        app_commands.Choice(name="⚡ First Finisher Wins", value="first_wins"),
        app_commands.Choice(name="🤝 All-Must-Sign-Off", value="all_signoff"),
    ])
    @rate_limit_check("command")
    async def assign_mode_cmd(
        self,
        interaction: discord.Interaction,
        task_id: int,
        mode: str,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await interaction.response.defer(ephemeral=True)

        try:
            summary = await service.set_assignment_mode(
                task_id=task_id,
                mode=mode,
                actor_id=uid,
                guild_id=str(interaction.guild_id) if interaction.guild_id else None,
                is_guild_admin=_is_guild_admin(interaction),
            )
        except service.AssignmentPermissionError:
            await interaction.followup.send(t("permission_denied", lang), ephemeral=True)
            return
        except (service.AssignmentError, ValueError) as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
            return

        await interaction.followup.send(
            f"✅ {t('assign_mode_updated', lang, task_id=task_id, mode=summary.assignment_mode)}",
            ephemeral=True,
        )

    @assign_group.command(
        name="signoff",
        description="✍️ กดยืนยันความเสร็จในส่วนของคุณ (All-Must-Sign-Off) / Sign off your part of a shared task",
    )
    @app_commands.describe(task_id="รหัสงาน / Task ID")
    @rate_limit_check("command")
    async def assign_signoff_cmd(self, interaction: discord.Interaction, task_id: int) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)

        actor_roles = [r.id for r in getattr(interaction.user, "roles", [])]
        summary_pre = await service.get_assignment_summary(task_id)
        role_members = _resolve_role_member_ids(interaction.guild, summary_pre.role_ids)
        task_row = await service._fetch_task_row(task_id)
        is_owner = str(task_row["owner_id"]) == uid
        is_assigned = await service.is_user_assigned_to_task(task_id, uid, actor_roles)
        if not (is_owner or is_assigned):
            await interaction.followup.send(t("permission_denied", lang), ephemeral=True)
            return

        res = await service.handle_task_completion_attempt(
            task_id, uid, role_member_ids=role_members
        )
        if res.completed:
            await gamification_service.complete_personal_task(task_id, uid)
            await interaction.followup.send(
                f"✅ {t('assign_signoff_all_done', lang, task_id=task_id)}",
                ephemeral=True,
            )
        else:
            waiting = ", ".join(f"<@{u}>" for u in res.pending_users) or "—"
            msg = t(
                "assign_signoff_pending",
                lang,
                done=len(res.signed_users),
                total=len(res.signed_users) + len(res.pending_users),
                waiting=waiting,
            )
            await interaction.followup.send(f"✍️ {msg}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AssignmentsCog(bot))
