"""
agile/views.py — Discord interactive UI views, embeds, and modals for Agile & Scrum Suite.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import discord
from discord import ui

from agile import service
from agile.models import (
    FIBONACCI_POINTS,
    Epic,
    PlanningPokerSession,
    RetroCard,
    RetroColumn,
    Sprint,
    VelocityStats,
)
from locales.i18n import t

log = logging.getLogger(__name__)


def _progress_bar(pct: int, length: int = 12) -> str:
    """ASCII/Emoji progress bar."""
    pct = max(0, min(100, int(pct)))
    filled = int(round(length * pct / 100))
    empty = length - filled
    return f"`[{'█' * filled}{'░' * empty}]` **{pct}%**"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Embed Builders
# ─────────────────────────────────────────────────────────────────────────────

def build_sprint_embed(sprint: Sprint, lang: str = "th") -> discord.Embed:
    """Build an interactive dashboard embed for a Sprint."""
    status_emoji = {"planned": "📅", "active": "⚡", "closed": "🏁"}.get(sprint.status, "📋")
    color = 0x5865F2 if sprint.is_active else (0x57F287 if sprint.is_closed else 0xFEE75C)

    embed = discord.Embed(
        title=f"{status_emoji} Sprint: {sprint.name} (#{sprint.sprint_id})",
        color=color,
    )
    if sprint.goal:
        embed.description = f"🎯 **Sprint Goal:** {sprint.goal}\n"
    else:
        embed.description = ""

    embed.description += (
        f"\n**Task Completion:** {_progress_bar(sprint.completion_pct)} "
        f"({sprint.completed_tasks}/{sprint.total_tasks} Tasks)\n"
        f"**Story Points Burnt:** {_progress_bar(sprint.points_completion_pct)} "
        f"({sprint.completed_points}/{sprint.total_points} Points)\n"
    )

    status_str = sprint.status.capitalize()
    embed.add_field(name="📊 Status", value=f"`{status_str}`", inline=True)

    if sprint.start_date:
        ts = int(sprint.start_date.timestamp())
        embed.add_field(name="🚀 Start Date", value=f"<t:{ts}:D>", inline=True)
    if sprint.end_date:
        ts = int(sprint.end_date.timestamp())
        days_left = sprint.days_remaining
        time_str = f"<t:{ts}:R>" if days_left is not None else f"<t:{ts}:D>"
        embed.add_field(name="⏳ Target End", value=time_str, inline=True)

    embed.set_footer(text=f"Project #{sprint.project_id} · To-Do List Bot Gen 5.0 Agile")
    return embed


def build_velocity_embed(stats: VelocityStats, lang: str = "th") -> discord.Embed:
    """Build a Team Velocity and Capacity Forecasting embed."""
    embed = discord.Embed(
        title="📈 Team Velocity & Sprint Capacity Forecast",
        color=0x5865F2,
    )
    embed.description = (
        f"**Average Velocity:** `⚡ {stats.average_velocity} Story Points / Sprint`\n"
        f"**Remaining Backlog:** `{stats.backlog_tasks_count} Tasks` · `{stats.backlog_points} Points`\n"
        f"**Forecast to Clear:** `🎯 ~{stats.forecast_sprints} Sprints`\n"
    )

    if stats.sprint_history:
        history_lines = []
        for name, pts in stats.sprint_history:
            bar = "█" * min(15, max(1, int(pts // 2)))
            history_lines.append(f"• **{name}**: `{bar}` **{pts} pts**")
        embed.add_field(
            name="📊 Closed Sprints History (Last 5)",
            value="\n".join(history_lines),
            inline=False,
        )
    else:
        embed.add_field(
            name="📊 Closed Sprints History",
            value="*No closed sprints yet. Complete your first sprint to track team velocity!*",
            inline=False,
        )

    embed.set_footer(text=f"Project #{stats.project_id} · Formula: Avg Points = Sum(Completed) / Sprints")
    return embed


def build_poker_embed(session: PlanningPokerSession, lang: str = "th") -> discord.Embed:
    """Build the Planning Poker voting embed."""
    embed = discord.Embed(
        title=f"🃏 Planning Poker: Task #{session.task_id}",
        description=f"**Task Title:** {session.task_title}\n\n"
                    f"*Click a Fibonacci card below to cast your secret vote!*",
        color=0x5865F2,
    )

    if not session.is_revealed:
        # Hide individual votes, show list of who has voted
        if session.votes:
            voters = [f"• <@{uid}> `[Voted 🔒]`" for uid in session.votes]
            embed.add_field(
                name=f"👥 Participants Voted ({session.voter_count})",
                value="\n".join(voters),
                inline=False,
            )
        else:
            embed.add_field(
                name="👥 Participants",
                value="*Waiting for votes...*",
                inline=False,
            )
    else:
        # Revealed! Show all individual votes and computed consensus metrics
        vote_lines = [f"• <@{uid}>: **{pts} points**" for uid, pts in session.votes.items()]
        embed.add_field(
            name=f"🃏 Revealed Cards ({session.voter_count} Votes)",
            value="\n".join(vote_lines) if vote_lines else "*No votes cast*",
            inline=False,
        )
        consensus = session.consensus
        consensus_text = f"🎯 Consensus: **{consensus} Points**" if consensus is not None else "⚠️ Divergent (Discussion recommended)"
        embed.add_field(
            name="📊 Statistics & Recommendation",
            value=(
                f"• **Mean (Average):** `{session.mean}`\n"
                f"• **Median:** `{session.median}`\n"
                f"• **Recommended Fibonacci:** `{session.nearest_fibonacci} Points`\n"
                f"• **Consensus Check:** {consensus_text}"
            ),
            inline=False,
        )
        embed.color = 0x57F287

    embed.set_footer(text=f"Host: User #{session.host_id} · Fibonacci: 1, 2, 3, 5, 8, 13, 21")
    return embed


def build_epic_embed(epic: Epic, tasks: list[dict[str, Any]], lang: str = "th") -> discord.Embed:
    """Build Epic view with Hierarchical Tree View."""
    color = int(epic.color.lstrip("#"), 16) if epic.color.startswith("#") else 0x5865F2
    embed = discord.Embed(
        title=f"👑 Epic: {epic.name} (#{epic.epic_id})",
        color=color,
    )
    if epic.description:
        embed.description = f"{epic.description}\n\n"
    else:
        embed.description = ""

    embed.description += (
        f"**Progress:** {_progress_bar(epic.progress_pct)} "
        f"({epic.completed_tasks}/{epic.total_tasks} Tasks · {epic.completed_points}/{epic.total_points} Points)\n"
    )

    if not tasks:
        embed.add_field(name="📋 Tasks in Epic", value="*No tasks attached yet. Use `/epic attach` to add tasks.*", inline=False)
    else:
        lines = []
        for t_info in tasks[:12]:
            tid = t_info["task_id"]
            name = t_info["task"][:40]
            pts = f"({t_info['story_points']} pts)" if t_info.get("story_points") else ""
            status_ico = "✅" if t_info["status"] == "Completed" else ("⚡" if t_info["status"] == "In_Progress" else "📋")
            lines.append(f"{status_ico} `#{tid}` **{name}** {pts}")

            # Subtasks indentation
            for st in t_info.get("subtasks", [])[:3]:
                st_ico = "✅" if st["status"] == "Completed" else "↳"
                lines.append(f"  {st_ico} `#{st['task_id']}` *{st['task'][:30]}*")

        if len(tasks) > 12:
            lines.append(f"... +{len(tasks) - 12} more tasks")
        embed.add_field(name="🌳 Hierarchical Task Tree", value="\n".join(lines), inline=False)

    embed.set_footer(text=f"Project #{epic.project_id} · Status: {epic.status.capitalize()}")
    return embed


def build_retro_embed(
    sprint_id: int,
    board: dict[str, list[RetroCard]],
    lang: str = "th",
    user_id: Optional[str] = None,
) -> discord.Embed:
    """Build the Interactive Sprint Retrospective Board."""
    embed = discord.Embed(
        title=f"🏁 Sprint Retrospective Board (Sprint #{sprint_id})",
        description="Share your insights and vote on team improvement action items!",
        color=0x5865F2,
    )

    # 1. What Went Well
    well_cards = board.get(RetroColumn.WELL.value, [])
    well_lines = [f"• **{c.votes} 🌟** {c.content} *(by {f'<@{c.author_id}>' if c.author_id else 'Anonymous'})*" for c in well_cards[:8]]
    embed.add_field(
        name=f"🌟 What Went Well ({len(well_cards)})",
        value="\n".join(well_lines) if well_lines else "*No cards yet*",
        inline=False,
    )

    # 2. What Could Be Improved
    imp_cards = board.get(RetroColumn.IMPROVE.value, [])
    imp_lines = [f"• **{c.votes} 🔧** {c.content} *(by {f'<@{c.author_id}>' if c.author_id else 'Anonymous'})*" for c in imp_cards[:8]]
    embed.add_field(
        name=f"🔧 What Could Be Improved ({len(imp_cards)})",
        value="\n".join(imp_lines) if imp_lines else "*No cards yet*",
        inline=False,
    )

    # 3. Action Items
    act_cards = board.get(RetroColumn.ACTION.value, [])
    act_lines = [f"• **{c.votes} 🎯** `#{c.retro_id}` {c.content} *(by {f'<@{c.author_id}>' if c.author_id else 'Anonymous'})*" for c in act_cards[:8]]
    embed.add_field(
        name=f"🎯 Action Items ({len(act_cards)})",
        value="\n".join(act_lines) if act_lines else "*No action items yet*",
        inline=False,
    )

    if user_id:
        rem_votes = service.get_user_remaining_votes(sprint_id, user_id)
        embed.set_footer(text=f"Your Remaining Dot Votes: {rem_votes}/3 · Sprint #{sprint_id}")
    else:
        embed.set_footer(text=f"Dot Voting: 3 votes per team member · Sprint #{sprint_id}")

    return embed


# ─────────────────────────────────────────────────────────────────────────────
# 2. Interactive Views & Modals
# ─────────────────────────────────────────────────────────────────────────────

class PlanningPokerView(ui.View):
    """Interactive planning poker voting action row."""

    def __init__(self, task_id: int, host_id: str, lang: str = "th") -> None:
        super().__init__(timeout=600)
        self.task_id = task_id
        self.host_id = host_id
        self.lang = lang

    async def _handle_vote(self, interaction: discord.Interaction, points: int) -> None:
        uid = str(interaction.user.id)
        ok = service.cast_poker_vote(self.task_id, uid, points)
        if not ok:
            await interaction.response.send_message("❌ This poker session has already been revealed or ended.", ephemeral=True)
            return

        session = service.get_poker_session(self.task_id)
        if session:
            new_embed = build_poker_embed(session, self.lang)
            try:
                await interaction.message.edit(embed=new_embed, view=self)
            except Exception:
                pass
        await interaction.response.send_message(f"✅ Your secret vote of **{points} points** has been recorded!", ephemeral=True)

    @ui.button(label="1", style=discord.ButtonStyle.secondary, row=0)
    async def btn_1(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._handle_vote(interaction, 1)

    @ui.button(label="2", style=discord.ButtonStyle.secondary, row=0)
    async def btn_2(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._handle_vote(interaction, 2)

    @ui.button(label="3", style=discord.ButtonStyle.secondary, row=0)
    async def btn_3(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._handle_vote(interaction, 3)

    @ui.button(label="5", style=discord.ButtonStyle.secondary, row=0)
    async def btn_5(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._handle_vote(interaction, 5)

    @ui.button(label="8", style=discord.ButtonStyle.secondary, row=1)
    async def btn_8(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._handle_vote(interaction, 8)

    @ui.button(label="13", style=discord.ButtonStyle.secondary, row=1)
    async def btn_13(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._handle_vote(interaction, 13)

    @ui.button(label="21", style=discord.ButtonStyle.secondary, row=1)
    async def btn_21(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._handle_vote(interaction, 21)

    @ui.button(label="🃏 Reveal Cards", style=discord.ButtonStyle.primary, row=2)
    async def btn_reveal(self, interaction: discord.Interaction, button: ui.Button) -> None:
        uid = str(interaction.user.id)
        if uid != self.host_id and not (isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("❌ Only the poker host or a server admin can reveal the cards.", ephemeral=True)
            return

        session = service.reveal_poker(self.task_id)
        if not session:
            await interaction.response.send_message("❌ Poker session not found.", ephemeral=True)
            return

        # Disable Fibonacci buttons, enable save button
        for child in self.children:
            if isinstance(child, ui.Button) and child.label in [str(x) for x in FIBONACCI_POINTS]:
                child.disabled = True
        button.disabled = True
        self.btn_save.disabled = False

        new_embed = build_poker_embed(session, self.lang)
        await interaction.response.edit_message(embed=new_embed, view=self)

    @ui.button(label="💾 Save Points", style=discord.ButtonStyle.success, row=2, disabled=True)
    async def btn_save(self, interaction: discord.Interaction, button: ui.Button) -> None:
        uid = str(interaction.user.id)
        if uid != self.host_id and not (isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("❌ Only the poker host or a server admin can save points.", ephemeral=True)
            return

        session = service.get_poker_session(self.task_id)
        if not session or not session.votes:
            await interaction.response.send_message("❌ No votes recorded.", ephemeral=True)
            return

        final_pts = session.nearest_fibonacci
        await service.save_poker_points(self.task_id, final_pts)

        self.stop()
        await interaction.response.send_message(
            f"✅ **Story points saved!** Task #{self.task_id} has been set to **{final_pts} points**.",
            ephemeral=False,
        )


class RetroAddCardModal(ui.Modal):
    """Modal for submitting a retrospective card."""

    def __init__(self, sprint_id: int, lang: str = "th") -> None:
        super().__init__(title="➕ Submit Retrospective Card")
        self.sprint_id = sprint_id
        self.lang = lang

        self.col_input = ui.TextInput(
            label="Column (well / improve / action)",
            placeholder="well, improve, or action",
            default="well",
            max_length=10,
            required=True,
        )
        self.content_input = ui.TextInput(
            label="Your Feedback / Action Item",
            style=discord.TextStyle.paragraph,
            placeholder="What went well or what should we improve?",
            max_length=500,
            required=True,
        )
        self.anon_input = ui.TextInput(
            label="Anonymous? (yes / no)",
            placeholder="Type 'yes' to hide your username",
            default="no",
            max_length=5,
            required=False,
        )
        self.add_item(self.col_input)
        self.add_item(self.content_input)
        self.add_item(self.anon_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        col_raw = self.col_input.value.strip().lower()
        if col_raw not in ("well", "improve", "action"):
            await interaction.response.send_message("❌ Invalid column! Please enter 'well', 'improve', or 'action'.", ephemeral=True)
            return

        content = self.content_input.value.strip()
        is_anon = self.anon_input.value.strip().lower() in ("yes", "y", "true")
        author_id = None if is_anon else str(interaction.user.id)

        try:
            await service.add_retro_card(self.sprint_id, col_raw, content, author_id)
            await interaction.response.send_message("✅ Your card has been submitted to the Retrospective Board!", ephemeral=True)
        except Exception as exc:
            await interaction.response.send_message(f"❌ Error submitting card: {exc}", ephemeral=True)


class RetroDotVoteSelect(ui.Select):
    """Dropdown to spend a dot vote on an Action Item or Improvement card."""

    def __init__(self, sprint_id: int, cards: list[RetroCard], lang: str = "th") -> None:
        self.sprint_id = sprint_id
        options = []
        for c in cards[:25]:
            col_icon = "🌟" if c.column_type == "well" else ("🔧" if c.column_type == "improve" else "🎯")
            options.append(
                discord.SelectOption(
                    label=f"{col_icon} #{c.retro_id}: {c.content[:70]}",
                    value=str(c.retro_id),
                    description=f"Current votes: {c.votes}",
                )
            )
        super().__init__(placeholder="Choose a card to spend 1 Dot Vote...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        retro_id = int(self.values[0])
        uid = str(interaction.user.id)
        try:
            new_votes = await service.vote_retro_card(retro_id, self.sprint_id, uid)
            rem = service.get_user_remaining_votes(self.sprint_id, uid)
            await interaction.response.send_message(
                f"🗳️ Vote recorded! Card #{retro_id} now has **{new_votes} votes**. (Remaining votes: {rem}/3)",
                ephemeral=True,
            )
        except service.DotVotesExhaustedError as exc:
            await interaction.response.send_message(f"⚠️ {exc}", ephemeral=True)
        except Exception as exc:
            await interaction.response.send_message(f"❌ Error: {exc}", ephemeral=True)


class RetroBoardView(ui.View):
    """Main interactive view for Sprint Retrospective Board."""

    def __init__(self, sprint_id: int, project_id: int, lang: str = "th") -> None:
        super().__init__(timeout=600)
        self.sprint_id = sprint_id
        self.project_id = project_id
        self.lang = lang

    @ui.button(label="➕ Add Card", style=discord.ButtonStyle.primary, row=0)
    async def btn_add_card(self, interaction: discord.Interaction, button: ui.Button) -> None:
        modal = RetroAddCardModal(self.sprint_id, self.lang)
        await interaction.response.send_modal(modal)

    @ui.button(label="🗳️ Cast Dot Vote", style=discord.ButtonStyle.secondary, row=0)
    async def btn_vote(self, interaction: discord.Interaction, button: ui.Button) -> None:
        board = await service.get_retro_board(self.sprint_id)
        all_cards = board[RetroColumn.WELL.value] + board[RetroColumn.IMPROVE.value] + board[RetroColumn.ACTION.value]
        if not all_cards:
            await interaction.response.send_message("❌ No cards submitted yet to vote on.", ephemeral=True)
            return

        vote_view = ui.View(timeout=120)
        vote_view.add_item(RetroDotVoteSelect(self.sprint_id, all_cards, self.lang))
        await interaction.response.send_message("Select a card to vote on:", view=vote_view, ephemeral=True)

    @ui.button(label="🔄 Refresh Board", style=discord.ButtonStyle.secondary, row=0)
    async def btn_refresh(self, interaction: discord.Interaction, button: ui.Button) -> None:
        board = await service.get_retro_board(self.sprint_id)
        uid = str(interaction.user.id)
        new_embed = build_retro_embed(self.sprint_id, board, self.lang, user_id=uid)
        await interaction.response.edit_message(embed=new_embed, view=self)

    @ui.button(label="🚀 Convert Actions to Tasks", style=discord.ButtonStyle.success, row=1)
    async def btn_convert_actions(self, interaction: discord.Interaction, button: ui.Button) -> None:
        uid = str(interaction.user.id)
        count = await service.convert_action_items_to_tasks(self.sprint_id, self.project_id, uid)
        if count > 0:
            await interaction.response.send_message(
                f"🎯 **Success!** Converted **{count} Action Items** into new Backlog tasks for the next sprint.",
                ephemeral=False,
            )
        else:
            await interaction.response.send_message("ℹ️ No Action Items found on this board to convert.", ephemeral=True)


class SprintCloseConfirmView(ui.View):
    """Confirmation view when closing a sprint with carryover options."""

    def __init__(self, sprint_id: int, project_id: int, lang: str = "th") -> None:
        super().__init__(timeout=120)
        self.sprint_id = sprint_id
        self.project_id = project_id
        self.lang = lang

    @ui.button(label="📦 Return Unfinished to Backlog", style=discord.ButtonStyle.primary)
    async def btn_backlog(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        uid = str(interaction.user.id)
        sprint, done_cnt, carried_cnt, pts = await service.close_sprint(
            self.sprint_id, self.project_id, uid, carryover_target="backlog"
        )
        self.stop()
        embed = discord.Embed(
            title=f"🏁 Sprint #{self.sprint_id} Closed",
            description=(
                f"**Completion Summary:**\n"
                f"• Completed Tasks: `{done_cnt}`\n"
                f"• Story Points Burnt: `{pts}`\n"
                f"• Unfinished Tasks Returned to Backlog: `{carried_cnt}`"
            ),
            color=0x57F287,
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

    @ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def btn_cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.stop()
        await interaction.response.send_message("Cancelled sprint closure.", ephemeral=True)

