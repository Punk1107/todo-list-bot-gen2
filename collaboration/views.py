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

import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import ui
import pytz

from collaboration import service
from collaboration.models import BoardData, Project, ProjectStats, ProjectTask, ProjectActivity
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
            f"{p.status_emoji} {p.emoji} **{p.name}** `#{p.project_id}`\n"
            f"   ╰ {p.description[:60] + '…' if p.description and len(p.description) > 60 else (p.description or '—')}"
        )
    embed.description = "\n".join(lines)
    embed.set_footer(text=t("proj_footer", lang, count=len(projects)))
    return embed


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
            deadline_str = format_deadline(task.deadline, "UTC") if task.deadline else "—"
            embed.add_field(
                name=f"{task.priority_emoji} `#{task.task_id}` {task.task[:55]}",
                value=(
                    f"📅 `{deadline_str}` · ⏱️ `{time_left_str(task.deadline)}`{assignee_str}"
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

    def __init__(self, lang: str) -> None:
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
        self.add_item(self.name)
        self.add_item(self.description)
        self.add_item(self.color)
        self.add_item(self.emoji_field)

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

        await ensure_user(owner_id, lang)
        try:
            project = await service.create_project(
                guild_id    = guild_id,
                name        = name,
                owner_id    = owner_id,
                description = self.description.value.strip() or None,
                color       = color_val,
                emoji       = emoji_val,
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

    def __init__(self, project: Project, lang: str) -> None:
        super().__init__(title=t("proj_add_task_modal_title", lang, name=project.name[:30]))
        self.project = project
        self.lang    = lang

        self.task_name = ui.TextInput(
            label=t("task_name_label", lang),
            placeholder=t("task_name_placeholder", lang),
            max_length=200, required=True,
        )
        self.deadline = ui.TextInput(
            label=t("task_deadline_label", lang),
            placeholder=t("task_deadline_placeholder", lang),
            max_length=20, required=True,
        )
        self.description_field = ui.TextInput(
            label=t("task_desc_label", lang),
            placeholder=t("task_desc_placeholder", lang),
            style=discord.TextStyle.paragraph,
            max_length=500, required=False,
        )
        self.add_item(self.task_name)
        self.add_item(self.deadline)
        self.add_item(self.description_field)

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

        try:
            task = await service.add_project_task(
                project_id  = self.project.project_id,
                guild_id    = self.project.guild_id,
                task_name   = self.task_name.value.strip(),
                deadline_iso= dt.isoformat(),
                creator_id  = uid,
                description = self.description_field.value.strip() or None,
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

class ProjectDashboardView(ui.View):
    """Main project dashboard with navigation buttons."""

    def __init__(self, project_id: int, guild_id: str, lang: str, user: discord.User | discord.Member) -> None:
        super().__init__(timeout=300)
        self.project_id = project_id
        self.guild_id   = guild_id
        self.lang       = lang
        self.user       = user

    @ui.button(label="📊 Dashboard", style=discord.ButtonStyle.primary,  custom_id="proj_dash_dashboard")
    async def btn_dashboard(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        await interaction.response.defer()
        try:
            stats = await service.get_project_stats(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang), ephemeral=True)
            return
        embed = build_project_dashboard_embed(stats, lang)
        await interaction.message.edit(embed=embed, view=self)

    @ui.button(label="📋 Board", style=discord.ButtonStyle.secondary, custom_id="proj_dash_board")
    async def btn_board(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        await interaction.response.defer()
        try:
            board = await service.get_project_board(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang), ephemeral=True)
            return
        embed = build_board_embed(board, lang, "pending")
        view  = ProjectBoardView(self.project_id, self.guild_id, lang, self.user, board)
        await interaction.message.edit(embed=embed, view=view)

    @ui.button(label="👥 Members", style=discord.ButtonStyle.secondary, custom_id="proj_dash_members")
    async def btn_members(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        await interaction.response.defer()
        try:
            project = await service.get_project(self.project_id, self.guild_id)
            members = await service.get_project_members(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang), ephemeral=True)
            return
        embed = build_members_embed(members, project, lang)
        view  = MembersView(project, lang, self.user, members)
        await interaction.message.edit(embed=embed, view=view)

    @ui.button(label="📜 Activity", style=discord.ButtonStyle.secondary, custom_id="proj_dash_activity")
    async def btn_activity(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        await interaction.response.defer()
        try:
            project    = await service.get_project(self.project_id, self.guild_id)
            activities = await service.get_project_activity(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang), ephemeral=True)
            return
        embed = build_activity_embed(activities, project, lang)
        await interaction.message.edit(embed=embed, view=self)

    @ui.button(label="➕ Add Task", style=discord.ButtonStyle.success, custom_id="proj_dash_add_task")
    async def btn_add_task(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        try:
            project = await service.get_project(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.response.send_message(t("proj_not_found", lang), ephemeral=True)
            return
        modal = AddProjectTaskModal(project, lang)
        await interaction.response.send_modal(modal)


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
        try:
            board = await service.get_project_board(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", self.lang), ephemeral=True)
            return
        embed = build_board_embed(board, self.lang, col)
        view  = ProjectBoardView(self.project_id, self.guild_id, self.lang, self.user, board, current_col=col)
        await interaction.message.edit(embed=embed, view=view)


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

    @ui.button(label="🙋 Claim a Task", style=discord.ButtonStyle.success, custom_id="board_claim_btn")
    async def btn_claim(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = self.lang
        await interaction.response.defer(ephemeral=True)
        try:
            board = await service.get_project_board(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang), ephemeral=True)
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

    @ui.button(label="⬅️ Dashboard", style=discord.ButtonStyle.secondary, custom_id="board_back_btn")
    async def btn_back(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer()
        try:
            stats = await service.get_project_stats(self.project_id, self.guild_id)
        except service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", self.lang), ephemeral=True)
            return
        embed = build_project_dashboard_embed(stats, self.lang)
        view  = ProjectDashboardView(self.project_id, self.guild_id, self.lang, self.user)
        await interaction.message.edit(embed=embed, view=view)


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
            await interaction.followup.send(t("proj_not_found", lang), ephemeral=True)
            return
        except service.TaskNotFound:
            await interaction.followup.send(t("proj_task_not_found", lang, task_id=task_id), ephemeral=True)
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


class MembersView(ui.View):
    """Members list with management options for the project lead."""

    def __init__(self, project: Project, lang: str, user: discord.User | discord.Member, members: list[ProjectMember]) -> None:
        super().__init__(timeout=300)
        self.project = project
        self.lang    = lang
        self.user    = user
        self.members = members

    @ui.button(label="⬅️ Dashboard", style=discord.ButtonStyle.secondary, custom_id="members_back")
    async def btn_back(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer()
        stats = await service.get_project_stats(self.project.project_id, self.project.guild_id)
        embed = build_project_dashboard_embed(stats, self.lang)
        view  = ProjectDashboardView(self.project.project_id, self.project.guild_id, self.lang, self.user)
        await interaction.message.edit(embed=embed, view=view)
