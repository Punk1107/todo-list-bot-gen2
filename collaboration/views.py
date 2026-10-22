"""
collaboration/views.py — Discord UI Views, Modals, and Dropdowns for Shared Projects

Components:
  - CreateProjectModal     : form for creating a new shared project
  - ProjectDashboardView   : project dashboard with navigation tabs
  - ProjectBoardView       : kanban board with column switcher + claim buttons
  - ClaimConfirmView       : confirmation before claiming a task
  - AddProjectTaskModal    : form for adding a task to a project
  - MembersView            : paginated members list with role management
  - ActivityView           : recent activity feed display
  - ProjectSelectDropdown  : guild project switcher
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import ui
import pytz

from collaboration import service
from collaboration.models import BoardData, Project, ProjectMember, ProjectStats, ProjectTask, ProjectActivity
from locales.i18n import t
from utils.helpers import get_user_lang, get_user_timezone, ensure_user, format_deadline, time_left_str

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Embed builders
# ─────────────────────────────────────────────────────────────────────────────

def _progress_bar(pct: float, width: int = 14) -> str:
    filled = int(round(pct / 100 * width))
    bar = "▰" * filled + "▱" * (width - filled)
    return f"`{bar}` **{pct:.1f}%**"


def build_project_list_embed(projects: list[Project], guild_name: str, lang: str) -> discord.Embed:
    embed = discord.Embed(
        title=t("proj_list_title", lang, guild=guild_name),
        color=0x5865F2,
    )
    if not projects:
        embed.description = f"> {t('proj_list_empty', lang)}"
        return embed
    lines = []
    for p in projects:
        lines.append(
            f"{p.status_emoji} {p.priority_emoji} {p.emoji} **{p.name}** `#{p.project_id}`\n"
            f"   ╰ {p.description[:60] + '…' if p.description and len(p.description) > 60 else (p.description or '—')}"
        )
    embed.description = "\n".join(lines)
    embed.set_footer(text=t("proj_footer", lang, count=len(projects)))
    return embed


class ProjectSelectDropdown(ui.Select):
    """Dropdown for choosing a project from the project list."""

    def __init__(self, projects: list[Project], uid: str, lang: str) -> None:
        self.uid  = uid
        self.lang = lang
        options = [
            discord.SelectOption(
                label=f"#{p.project_id} {p.name[:40]}",
                value=str(p.project_id),
                description=p.description[:50] if p.description else "",
            )
            for p in projects[:25]
        ]
        if not options:
            options = [discord.SelectOption(label=t("quickaction_none", lang), value="0")]
        placeholder = t("proj_select_dashboard_placeholder", lang)
        super().__init__(
            placeholder=placeholder,
            options=options,
            min_values=1, max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        proj_id_str = self.values[0]
        if proj_id_str == "0":
            return
        proj_id = int(proj_id_str)
        guild_id = str(interaction.guild_id) if interaction.guild_id else ""
        from collaboration import service
        try:
            stats = await service.get_project_stats(proj_id, guild_id)
        except Exception:
            await interaction.response.send_message(
                t("proj_not_found", self.lang, project_id=proj_id), ephemeral=True
            )
            return

        embed = build_project_dashboard_embed(stats, self.lang)
        view  = ProjectDashboardView(proj_id, guild_id, self.lang, interaction.user)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ProjectListView(ui.View):
    """Interactive view for /project list with project select dropdown."""

    def __init__(self, projects: list[Project], uid: str, lang: str) -> None:
        super().__init__(timeout=300)
        self.uid = uid
        self.lang = lang
        if projects:
            self.add_item(ProjectSelectDropdown(projects, uid, lang))


def build_project_dashboard_embed(stats: ProjectStats, lang: str) -> discord.Embed:
    p = stats.project
    color = int(p.color.lstrip("#"), 16) if p.color.startswith("#") else 0x5865F2
    embed = discord.Embed(
        title=f"{p.emoji} {p.name}",
        description=p.description or "",
        color=color,
    )
    embed.add_field(
        name=t("proj_progress", lang),
        value=_progress_bar(stats.progress_pct),
        inline=False,
    )
    embed.add_field(name=f"📋 {t('proj_pending', lang)}",    value=str(stats.pending),     inline=True)
    embed.add_field(name=f"⚡ {t('proj_in_progress', lang)}",value=str(stats.in_progress), inline=True)
    embed.add_field(name=f"✅ {t('proj_completed', lang)}",  value=str(stats.completed),   inline=True)
    if stats.overdue:
        embed.add_field(name=f"🚨 {t('proj_overdue', lang)}", value=str(stats.overdue), inline=True)
    embed.add_field(name=f"👥 {t('proj_members', lang)}", value=str(stats.members), inline=True)
    embed.add_field(name=f"📊 {t('proj_status_label', lang)}", value=p.status_emoji + " " + p.status.capitalize(), inline=True)
    embed.add_field(name=f"🎯 {t('proj_priority_label', lang)}", value=f"{p.priority_emoji} {t(f'priority_{p.priority}', lang)} (P{p.priority})", inline=True)

    if stats.leaderboard:
        lb_lines = []
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, (uid, count) in enumerate(stats.leaderboard):
            medal = medals[i] if i < len(medals) else "▫️"
            lb_lines.append(f"{medal} <@{uid}> — **{count}** {t('proj_lb_tasks', lang)}")
        embed.add_field(name=f"🏆 {t('proj_leaderboard', lang)}", value="\n".join(lb_lines), inline=False)

    embed.set_footer(text=t("proj_footer_id", lang, project_id=p.project_id))
    return embed


def build_board_embed(board: BoardData, lang: str, column: str = "pending") -> discord.Embed:
    """Build Kanban board embed for a specific column."""
    p = board.project
    color = int(p.color.lstrip("#"), 16) if p.color.startswith("#") else 0x5865F2

    column_map = {
        "pending":     (board.pending,     "📋", t("proj_pending", lang)),
        "in_progress": (board.in_progress, "⚡", t("proj_in_progress", lang)),
        "completed":   (board.completed,   "✅", t("proj_completed", lang)),
        "cancelled":   (board.cancelled,   "❌", t("proj_cancelled", lang)),
    }
    tasks, col_emoji, col_name = column_map.get(column, column_map["pending"])

    embed = discord.Embed(
        title=f"{p.emoji} {p.name} — {col_emoji} {col_name}",
        color=color,
    )
    embed.description = (
        f"{_progress_bar(board.progress_pct)}  "
        f"({board.done_count}/{board.total - len(board.cancelled)} {t('proj_tasks_done', lang)})"
    )

    if not tasks:
        embed.add_field(name="\u200b", value=f"> *{t('proj_board_empty_col', lang, column=col_name)}*", inline=False)
    else:
        for task in tasks[:8]:  # Discord embed limit: show up to 8 per column
            assignee_str = ""
            if task.assignees:
                assignee_str = "  👤 " + ", ".join(f"<@{u}>" for u in task.assignees[:3])
            if task.assigned_roles:
                role_mentions = ", ".join(f"<@&{role_id}>" for role_id in task.assigned_roles[:3])
                assignee_str += f"  🏷️ {role_mentions}"
            active_blockers = [
                f"#{blocker_id} {title[:35]}"
                for blocker_id, title, status in task.blocked_by
                if status != "Completed"
            ]
            blocker_str = f"\n⛔ Blocked by: {', '.join(active_blockers[:3])}" if active_blockers else ""
            deadline_str = format_deadline(task.deadline, "UTC") if task.deadline else "—"
            priv_badge = "🔒 " if task.is_private else ""
            embed.add_field(
                name=f"{priv_badge}{task.priority_emoji} `#{task.task_id}` {task.task[:55]}",
                value=(
                    f"📅 `{deadline_str}` · ⏱️ `{time_left_str(task.deadline)}`{assignee_str}{blocker_str}"
                ),
                inline=False,
            )
        if len(tasks) > 8:
            embed.set_footer(text=t("proj_board_more", lang, count=len(tasks) - 8))

    return embed


def build_activity_embed(activities: list[ProjectActivity], project: Project, lang: str) -> discord.Embed:
    color = int(project.color.lstrip("#"), 16) if project.color.startswith("#") else 0x5865F2
    embed = discord.Embed(
        title=f"{project.emoji} {project.name} — 📜 {t('proj_activity_title', lang)}",
        color=color,
    )
    if not activities:
        embed.description = f"> *{t('proj_activity_empty', lang)}*"
        return embed
    lines = []
    for act in activities[:15]:
        ts = act.created_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        discord_ts = f"<t:{int(ts.timestamp())}:R>"
        detail = f" — *{act.detail[:60]}*" if act.detail else ""
        lines.append(f"{act.action_emoji} <@{act.user_id}> `{act.action}`{detail}  {discord_ts}")
    embed.description = "\n".join(lines)
    return embed


def build_members_embed(members: list[ProjectMember], project: Project, lang: str) -> discord.Embed:
    color = int(project.color.lstrip("#"), 16) if project.color.startswith("#") else 0x5865F2
    embed = discord.Embed(
        title=f"{project.emoji} {project.name} — 👥 {t('proj_members_title', lang)}",
        color=color,
    )
    if not members:
        embed.description = f"> *{t('proj_members_empty', lang)}*"
        return embed
    lines = []
    for m in members:
        lines.append(f"{m.role_emoji} <@{m.user_id}> — **{m.role.capitalize()}**")
    embed.description = "\n".join(lines)
    embed.set_footer(text=t("proj_members_count", lang, count=len(members)))
    return embed


def build_my_tasks_embed(tasks: list[ProjectTask], lang: str, username: str) -> discord.Embed:
    embed = discord.Embed(
        title=t("proj_my_tasks_title", lang, user=username),
        color=0x5865F2,
    )
    if not tasks:
        embed.description = f"> {t('proj_my_tasks_empty', lang)}"
        return embed
    lines = []
    for task in tasks[:15]:
        dl = format_deadline(task.deadline, "UTC") if task.deadline else "—"
        tl = time_left_str(task.deadline) if task.deadline else ""
        lines.append(
            f"{task.status_emoji} `#{task.task_id}` **{task.task[:50]}**\n"
            f"   ╰ 📅 `{dl}`  ·  ⏱️ `{tl}`"
        )
    embed.description = "\n".join(lines)
    embed.set_footer(text=t("proj_my_tasks_footer", lang, count=len(tasks)))
    return embed


# ─────────────────────────────────────────────────────────────────────────────
# Modals
# ─────────────────────────────────────────────────────────────────────────────

class CreateProjectModal(ui.Modal):
    """Form for creating a new shared project in the current guild."""

    def __init__(self, lang: str, priority: int = 0) -> None:
        super().__init__(title=t("proj_create_modal_title", lang))
        self.lang = lang

        self.name = ui.TextInput(
            label=t("proj_name_label", lang),
            placeholder=t("proj_name_placeholder", lang),
            max_length=80, required=True,
        )
        self.description = ui.TextInput(
            label=t("proj_desc_label", lang),
            placeholder=t("proj_desc_placeholder", lang),
            style=discord.TextStyle.paragraph,
            max_length=500, required=False,
        )
        self.color = ui.TextInput(
            label=t("proj_color_label", lang),
            placeholder="#5865F2",
            max_length=7, required=False,
        )
        self.emoji_field = ui.TextInput(
            label=t("proj_emoji_label", lang),
            placeholder="📁",
            max_length=4, required=False,
        )
        self.priority = ui.TextInput(
            label=t("task_priority_label", lang),
            placeholder="0-7 (0=⬜, 1=🟦, 2=🟩, 3=🟨, 4=🟧, 5=🟥, 6=🔴, 7=🆘)",
            default=str(max(0, min(7, int(priority)))),
            max_length=1, required=False,
        )
        self.add_item(self.name)
        self.add_item(self.description)
        self.add_item(self.color)
        self.add_item(self.emoji_field)
        self.add_item(self.priority)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        lang = self.lang
        if not interaction.guild:
            await interaction.response.send_message(t("proj_guild_only", lang), ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        owner_id = str(interaction.user.id)
        name = self.name.value.strip()

        # Validate color
        color_val = self.color.value.strip() if self.color.value else "#5865F2"
        import re
        if color_val and not re.match(r"^#[0-9A-Fa-f]{6}$", color_val):
            color_val = "#5865F2"

        emoji_val = self.emoji_field.value.strip() if self.emoji_field.value else "📁"

        # Validate priority
        prio_val = 0
        if self.priority.value and self.priority.value.strip().isdigit():
            prio_val = max(0, min(7, int(self.priority.value.strip())))

        await ensure_user(owner_id, lang)
        try:
            project = await service.create_project(
                guild_id    = guild_id,
                name        = name,
                owner_id    = owner_id,
                description = self.description.value.strip() or None,
                color       = color_val,
                emoji       = emoji_val,
                priority    = prio_val,
            )
        except Exception as exc:
            log.error("CreateProjectModal error: %s", exc)
            await interaction.response.send_message(t("err_db", lang), ephemeral=True)
            return

        stats = await service.get_project_stats(project.project_id, guild_id)
        embed = build_project_dashboard_embed(stats, lang)
        view  = ProjectDashboardView(project.project_id, guild_id, lang, interaction.user)
        await interaction.response.send_message(
            t("proj_created_success", lang, name=name),
            embed=embed, view=view,
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.error("CreateProjectModal.on_error: %s", error, exc_info=True)
        lang = await get_user_lang(interaction.user.id)
        await interaction.response.send_message(t("err_generic", lang), ephemeral=True)


class AddProjectTaskModal(ui.Modal):
    """Form for adding a new task to a shared project."""

    def __init__(self, project: Project, lang: str, priority: int = 0, is_private: bool = False) -> None:
        super().__init__(title=t("proj_add_task_modal_title", lang, name=project.name[:30]))
        self.project = project
        self.lang    = lang
        self.is_private = is_private

        self.task_name = ui.TextInput(
            label=t("task_name_label", lang),
            placeholder=t("task_name_placeholder", lang),
            max_length=200, required=True,
        )
        self.deadline = ui.TextInput(
            label=t("task_deadline_label", lang),
            placeholder=t("task_deadline_placeholder", lang),
            max_length=50, required=True,
        )
        self.description_field = ui.TextInput(
            label=t("task_desc_label", lang),
            placeholder=t("task_desc_placeholder", lang),
            style=discord.TextStyle.paragraph,
            max_length=500, required=False,
        )
        self.priority = ui.TextInput(
            label=t("task_priority_label", lang),
            placeholder="0-7 (0=⬜, 1=🟦, 2=🟩, 3=🟨, 4=🟧, 5=🟥, 6=🔴, 7=🆘)",
            default=str(max(0, min(7, int(priority)))),
            max_length=1, required=False,
        )
        self.add_item(self.task_name)
        self.add_item(self.deadline)
        self.add_item(self.description_field)
        self.add_item(self.priority)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        lang = self.lang
        from utils.helpers import parse_deadline, get_user_timezone
        from utils.conflict_resolver import validate_deadline_defensive, DeadlineValidationError

        uid     = str(interaction.user.id)
        tz_name = await get_user_timezone(uid)

        try:
            dt = validate_deadline_defensive(self.deadline.value, tz_name)
        except DeadlineValidationError as e:
            await interaction.response.send_message(t(e.i18n_key, lang, **e.kwargs), ephemeral=True)
            return

        prio_val = 0
        if self.priority.value and self.priority.value.strip().isdigit():
            prio_val = max(0, min(7, int(self.priority.value.strip())))

        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        try:
            task = await service.add_project_task(
                project_id  = self.project.project_id,
                guild_id    = self.project.guild_id,
                task_name   = self.task_name.value.strip(),
                deadline_iso= dt.isoformat(),
                creator_id  = uid,
                priority    = prio_val,
                description = self.description_field.value.strip() or None,
                is_private  = self.is_private,
                is_guild_admin = is_admin,
            )
        except service.ProjectPermissionError:
            await interaction.response.send_message(t("proj_no_permission", lang), ephemeral=True)
            return
        except Exception as exc:
            log.error("AddProjectTaskModal error: %s", exc)
            await interaction.response.send_message(t("err_db", lang), ephemeral=True)
            return

        embed = discord.Embed(
            title=t("proj_task_added", lang, task_id=task.task_id, name=task.task[:60]),
            color=0x57F287,
        )
        embed.set_footer(text=f"{self.project.emoji} {self.project.name}")
        view = ProjectDashboardView(self.project.project_id, self.project.guild_id, lang, interaction.user)
        await interaction.response.send_message(embed=embed, view=view)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        lang = self.lang
        await interaction.response.send_message(t("err_generic", lang), ephemeral=True)


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

async def _register_live_dashboard(
    view: "ProjectDashboardView",
    interaction: discord.Interaction,
) -> None:
    """
    Register the interaction message as the live dashboard for this project.
    Called after every Dashboard tab click so the Realtime listener can
    auto-update it in-place without user having to re-run /project view.
    """
    try:
        msg = await interaction.original_response()
        view._message = msg
        from realtime.dashboard_tracker import dashboard_tracker
        dashboard_tracker.register(
            project_id=view.project_id,
            guild_id=view.guild_id,
            channel_id=msg.channel.id,
            message_id=msg.id,
            lang=view.lang,
        )
        await dashboard_tracker.persist(view.project_id)
    except Exception as exc:
        log.debug("Could not register live dashboard (non-fatal): %s", exc)


class AdvanceProgressSelect(ui.Select):
    """Dropdown for choosing an active task to mark as Completed to advance project progress."""

    def __init__(
        self,
        project_id: int,
        guild_id: str,
        lang: str,
        tasks: list[ProjectTask],
        parent_dashboard_view: Optional["ProjectDashboardView"] = None,
    ) -> None:
        self.project_id = project_id
        self.guild_id   = guild_id
        self.lang       = lang
        self.parent_dashboard_view = parent_dashboard_view
        options = [
            discord.SelectOption(
                label=f"#{tk.task_id} {tk.task[:70]}",
                value=str(tk.task_id),
                description=f"[{tk.status}] " + (f"📅 {format_deadline(tk.deadline, 'UTC')}" if tk.deadline else ""),
                emoji="⚡" if tk.status == "In_Progress" else "📋",
            )
            for tk in tasks[:25]
        ]
        super().__init__(placeholder=t("proj_advance_select_placeholder", lang), options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        lang     = self.lang
        task_id  = int(self.values[0])
        uid      = str(interaction.user.id)
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        await interaction.response.defer(ephemeral=True)
        try:
            task = await service.update_task_status(
                task_id, self.project_id, self.guild_id,
                "Completed", uid, is_guild_admin=is_admin,
                actor_role_ids=[
                    role.id for role in interaction.user.roles
                ] if isinstance(interaction.user, discord.Member) else [],
            )
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=self.project_id), ephemeral=True)
            return
        except service.TaskNotFound:
            await interaction.followup.send(t("proj_task_not_found", lang, task_id=task_id), ephemeral=True)
            return
        except service.ProjectPermissionError:
            await interaction.followup.send(t("proj_no_permission", lang), ephemeral=True)
            return
        except service.TaskBlocked as exc:
            blockers = ", ".join(f"#{blocker_id} {name}" for blocker_id, name in exc.blockers)
            await interaction.followup.send(
                t("proj_task_blocked", lang, blockers=blockers), ephemeral=True
            )
            return
        except Exception as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        stats = await service.get_project_stats(self.project_id, self.guild_id)
        embed = discord.Embed(
            title=f"📈 {t('proj_advance_select_title', lang)}",
            description=t("proj_advance_success", lang, task_id=task.task_id) + f"\n\n{_progress_bar(stats.progress_pct)}",
            color=0x57F287,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        if self.parent_dashboard_view and getattr(self.parent_dashboard_view, "_message", None):
            try:
                new_dash_embed = build_project_dashboard_embed(stats, self.lang)
                await self.parent_dashboard_view._message.edit(embed=new_dash_embed, view=self.parent_dashboard_view)
            except Exception:
                pass


class AdvanceProgressSelectView(ui.View):
    """View containing the task selection dropdown to advance progress."""

    def __init__(
        self,
        project_id: int,
        guild_id: str,
        lang: str,
        tasks: list[ProjectTask],
        parent_dashboard_view: Optional["ProjectDashboardView"] = None,
    ) -> None:
        super().__init__(timeout=120)
        self.add_item(AdvanceProgressSelect(project_id, guild_id, lang, tasks, parent_dashboard_view=parent_dashboard_view))


class ManualProgressModal(ui.Modal):
    """Modal for entering a manual progress percentage for a project."""

    def __init__(
        self,
        project_id: int,
        guild_id: str,
        lang: str,
        parent_dashboard_view: Optional["ProjectDashboardView"] = None,
    ) -> None:
        super().__init__(title=t("proj_manual_progress_modal_title", lang))
        self.project_id = project_id
        self.guild_id   = guild_id
        self.lang       = lang
        self.parent_dashboard_view = parent_dashboard_view

        self.progress_input = ui.TextInput(
            label=t("proj_manual_progress_input_label", lang),
            placeholder="0 - 100",
            max_length=3,
            required=True,
        )
        self.add_item(self.progress_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        val_str = self.progress_input.value.strip()
        if not val_str.isdigit() or not (0 <= int(val_str) <= 100):
            await interaction.response.send_message(t("err_generic", self.lang), ephemeral=True)
            return

        prog = int(val_str)
        uid = str(interaction.user.id)
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        try:
            await service.update_project_manual_progress(self.project_id, self.guild_id, prog, uid, is_guild_admin=is_admin)
        except Exception as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        stats = await service.get_project_stats(self.project_id, self.guild_id)
        await interaction.response.send_message(
            t("proj_manual_progress_updated", self.lang, progress=prog) + f"\n\n{_progress_bar(stats.progress_pct)}",
            ephemeral=True,
        )
        if self.parent_dashboard_view and getattr(self.parent_dashboard_view, "_message", None):
            try:
                new_dash_embed = build_project_dashboard_embed(stats, self.lang)
                await self.parent_dashboard_view._message.edit(embed=new_dash_embed, view=self.parent_dashboard_view)
            except Exception:
                pass


class ManualProgressView(ui.View):
    """Buttons to advance project progress when no tasks exist."""

    def __init__(
        self,
        project_id: int,
        guild_id: str,
        lang: str,
        parent_dashboard_view: Optional["ProjectDashboardView"] = None,
    ) -> None:
        super().__init__(timeout=120)
        self.project_id = project_id
        self.guild_id   = guild_id
        self.lang       = lang
        self.parent_dashboard_view = parent_dashboard_view

    async def _set_pct(self, interaction: discord.Interaction, pct: int) -> None:
        uid = str(interaction.user.id)
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        try:
            await service.update_project_manual_progress(self.project_id, self.guild_id, pct, uid, is_guild_admin=is_admin)
        except Exception as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        stats = await service.get_project_stats(self.project_id, self.guild_id)
        await interaction.response.send_message(
            t("proj_manual_progress_updated", self.lang, progress=pct) + f"\n\n{_progress_bar(stats.progress_pct)}",
            ephemeral=True,
        )
        if self.parent_dashboard_view and getattr(self.parent_dashboard_view, "_message", None):
            try:
                new_dash_embed = build_project_dashboard_embed(stats, self.lang)
                await self.parent_dashboard_view._message.edit(embed=new_dash_embed, view=self.parent_dashboard_view)
            except Exception:
                pass

    @ui.button(label="+10%", style=discord.ButtonStyle.secondary)
    async def btn_p10(self, interaction: discord.Interaction, button: ui.Button) -> None:
        stats = await service.get_project_stats(self.project_id, self.guild_id)
        new_val = min(100, int(stats.progress_pct) + 10)
        await self._set_pct(interaction, new_val)

    @ui.button(label="+25%", style=discord.ButtonStyle.secondary)
    async def btn_p25(self, interaction: discord.Interaction, button: ui.Button) -> None:
        stats = await service.get_project_stats(self.project_id, self.guild_id)
        new_val = min(100, int(stats.progress_pct) + 25)
        await self._set_pct(interaction, new_val)

    @ui.button(label="+50%", style=discord.ButtonStyle.secondary)
    async def btn_p50(self, interaction: discord.Interaction, button: ui.Button) -> None:
        stats = await service.get_project_stats(self.project_id, self.guild_id)
        new_val = min(100, int(stats.progress_pct) + 50)
        await self._set_pct(interaction, new_val)

    @ui.button(label="100% (Done)", style=discord.ButtonStyle.success)
    async def btn_100(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._set_pct(interaction, 100)

    @ui.button(label="✏️ Custom %", style=discord.ButtonStyle.primary)
    async def btn_custom(self, interaction: discord.Interaction, button: ui.Button) -> None:
        modal = ManualProgressModal(self.project_id, self.guild_id, self.lang, parent_dashboard_view=self.parent_dashboard_view)
        await interaction.response.send_modal(modal)


class ProjectCompleteConfirmView(ui.View):
    """Confirmation view before completing a project."""

    def __init__(
        self,
        project_id: int,
        guild_id: str,
        lang: str,
        project: Project,
        parent_dashboard_view: Optional["ProjectDashboardView"] = None,
    ) -> None:
        super().__init__(timeout=60)
        self.project_id = project_id
        self.guild_id   = guild_id
        self.lang       = lang
        self.project    = project
        self.parent_dashboard_view = parent_dashboard_view

        self.btn_complete_all.label = t("proj_complete_all_btn", lang)
        self.btn_complete_only.label = t("proj_complete_status_only_btn", lang)
        self.btn_cancel.label = t("cancel", lang)

    @ui.button(label="✅ Complete Project & All Tasks", style=discord.ButtonStyle.success)
    async def btn_complete_all(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        uid = str(interaction.user.id)
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        try:
            await service.complete_project_with_tasks(self.project_id, self.guild_id, uid, complete_all_tasks=True, is_guild_admin=is_admin)
        except Exception as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        self.stop()
        embed = discord.Embed(
            title=t("proj_completed_success", self.lang, name=self.project.name),
            color=0x57F287,
        )
        embed.set_footer(text=t("proj_footer_id", self.lang, project_id=self.project_id))
        await interaction.followup.send(embed=embed, ephemeral=True)

        # Broadcast celebratory message to Discord channel and DM all project stakeholders
        asyncio.create_task(
            service.notify_project_completed(
                bot=interaction.client,
                project=self.project,
                actor=interaction.user,
                guild=interaction.guild,
                trigger_channel=interaction.channel,
                complete_all_tasks=True,
            )
        )

        if self.parent_dashboard_view and getattr(self.parent_dashboard_view, "_message", None):
            try:
                stats = await service.get_project_stats(self.project_id, self.guild_id)
                new_dash_embed = build_project_dashboard_embed(stats, self.lang)
                await self.parent_dashboard_view._message.edit(embed=new_dash_embed, view=self.parent_dashboard_view)
            except Exception:
                pass

    @ui.button(label="🏁 Complete Project Only", style=discord.ButtonStyle.primary)
    async def btn_complete_only(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        uid = str(interaction.user.id)
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        try:
            await service.complete_project_with_tasks(self.project_id, self.guild_id, uid, complete_all_tasks=False, is_guild_admin=is_admin)
        except Exception as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        self.stop()
        embed = discord.Embed(
            title=t("proj_completed_success", self.lang, name=self.project.name),
            color=0x57F287,
        )
        embed.set_footer(text=t("proj_footer_id", self.lang, project_id=self.project_id))
        await interaction.followup.send(embed=embed, ephemeral=True)

        # Broadcast celebratory message to Discord channel and DM all project stakeholders
        asyncio.create_task(
            service.notify_project_completed(
                bot=interaction.client,
                project=self.project,
                actor=interaction.user,
                guild=interaction.guild,
                trigger_channel=interaction.channel,
                complete_all_tasks=False,
            )
        )

        if self.parent_dashboard_view and getattr(self.parent_dashboard_view, "_message", None):
            try:
                stats = await service.get_project_stats(self.project_id, self.guild_id)
                new_dash_embed = build_project_dashboard_embed(stats, self.lang)
                await self.parent_dashboard_view._message.edit(embed=new_dash_embed, view=self.parent_dashboard_view)
            except Exception:
                pass

    @ui.button(label="✖ Cancel", style=discord.ButtonStyle.secondary)
    async def btn_cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content=t("cancel", self.lang), embed=None, view=None)


class ProjectPrioritySelect(ui.Select):
    """Dropdown for changing a project's priority (0-7)."""

    def __init__(
        self,
        project_id: int,
        guild_id: str,
        lang: str,
        current_priority: int = 0,
        parent_dashboard_view: Optional["ProjectDashboardView"] = None,
    ) -> None:
        self.project_id = project_id
        self.guild_id   = guild_id
        self.lang       = lang
        self.parent_dashboard_view = parent_dashboard_view

        options = [
            discord.SelectOption(
                label=f"{emoji} {t(f'priority_{v}', lang)} (P{v})",
                value=str(v),
                default=(v == current_priority),
            )
            for v, emoji in [
                (0, "⬜"),
                (1, "🟦"),
                (2, "🟩"),
                (3, "🟨"),
                (4, "🟧"),
                (5, "🟥"),
                (6, "🔴"),
                (7, "🆘"),
            ]
        ]
        super().__init__(
            placeholder=t("proj_priority_select_placeholder", lang),
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        new_prio = int(self.values[0])
        uid = str(interaction.user.id)
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        try:
            updated = await service.update_project_priority(
                self.project_id, self.guild_id, new_prio, uid, is_guild_admin=is_admin
            )
        except Exception as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        prio_text = f"{updated.priority_emoji} {t(f'priority_{updated.priority}', self.lang)} (P{updated.priority})"
        await interaction.followup.send(
            t("proj_priority_updated", self.lang, priority=prio_text),
            ephemeral=True,
        )

        if self.parent_dashboard_view and getattr(self.parent_dashboard_view, "_message", None):
            try:
                stats = await service.get_project_stats(self.project_id, self.guild_id)
                new_dash_embed = build_project_dashboard_embed(stats, self.lang)
                await self.parent_dashboard_view._message.edit(embed=new_dash_embed, view=self.parent_dashboard_view)
            except Exception:
                pass


class ProjectPrioritySelectView(ui.View):
    """View containing the project priority select dropdown."""

    def __init__(
        self,
        project_id: int,
        guild_id: str,
        lang: str,
        current_priority: int = 0,
        parent_dashboard_view: Optional["ProjectDashboardView"] = None,
    ) -> None:
        super().__init__(timeout=120)
        self.add_item(ProjectPrioritySelect(project_id, guild_id, lang, current_priority, parent_dashboard_view=parent_dashboard_view))


class ProjectDashboardView(ui.View):
    """Main project dashboard with navigation and action buttons."""

    def __init__(
        self,
        project_id: int,
        guild_id: str,
        lang: str,
        user: Optional[discord.User | discord.Member],
    ) -> None:
        super().__init__(timeout=300)
        self.project_id = project_id
        self.guild_id   = guild_id
        self.lang       = lang
        self.user       = user
        self._message: Optional[discord.Message] = None

        # Localize button labels after init
        self.btn_dashboard.label = t("proj_btn_dashboard", lang)
        self.btn_board.label     = t("proj_btn_board",     lang)
        self.btn_members.label   = t("proj_btn_members",   lang)
        self.btn_activity.label  = t("proj_btn_activity",  lang)
        self.btn_files.label     = t("proj_btn_files",     lang)

        self.btn_add_task.label  = t("proj_btn_add_task",  lang)
        self.btn_advance.label   = t("proj_btn_advance_progress", lang)
        self.btn_complete.label  = t("proj_btn_complete_project", lang)
        self.btn_priority.label  = t("proj_btn_change_priority",  lang)

    @ui.button(label="📊 Dashboard", style=discord.ButtonStyle.primary, custom_id="proj_dash_dashboard", row=0)
    async def btn_dashboard(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        await interaction.response.defer()
        try:
            stats = await service.get_project_stats(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=self.project_id), ephemeral=True)
            return
        embed = build_project_dashboard_embed(stats, lang)
        self._message = interaction.message
        await interaction.message.edit(embed=embed, view=self)
        await _register_live_dashboard(self, interaction)

    @ui.button(label="📋 Board", style=discord.ButtonStyle.secondary, custom_id="proj_dash_board", row=0)
    async def btn_board(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        await interaction.response.defer()
        try:
            board = await service.get_project_board(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=self.project_id), ephemeral=True)
            return
        embed = build_board_embed(board, lang, "pending")
        view  = ProjectBoardView(self.project_id, self.guild_id, lang, self.user, board)
        view._message = interaction.message
        await interaction.message.edit(embed=embed, view=view)

    @ui.button(label="👥 Members", style=discord.ButtonStyle.secondary, custom_id="proj_dash_members", row=0)
    async def btn_members(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        await interaction.response.defer()
        try:
            project = await service.get_project(self.project_id, self.guild_id)
            members = await service.get_project_members(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=self.project_id), ephemeral=True)
            return
        embed = build_members_embed(members, project, lang)
        view  = MembersView(project, lang, self.user, members)
        view._message = interaction.message
        await interaction.message.edit(embed=embed, view=view)

    @ui.button(label="📜 Activity", style=discord.ButtonStyle.secondary, custom_id="proj_dash_activity", row=0)
    async def btn_activity(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        await interaction.response.defer()
        try:
            project    = await service.get_project(self.project_id, self.guild_id)
            activities = await service.get_project_activity(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=self.project_id), ephemeral=True)
            return
        embed = build_activity_embed(activities, project, lang)
        self._message = interaction.message
        await interaction.message.edit(embed=embed, view=self)

    @ui.button(label="📎 Files", style=discord.ButtonStyle.secondary, custom_id="proj_dash_files", row=0)
    async def btn_files(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Show attachments across all project tasks."""
        lang = self.lang
        await interaction.response.defer(ephemeral=True)
        from storage import service as storage_svc
        from core.config import config as bot_config
        if not bot_config.storage.enabled:
            await interaction.followup.send(t("storage_disabled", lang), ephemeral=True)
            return
        from core.database import db
        att_rows = await db.fetchall(
            """SELECT * FROM task_attachments
                WHERE project_id=$1
                ORDER BY created_at DESC""",
            (self.project_id,),
        )
        if not att_rows:
            await interaction.followup.send(t("storage_no_attachments", lang), ephemeral=True)
            return
        from storage.models import TaskAttachment
        all_attachments = [TaskAttachment.from_record(r) for r in att_rows]
        from storage.views import build_attachments_embed, TaskAttachmentsView
        uid = str(interaction.user.id) if interaction.user else ""
        embed = build_attachments_embed(
            task_id=self.project_id,
            task_name=f"Project #{self.project_id} — All Files",
            attachments=all_attachments,
            lang=lang,
        )
        view = TaskAttachmentsView(
            task_id=self.project_id,
            task_name="",
            attachments=all_attachments,
            uid=uid,
            lang=lang,
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @ui.button(label="➕ Add Task", style=discord.ButtonStyle.secondary, custom_id="proj_dash_add_task", row=1)
    async def btn_add_task(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        try:
            project = await service.get_project(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.response.send_message(t("proj_not_found", lang, project_id=self.project_id), ephemeral=True)
            return
        modal = AddProjectTaskModal(project, lang)
        await interaction.response.send_modal(modal)

    @ui.button(label="📈 Advance Progress", style=discord.ButtonStyle.primary, custom_id="proj_dash_advance", row=1)
    async def btn_advance(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        await interaction.response.defer(ephemeral=True)
        try:
            board = await service.get_project_board(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=self.project_id), ephemeral=True)
            return

        actor_id = str(interaction.user.id)
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        role = await service.get_member_role(self.project_id, actor_id)
        if not (role is not None or is_admin):
            await interaction.followup.send(t("proj_no_permission", lang), ephemeral=True)
            return

        completable = board.in_progress + board.pending
        if completable:
            self._message = interaction.message
            view = AdvanceProgressSelectView(self.project_id, self.guild_id, lang, completable, parent_dashboard_view=self)
            embed = discord.Embed(
                title=f"📈 {t('proj_advance_select_title', lang)}",
                description=t("proj_advance_select_desc", lang),
                color=0x5865F2,
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            self._message = interaction.message
            view = ManualProgressView(self.project_id, self.guild_id, lang, parent_dashboard_view=self)
            embed = discord.Embed(
                title=f"📈 {t('proj_advance_select_title', lang)}",
                description=t("proj_manual_progress_desc", lang),
                color=0x5865F2,
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @ui.button(label="🏁 Complete Project", style=discord.ButtonStyle.success, custom_id="proj_dash_complete", row=1)
    async def btn_complete(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        actor_id = str(interaction.user.id)
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        try:
            project = await service.get_project(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.response.send_message(t("proj_not_found", lang, project_id=self.project_id), ephemeral=True)
            return

        actor_role = await service.get_member_role(self.project_id, actor_id)
        is_lead = actor_role == "lead" or project.owner_id == actor_id
        if not (is_lead or is_admin):
            await interaction.response.send_message(t("proj_no_permission", lang), ephemeral=True)
            return

        if project.status == "completed":
            await interaction.response.send_message(t("proj_already_completed", lang), ephemeral=True)
            return

        self._message = interaction.message
        view = ProjectCompleteConfirmView(self.project_id, self.guild_id, lang, project, parent_dashboard_view=self)
        embed = discord.Embed(
            title=f"🏁 {t('proj_complete_confirm_title', lang)}",
            description=t("proj_complete_confirm_desc", lang, name=project.name),
            color=0x57F287,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @ui.button(label="🎯 Priority", style=discord.ButtonStyle.secondary, custom_id="proj_dash_priority", row=1)
    async def btn_priority(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        actor_id = str(interaction.user.id)
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        try:
            project = await service.get_project(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.response.send_message(t("proj_not_found", lang, project_id=self.project_id), ephemeral=True)
            return

        actor_role = await service.get_member_role(self.project_id, actor_id)
        is_lead = actor_role == "lead" or project.owner_id == actor_id
        if not (is_lead or is_admin):
            await interaction.response.send_message(t("proj_no_permission", lang), ephemeral=True)
            return

        self._message = interaction.message
        view = ProjectPrioritySelectView(self.project_id, self.guild_id, lang, project.priority, parent_dashboard_view=self)
        embed = discord.Embed(
            title=f"🎯 {t('proj_priority_select_title', lang)}",
            description=t("proj_priority_select_desc", lang, project=project.name, current=f"{project.priority_emoji} {t(f'priority_{project.priority}', lang)}"),
            color=0x5865F2,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @ui.button(label="🛡️ Permissions", style=discord.ButtonStyle.secondary, custom_id="proj_dash_perms", row=2)
    async def btn_permissions(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        actor_id = str(interaction.user.id)
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        try:
            project = await service.get_project(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.response.send_message(t("proj_not_found", lang, project_id=self.project_id), ephemeral=True)
            return

        actor_role = await service.get_member_role(self.project_id, actor_id)
        is_lead = actor_role == "lead" or project.owner_id == actor_id
        if not (is_lead or is_admin):
            await interaction.response.send_message(t("proj_no_permission", lang), ephemeral=True)
            return

        perms = await service.get_project_role_permissions(self.project_id, "member")
        embed = build_project_permissions_embed(project, "member", perms, lang)
        view = ProjectPermissionsView(project, lang, self.user, role="member", permissions=perms)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)



class BoardColumnSelect(ui.Select):
    """Dropdown to switch between Kanban columns."""

    def __init__(self, project_id: int, guild_id: str, lang: str, user: discord.User | discord.Member, board: BoardData, current: str = "pending") -> None:
        self.project_id = project_id
        self.guild_id   = guild_id
        self.lang       = lang
        self.user       = user
        self._board     = board
        options = [
            discord.SelectOption(label=f"📋 {t('proj_pending', lang)}     ({len(board.pending)})",     value="pending",     default=(current == "pending")),
            discord.SelectOption(label=f"⚡ {t('proj_in_progress', lang)} ({len(board.in_progress)})", value="in_progress", default=(current == "in_progress")),
            discord.SelectOption(label=f"✅ {t('proj_completed', lang)}   ({len(board.completed)})",   value="completed",   default=(current == "completed")),
            discord.SelectOption(label=f"❌ {t('proj_cancelled', lang)}   ({len(board.cancelled)})",   value="cancelled",   default=(current == "cancelled")),
        ]
        super().__init__(placeholder=t("proj_board_select_col", lang), options=options, custom_id="board_col_select")

    async def callback(self, interaction: discord.Interaction) -> None:
        col = self.values[0]
        await interaction.response.defer()
        actor_id = str(interaction.user.id)
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        try:
            board = await service.get_project_board(self.project_id, self.guild_id, actor_id=actor_id, is_guild_admin=is_admin)
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", self.lang, project_id=self.project_id), ephemeral=True)
            return
        embed = build_board_embed(board, self.lang, col)
        view  = ProjectBoardView(self.project_id, self.guild_id, self.lang, self.user, board, current_col=col)
        await interaction.message.edit(embed=embed, view=view)


class TaskDiscussionView(ui.View):
    """Choose an active project task and create its public/private thread."""

    def __init__(
        self,
        project_id: int,
        guild_id: str,
        lang: str,
        uid: str,
        tasks: list[ProjectTask],
    ) -> None:
        super().__init__(timeout=120)
        self.project_id = project_id
        self.guild_id = guild_id
        self.lang = lang
        self.uid = uid
        self.selected_task_id: Optional[int] = None
        self.public_thread.label = t("proj_thread_public_button", lang)
        self.private_thread.label = t("proj_thread_private_button", lang)
        options = [
            discord.SelectOption(
                label=f"#{task.task_id} · {task.task[:75]}",
                value=str(task.task_id),
                description=task.status[:100],
            )
            for task in tasks[:25]
        ]
        self.add_item(ui.Select(
            placeholder=t("proj_thread_select_task", lang),
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        ))
        self.children[0].callback = self._select_task  # type: ignore[method-assign]

    async def _select_task(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.uid:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        select = self.children[0]
        self.selected_task_id = int(select.values[0])  # type: ignore[attr-defined]
        await interaction.response.edit_message(
            content=t("proj_thread_selected", self.lang, task_id=self.selected_task_id),
            view=self,
        )

    async def _create_thread(
        self, interaction: discord.Interaction, thread_type: str
    ) -> None:
        if str(interaction.user.id) != self.uid:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        if self.selected_task_id is None:
            await interaction.response.send_message(t("proj_thread_select_first", self.lang), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        actor_id = str(interaction.user.id)
        is_admin = (
            isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.administrator
        )
        created_thread: Optional[discord.Thread] = None
        starter: Optional[discord.Message] = None
        reserved = False
        try:
            project = await service.get_project(self.project_id, self.guild_id)
            await service.require_role(project, actor_id, "member", is_admin)
            task = await service.get_project_task(
                self.selected_task_id, self.project_id, self.guild_id
            )
            channel_id = (
                project.channel_id
                or project.notification_channel_id
                or interaction.channel_id
            )
            channel = interaction.guild.get_channel(channel_id) if interaction.guild and channel_id else None
            if channel is None and channel_id:
                channel = await interaction.client.fetch_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                await interaction.followup.send(t("proj_thread_channel_required", self.lang), ephemeral=True)
                return
            if not interaction.guild or channel.guild.id != interaction.guild.id:
                await interaction.followup.send(t("proj_thread_channel_required", self.lang), ephemeral=True)
                return

            await service.reserve_project_task_thread(
                task.task_id,
                self.project_id,
                self.guild_id,
                thread_type,
                channel.id,
                actor_id,
            )
            reserved = True
            thread_name = f"#{task.task_id} {task.task}".replace("\n", " ")[:100]
            if thread_type == "public":
                starter = await channel.send(
                    t("proj_thread_starter", self.lang, task_id=task.task_id, task_name=task.task),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                created_thread = await channel.create_thread(
                    name=thread_name,
                    message=starter,
                    auto_archive_duration=1440,
                    reason=f"Project task discussion for #{task.task_id}",
                )
            else:
                created_thread = await channel.create_thread(
                    name=thread_name,
                    type=discord.ChannelType.private_thread,
                    invitable=False,
                    auto_archive_duration=1440,
                    reason=f"Project task discussion for #{task.task_id}",
                )
                member_ids = {member.user_id for member in await service.get_project_members(
                    self.project_id, self.guild_id
                )}
                member_ids.add(project.owner_id)
                for member_id in sorted(member_ids):
                    member = interaction.guild.get_member(int(member_id))
                    if member is None:
                        try:
                            member = await interaction.guild.fetch_member(int(member_id))
                        except discord.NotFound:
                            continue
                    await created_thread.add_user(member)

            await service.complete_project_task_thread(
                task.task_id, self.project_id, self.guild_id, created_thread.id
            )
            reserved = False
            await interaction.followup.send(
                t("proj_thread_created", self.lang, url=created_thread.mention),
                ephemeral=True,
            )
            self.stop()
        except service.ProjectPermissionError:
            await interaction.followup.send(t("proj_no_permission", self.lang), ephemeral=True)
        except service.ProjectNotFound:
            await interaction.followup.send(
                t("proj_not_found", self.lang, project_id=self.project_id), ephemeral=True
            )
        except service.TaskNotFound:
            await interaction.followup.send(
                t("proj_task_not_found", self.lang, task_id=self.selected_task_id), ephemeral=True
            )
        except service.TaskThreadExists as exc:
            await interaction.followup.send(
                t(
                    "proj_thread_exists", self.lang,
                    url=f"https://discord.com/channels/{self.guild_id}/{exc}",
                ),
                ephemeral=True,
            )
        except service.TaskThreadPending:
            await interaction.followup.send(t("proj_thread_pending", self.lang), ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(t("proj_thread_permission_error", self.lang), ephemeral=True)
        except Exception as exc:
            log.exception(
                "Task discussion thread creation failed (project_id=%s task_id=%s)",
                self.project_id, self.selected_task_id,
            )
            await interaction.followup.send(t("err_generic", self.lang), ephemeral=True)
        finally:
            if reserved:
                if created_thread is not None:
                    try:
                        await created_thread.delete(reason="Thread mapping could not be saved")
                    except discord.HTTPException:
                        log.exception("Could not clean up unmapped project task thread")
                elif starter is not None:
                    try:
                        await starter.delete()
                    except discord.HTTPException:
                        log.exception("Could not clean up project task thread starter")
                try:
                    await service.release_project_task_thread_reservation(
                        self.selected_task_id, self.project_id, self.guild_id
                    )
                except Exception:
                    log.exception("Could not release project task thread reservation")

    @ui.button(label="🌐 Public Thread", style=discord.ButtonStyle.primary, row=1)
    async def public_thread(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._create_thread(interaction, "public")

    @ui.button(label="🔒 Private Thread", style=discord.ButtonStyle.secondary, row=1)
    async def private_thread(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._create_thread(interaction, "private")


class ProjectBoardView(ui.View):
    """Kanban board view with column switcher and Claim buttons."""

    def __init__(self, project_id: int, guild_id: str, lang: str,
                 user: discord.User | discord.Member, board: BoardData,
                 current_col: str = "pending") -> None:
        super().__init__(timeout=300)
        self.project_id  = project_id
        self.guild_id    = guild_id
        self.lang        = lang
        self.user        = user
        self.current_col = current_col
        self._board      = board

        # Column selector dropdown
        self.add_item(BoardColumnSelect(project_id, guild_id, lang, user, board, current_col))
        # Localize button labels
        self.btn_claim.label    = t("proj_btn_claim", lang)
        self.btn_complete.label = t("proj_btn_complete_task", lang)
        self.btn_back.label     = t("proj_btn_back",  lang)
        self.btn_thread.label   = t("proj_btn_thread", lang)

    @ui.button(label="🙋 Claim a Task", style=discord.ButtonStyle.success, custom_id="board_claim_btn", row=1)
    async def btn_claim(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        await interaction.response.defer(ephemeral=True)
        actor_id = str(interaction.user.id)
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        try:
            board = await service.get_project_board(self.project_id, self.guild_id, actor_id=actor_id, is_guild_admin=is_admin)
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=self.project_id), ephemeral=True)
            return

        # Show unclaimed pending tasks for selection
        claimable = [t_obj for t_obj in board.pending if not t_obj.assignees]
        if not claimable:
            await interaction.followup.send(t("proj_no_claimable", lang), ephemeral=True)
            return
        view = ClaimSelectView(self.project_id, self.guild_id, lang, claimable)
        embed = discord.Embed(
            title=t("proj_claim_select_title", lang),
            description=t("proj_claim_select_desc", lang),
            color=0x57F287,
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @ui.button(label="✅ Complete Task", style=discord.ButtonStyle.primary, custom_id="board_complete_btn", row=1)
    async def btn_complete(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        await interaction.response.defer(ephemeral=True)
        actor_id = str(interaction.user.id)
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        try:
            board = await service.get_project_board(self.project_id, self.guild_id, actor_id=actor_id, is_guild_admin=is_admin)
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=self.project_id), ephemeral=True)
            return

        # Permission check: Any member of the project can complete tasks!
        actor_id = str(interaction.user.id)
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        role = await service.get_member_role(self.project_id, actor_id)
        if not (role is not None or is_admin):
            await interaction.followup.send(t("proj_no_permission", lang), ephemeral=True)
            return

        # Active tasks (In Progress + Pending) that can be completed
        completable = board.in_progress + board.pending
        if not completable:
            await interaction.followup.send(t("proj_no_completable", lang), ephemeral=True)
            return

        view = CompleteTaskView(self.project_id, self.guild_id, lang, completable, parent_board_view=self)
        embed = discord.Embed(
            title=f"✅ {t('proj_complete_select_title', lang)}",
            description=t("proj_complete_select_desc", lang),
            color=0x57F287,
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @ui.button(label="⬅️ Dashboard", style=discord.ButtonStyle.secondary, custom_id="board_back_btn", row=1)
    async def btn_back(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer()
        try:
            stats = await service.get_project_stats(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", self.lang, project_id=self.project_id), ephemeral=True)
            return
        embed = build_project_dashboard_embed(stats, self.lang)
        view  = ProjectDashboardView(self.project_id, self.guild_id, self.lang, self.user)
        await interaction.message.edit(embed=embed, view=view)

    @ui.button(label="🧵 Task Thread", style=discord.ButtonStyle.secondary, custom_id="board_thread_btn", row=2)
    async def btn_thread(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        await interaction.response.defer(ephemeral=True)
        try:
            board = await service.get_project_board(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(
                t("proj_not_found", lang, project_id=self.project_id), ephemeral=True
            )
            return
        active_tasks = board.pending + board.in_progress
        if not active_tasks:
            await interaction.followup.send(t("proj_thread_no_tasks", lang), ephemeral=True)
            return
        view = TaskDiscussionView(
            self.project_id,
            self.guild_id,
            lang,
            str(interaction.user.id),
            active_tasks,
        )
        await interaction.followup.send(
            t("proj_thread_picker_description", lang),
            view=view,
            ephemeral=True,
        )


class ClaimTaskSelect(ui.Select):
    """Dropdown for selecting which task to claim."""

    def __init__(self, project_id: int, guild_id: str, lang: str, tasks: list[ProjectTask]) -> None:
        self.project_id = project_id
        self.guild_id   = guild_id
        self.lang       = lang
        options = [
            discord.SelectOption(
                label=f"#{tk.task_id} {tk.task[:80]}",
                value=str(tk.task_id),
                description=f"📅 {format_deadline(tk.deadline, 'UTC')}" if tk.deadline else "",
            )
            for tk in tasks[:25]
        ]
        super().__init__(placeholder=t("proj_claim_select_placeholder", lang), options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        lang    = self.lang
        task_id = int(self.values[0])
        uid     = str(interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        try:
            task = await service.claim_task(task_id, self.project_id, self.guild_id, uid)
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=self.project_id), ephemeral=True)
            return
        except service.TaskNotFound:
            await interaction.followup.send(t("proj_task_not_found", lang, task_id=task_id), ephemeral=True)
            return
        except service.TaskBlocked as exc:
            blockers = ", ".join(f"#{blocker_id} {name}" for blocker_id, name in exc.blockers)
            await interaction.followup.send(
                t("proj_task_blocked", lang, blockers=blockers), ephemeral=True
            )
            return
        except Exception as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        embed = discord.Embed(
            title=t("proj_claimed_title", lang),
            description=t("proj_claimed_desc", lang, task_id=task.task_id, name=task.task),
            color=0x57F287,
        )
        embed.set_footer(text=t("proj_claimed_footer", lang))
        await interaction.followup.send(embed=embed, ephemeral=True)


class ClaimSelectView(ui.View):
    """View containing the task selection dropdown for claiming."""
    def __init__(self, project_id: int, guild_id: str, lang: str, tasks: list[ProjectTask]) -> None:
        super().__init__(timeout=120)
        self.add_item(ClaimTaskSelect(project_id, guild_id, lang, tasks))


class CompleteTaskSelect(ui.Select):
    """Dropdown for selecting which task to mark as Completed."""

    def __init__(self, project_id: int, guild_id: str, lang: str, tasks: list[ProjectTask], parent_board_view: Optional[ProjectBoardView] = None) -> None:
        self.project_id = project_id
        self.guild_id   = guild_id
        self.lang       = lang
        self.parent_board_view = parent_board_view
        options = [
            discord.SelectOption(
                label=f"#{tk.task_id} {tk.task[:70]}",
                value=str(tk.task_id),
                description=f"[{tk.status}] " + (f"📅 {format_deadline(tk.deadline, 'UTC')}" if tk.deadline else ""),
                emoji="⚡" if tk.status == "In_Progress" else "📋",
            )
            for tk in tasks[:25]
        ]
        super().__init__(placeholder=t("proj_complete_select_placeholder", lang), options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        lang    = self.lang
        task_id = int(self.values[0])
        uid     = str(interaction.user.id)
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        await interaction.response.defer(ephemeral=True)
        try:
            task = await service.update_task_status(
                task_id, self.project_id, self.guild_id,
                "Completed", uid, is_guild_admin=is_admin,
                actor_role_ids=[
                    role.id for role in interaction.user.roles
                ] if isinstance(interaction.user, discord.Member) else [],
            )
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=self.project_id), ephemeral=True)
            return
        except service.TaskNotFound:
            await interaction.followup.send(t("proj_task_not_found", lang, task_id=task_id), ephemeral=True)
            return
        except service.ProjectPermissionError:
            await interaction.followup.send(t("proj_no_permission", lang), ephemeral=True)
            return
        except service.TaskBlocked as exc:
            blockers = ", ".join(f"#{blocker_id} {name}" for blocker_id, name in exc.blockers)
            await interaction.followup.send(
                t("proj_task_blocked", lang, blockers=blockers), ephemeral=True
            )
            return
        except Exception as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🎉 {t('proj_task_completed_title', lang)}",
            description=t(
                "proj_task_completed_desc", lang,
                user=interaction.user.mention, task_id=task.task_id, name=task.task
            ),
            color=0x57F287,
        )
        embed.set_footer(text=t("proj_task_completed_footer", lang))
        await interaction.followup.send(embed=embed, ephemeral=True)

        # Refresh Kanban board view in original message if available
        if self.parent_board_view and hasattr(self.parent_board_view, "_message") and self.parent_board_view._message:
            try:
                board = await service.get_project_board(self.project_id, self.guild_id)
                self.parent_board_view._board = board
                new_embed = build_board_embed(board, self.lang, self.parent_board_view.current_col)
                await self.parent_board_view._message.edit(embed=new_embed, view=self.parent_board_view)
            except Exception:
                pass


class CompleteTaskView(ui.View):
    """View containing the task selection dropdown for completing a task."""
    def __init__(self, project_id: int, guild_id: str, lang: str, tasks: list[ProjectTask], parent_board_view: Optional[ProjectBoardView] = None) -> None:
        super().__init__(timeout=120)
        self.add_item(CompleteTaskSelect(project_id, guild_id, lang, tasks, parent_board_view=parent_board_view))


class AddMemberSelect(ui.UserSelect):
    """User select dropdown to pick a member to add to the project."""

    def __init__(self, project: Project, lang: str, parent_view: Optional[MembersView] = None) -> None:
        super().__init__(
            placeholder=t("proj_add_member_select_placeholder", lang),
            min_values=1, max_values=1, custom_id="add_member_user_select"
        )
        self.project = project
        self.lang = lang
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        target_user = self.values[0]
        if target_user.bot:
            await interaction.followup.send(t("proj_member_bot_error", self.lang), ephemeral=True)
            return

        guild_id = str(interaction.guild.id) if interaction.guild else self.project.guild_id
        actor_id = str(interaction.user.id)
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator

        try:
            await service.add_member(
                self.project.project_id, guild_id,
                str(target_user.id), "member",
                actor_id, is_guild_admin=is_admin,
            )
        except Exception as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        # Send DM notification to the invited user
        guild_name = interaction.guild.name if interaction.guild else "Server"
        dm_sent = await service.send_project_invite_dm(
            target_user, self.project, guild_name, interaction.user, "member"
        )
        dm_status = t("proj_member_dm_sent", self.lang) if dm_sent else t("proj_member_dm_failed", self.lang)

        desc = t(
            "proj_member_added_desc", self.lang,
            user=target_user.mention,
            project=f"{self.project.emoji} {self.project.name}",
            role=t("proj_role_member", self.lang),
            dm_status=dm_status,
        )
        embed = discord.Embed(
            title=f"🎉 {t('proj_member_added_title', self.lang)}",
            description=desc,
            color=0x57F287,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        # Refresh members view in parent message if available
        if self.parent_view and hasattr(self.parent_view, "_message") and self.parent_view._message:
            try:
                updated_members = await service.get_project_members(self.project.project_id, guild_id)
                self.parent_view.members = updated_members
                new_embed = build_members_embed(updated_members, self.project, self.lang)
                await self.parent_view._message.edit(embed=new_embed, view=self.parent_view)
            except Exception:
                pass


class AddMemberView(ui.View):
    """View containing the AddMemberSelect dropdown."""

    def __init__(self, project: Project, lang: str, user: discord.User | discord.Member, parent_view: Optional[MembersView] = None) -> None:
        super().__init__(timeout=180)
        self.project = project
        self.lang = lang
        self.user = user
        self.add_item(AddMemberSelect(project, lang, parent_view=parent_view))


class MembersView(ui.View):
    """Members list with management options for the project lead."""

    def __init__(self, project: Project, lang: str, user: discord.User | discord.Member, members: list[ProjectMember]) -> None:
        super().__init__(timeout=300)
        self.project = project
        self.lang    = lang
        self.user    = user
        self.members = members
        self._message: Optional[discord.Message] = None
        # Localize button labels
        self.btn_add_member.label = t("proj_btn_add_member", lang)
        self.btn_back.label       = t("proj_btn_back", lang)

    @ui.button(label="➕ Add Member", style=discord.ButtonStyle.success, custom_id="members_add_btn")
    async def btn_add_member(self, interaction: discord.Interaction, button: ui.Button) -> None:
        actor_id = str(interaction.user.id)
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        actor_role = await service.get_member_role(self.project.project_id, actor_id)
        is_lead = actor_role == "lead" or self.project.owner_id == actor_id
        if not (is_lead or is_admin):
            await interaction.response.send_message(t("proj_no_permission", self.lang), ephemeral=True)
            return

        view = AddMemberView(self.project, self.lang, interaction.user, parent_view=self)
        embed = discord.Embed(
            title=f"{self.project.emoji} {t('proj_add_member_ui_title', self.lang)}",
            description=t("proj_add_member_ui_desc", self.lang, project=self.project.name),
            color=int(self.project.color.lstrip("#"), 16) if self.project.color.startswith("#") else 0x5865F2,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @ui.button(label="⬅️ Dashboard", style=discord.ButtonStyle.secondary, custom_id="members_back")
    async def btn_back(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer()
        stats = await service.get_project_stats(self.project.project_id, self.project.guild_id)
        embed = build_project_dashboard_embed(stats, self.lang)
        view  = ProjectDashboardView(self.project.project_id, self.project.guild_id, self.lang, self.user)
        await interaction.message.edit(embed=embed, view=view)


def build_project_permissions_embed(
    project: Project,
    role: str,
    permissions: dict[str, bool],
    lang: str,
) -> discord.Embed:
    """Build embed displaying granular permissions for a role in a project."""
    color = int(project.color.lstrip("#"), 16) if project.color.startswith("#") else 0x5865F2
    role_label = t(f"proj_role_{role}", lang) if role in ("lead", "member", "viewer") else role.capitalize()
    embed = discord.Embed(
        title=f"🛡️ {t('proj_perm_title', lang, project=project.name)}",
        description=t("proj_perm_desc", lang, role=role_label),
        color=color,
    )

    lines: list[str] = []
    labels = {
        "can_create_tasks": f"➕ {t('perm_can_create_tasks', lang)}",
        "can_change_deadline": f"📅 {t('perm_can_change_deadline', lang)}",
        "can_assign_tasks": f"👥 {t('perm_can_assign_tasks', lang)}",
        "can_delete_tasks": f"🗑️ {t('perm_can_delete_tasks', lang)}",
        "can_manage_dependencies": f"🔗 {t('perm_can_manage_dependencies', lang)}",
    }
    for perm_key, is_allowed in permissions.items():
        state_icon = "🟢" if is_allowed else "🔴"
        state_text = t("proj_perm_allowed", lang) if is_allowed else t("proj_perm_denied", lang)
        label = labels.get(perm_key, perm_key)
        lines.append(f"{state_icon} **{label}**: `{state_text}`")

    embed.add_field(
        name=t("proj_perm_role_heading", lang, role=role_label),
        value="\n".join(lines) if lines else "—",
        inline=False,
    )
    embed.set_footer(text=t("proj_perm_footer", lang))
    return embed


class ProjectPermissionsView(ui.View):
    """Interactive permission editor for project roles."""

    def __init__(
        self,
        project: Project,
        lang: str,
        user: discord.User | discord.Member,
        role: str = "member",
        permissions: Optional[dict[str, bool]] = None,
    ) -> None:
        super().__init__(timeout=300)
        self.project = project
        self.lang = lang
        self.user = user
        self.role = role
        self.permissions = permissions or {}
        self._sync_components()

    def _sync_components(self) -> None:
        self.clear_items()

        # 1. Role selector dropdown (Member vs Viewer)
        role_select = ui.Select(
            placeholder=t("proj_perm_select_role", self.lang),
            options=[
                discord.SelectOption(
                    label=f"👥 {t('proj_role_member', self.lang)}",
                    value="member",
                    default=(self.role == "member"),
                ),
                discord.SelectOption(
                    label=f"👀 {t('proj_role_viewer', self.lang)}",
                    value="viewer",
                    default=(self.role == "viewer"),
                ),
            ],
            row=0,
            custom_id="perm_role_select",
        )
        role_select.callback = self._on_role_change
        self.add_item(role_select)

        # 2. Permission toggle buttons (row 1 & 2)
        perm_configs = [
            ("can_create_tasks", "➕", t("perm_short_create", self.lang), 1),
            ("can_change_deadline", "📅", t("perm_short_deadline", self.lang), 1),
            ("can_assign_tasks", "👥", t("perm_short_assign", self.lang), 1),
            ("can_delete_tasks", "🗑️", t("perm_short_delete", self.lang), 2),
            ("can_manage_dependencies", "🔗", t("perm_short_deps", self.lang), 2),
        ]
        for perm_key, emoji, label, row_idx in perm_configs:
            is_allowed = self.permissions.get(perm_key, False)
            btn = ui.Button(
                label=f"{label}: {'ON' if is_allowed else 'OFF'}",
                emoji=emoji,
                style=discord.ButtonStyle.success if is_allowed else discord.ButtonStyle.secondary,
                row=row_idx,
                custom_id=f"perm_toggle_{perm_key}",
            )
            btn.callback = self._make_toggle_callback(perm_key)
            self.add_item(btn)

        # 3. Back button (row 3)
        back_btn = ui.Button(
            label=t("proj_btn_back", self.lang),
            style=discord.ButtonStyle.secondary,
            row=3,
            custom_id="perm_back_btn",
        )
        back_btn.callback = self._on_back
        self.add_item(back_btn)

    def _make_toggle_callback(self, perm_key: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer()
            actor_id = str(interaction.user.id)
            is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
            new_val = not self.permissions.get(perm_key, False)
            await service.set_project_role_permission(
                self.project.project_id,
                self.project.guild_id,
                self.role,
                perm_key,
                new_val,
                actor_id,
                is_guild_admin=is_admin,
            )
            self.permissions = await service.get_project_role_permissions(self.project.project_id, self.role)
            self._sync_components()
            embed = build_project_permissions_embed(self.project, self.role, self.permissions, self.lang)
            await interaction.edit_original_response(embed=embed, view=self)
        return callback

    async def _on_role_change(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.role = interaction.data["values"][0]
        self.permissions = await service.get_project_role_permissions(self.project.project_id, self.role)
        self._sync_components()
        embed = build_project_permissions_embed(self.project, self.role, self.permissions, self.lang)
        await interaction.edit_original_response(embed=embed, view=self)

    async def _on_back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        stats = await service.get_project_stats(self.project.project_id, self.project.guild_id)
        embed = build_project_dashboard_embed(stats, self.lang)
        view = ProjectDashboardView(self.project.project_id, self.project.guild_id, self.lang, self.user)
        await interaction.edit_original_response(embed=embed, view=view)
