"""
organization/views.py — Discord UI Views & Embed Builders for Eisenhower Matrix and Saved Filters
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import ui

from locales.i18n import t
from organization.models import (
    EisenhowerMatrixData,
    EisenhowerQuadrant,
    EisenhowerTask,
    QUADRANT_META,
    SavedFilter,
)
from organization import service

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Eisenhower Matrix Embed & Views
# ─────────────────────────────────────────────────────────────────────────────

def build_matrix_embed(
    matrix: EisenhowerMatrixData,
    lang: str,
    theme_color: int,
    scope_name: Optional[str] = None,
) -> discord.Embed:
    """Build the 4-quadrant Eisenhower Matrix overview embed."""
    title = f"🧭 {t('matrix_title', lang)}"
    if scope_name:
        title += f" — {scope_name}"

    summary = t(
        "matrix_summary", lang,
        q1=matrix.q1_count,
        q2=matrix.q2_count,
        q3=matrix.q3_count,
        q4=matrix.q4_count,
        total=matrix.total_count,
    )

    embed = discord.Embed(
        title=title,
        description=f"{t('matrix_desc', lang)}\n\n{summary}",
        color=theme_color,
    )

    # Helper to render task list for a quadrant
    def format_quadrant_field(tasks: list[EisenhowerTask], max_items: int = 4) -> str:
        if not tasks:
            return f"*{t('matrix_empty', lang)}*"
        lines = []
        for task in tasks[:max_items]:
            time_str = f" `{task.relative_time}`" if task.relative_time else ""
            priv_badge = "🔒 " if task.is_private else ""
            lines.append(f"• {task.priority_emoji} {priv_badge}**#{task.task_id}** {task.task[:35]}{time_str}")
        if len(tasks) > max_items:
            lines.append(f"*... +{len(tasks) - max_items} {t('matrix_more', lang)}*")
        return "\n".join(lines)

    # Quadrant 1: 🔴 Do First
    q1_name = f"🔴 {t('matrix_q1_title', lang)} ({matrix.q1_count})"
    embed.add_field(name=q1_name, value=format_quadrant_field(matrix.q1_tasks), inline=False)

    # Quadrant 2: 🔵 Schedule
    q2_name = f"🔵 {t('matrix_q2_title', lang)} ({matrix.q2_count})"
    embed.add_field(name=q2_name, value=format_quadrant_field(matrix.q2_tasks), inline=False)

    # Quadrant 3: 🟡 Delegate
    q3_name = f"🟡 {t('matrix_q3_title', lang)} ({matrix.q3_count})"
    embed.add_field(name=q3_name, value=format_quadrant_field(matrix.q3_tasks), inline=False)

    # Quadrant 4: ⚪ Eliminate
    q4_name = f"⚪ {t('matrix_q4_title', lang)} ({matrix.q4_count})"
    embed.add_field(name=q4_name, value=format_quadrant_field(matrix.q4_tasks), inline=False)

    embed.set_footer(text=t("footer_text", lang))
    return embed


class EisenhowerMatrixView(ui.View):
    """Interactive view for browsing and drilling into Eisenhower quadrants."""

    def __init__(
        self,
        user_id: str,
        guild_id: Optional[str],
        matrix: EisenhowerMatrixData,
        lang: str,
        theme_color: int,
        project_id: Optional[int] = None,
        scope_name: Optional[str] = None,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.guild_id = guild_id
        self.matrix = matrix
        self.lang = lang
        self.theme_color = theme_color
        self.project_id = project_id
        self.scope_name = scope_name

        self._build_components()

    def _build_components(self) -> None:
        self.clear_items()

        # Quadrant selector dropdown
        options = [
            discord.SelectOption(
                label=f"🔴 {t('matrix_q1_title', self.lang)} ({self.matrix.q1_count})",
                value=EisenhowerQuadrant.Q1_DO_FIRST.value,
                description=t("matrix_q1_desc", self.lang)[:50],
            ),
            discord.SelectOption(
                label=f"🔵 {t('matrix_q2_title', self.lang)} ({self.matrix.q2_count})",
                value=EisenhowerQuadrant.Q2_SCHEDULE.value,
                description=t("matrix_q2_desc", self.lang)[:50],
            ),
            discord.SelectOption(
                label=f"🟡 {t('matrix_q3_title', self.lang)} ({self.matrix.q3_count})",
                value=EisenhowerQuadrant.Q3_DELEGATE.value,
                description=t("matrix_q3_desc", self.lang)[:50],
            ),
            discord.SelectOption(
                label=f"⚪ {t('matrix_q4_title', self.lang)} ({self.matrix.q4_count})",
                value=EisenhowerQuadrant.Q4_ELIMINATE.value,
                description=t("matrix_q4_desc", self.lang)[:50],
            ),
        ]

        select = ui.Select(
            placeholder=t("matrix_select_quadrant", self.lang),
            options=options,
            row=0,
        )
        select.callback = self._on_quadrant_selected
        self.add_item(select)

        # Refresh button
        btn_refresh = ui.Button(
            label=t("matrix_btn_refresh", self.lang),
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        btn_refresh.callback = self._on_refresh
        self.add_item(btn_refresh)

    async def _on_quadrant_selected(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return

        chosen_val = interaction.data["values"][0] # type: ignore
        quadrant = EisenhowerQuadrant(chosen_val)
        tasks = self.matrix.get_quadrant_tasks(quadrant)

        view = QuadrantDetailView(
            user_id=self.user_id,
            guild_id=self.guild_id,
            parent_view=self,
            quadrant=quadrant,
            tasks=tasks,
            lang=self.lang,
            theme_color=self.theme_color,
        )
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    async def _on_refresh(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return

        self.matrix = await service.get_eisenhower_matrix(
            self.user_id, self.guild_id, self.project_id
        )
        self._build_components()
        embed = build_matrix_embed(self.matrix, self.lang, self.theme_color, self.scope_name)
        await interaction.response.edit_message(embed=embed, view=self)


class QuadrantDetailView(ui.View):
    """Detailed paginated view of tasks within a specific quadrant."""

    def __init__(
        self,
        user_id: str,
        guild_id: Optional[str],
        parent_view: EisenhowerMatrixView,
        quadrant: EisenhowerQuadrant,
        tasks: list[EisenhowerTask],
        lang: str,
        theme_color: int,
        page: int = 0,
        page_size: int = 5,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.guild_id = guild_id
        self.parent_view = parent_view
        self.quadrant = quadrant
        self.tasks = tasks
        self.lang = lang
        self.theme_color = theme_color
        self.page = page
        self.page_size = page_size

        self._build_components()

    @property
    def total_pages(self) -> int:
        return max(1, (len(self.tasks) + self.page_size - 1) // self.page_size)

    def build_embed(self) -> discord.Embed:
        meta = QUADRANT_META[self.quadrant]
        title = f"{meta.emoji} {t(meta.name_key, self.lang)} — ({len(self.tasks)} {t('matrix_tasks', self.lang)})"
        desc = t(meta.desc_key, self.lang)

        embed = discord.Embed(
            title=title,
            description=f"*{desc}*",
            color=meta.color_int,
        )

        start_idx = self.page * self.page_size
        page_tasks = self.tasks[start_idx : start_idx + self.page_size]

        if not page_tasks:
            embed.description += f"\n\n*{t('matrix_empty', self.lang)}*"
        else:
            for task in page_tasks:
                time_str = f" | `{task.relative_time}`" if task.relative_time else ""
                priv_str = " | 🔒 Private" if task.is_private else ""
                val = f"Status: `{task.status}`{time_str}{priv_str}"
                if task.description:
                    val += f"\n> {task.description[:80]}"
                embed.add_field(
                    name=f"{task.priority_emoji} #{task.task_id} {task.task}",
                    value=val,
                    inline=False,
                )

        footer_text = f"Page {self.page + 1}/{self.total_pages} • {t('footer_text', self.lang)}"
        embed.set_footer(text=footer_text)
        return embed

    def _build_components(self) -> None:
        self.clear_items()

        # Prev button
        btn_prev = ui.Button(label="◀️", style=discord.ButtonStyle.secondary, disabled=(self.page <= 0), row=0)
        btn_prev.callback = self._on_prev
        self.add_item(btn_prev)

        # Back to Overview button
        btn_back = ui.Button(label=t("btn_back", self.lang), emoji="🧭", style=discord.ButtonStyle.primary, row=0)
        btn_back.callback = self._on_back
        self.add_item(btn_back)

        # Next button
        btn_next = ui.Button(label="▶️", style=discord.ButtonStyle.secondary, disabled=(self.page >= self.total_pages - 1), row=0)
        btn_next.callback = self._on_next
        self.add_item(btn_next)

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        if self.page > 0:
            self.page -= 1
            self._build_components()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        if self.page < self.total_pages - 1:
            self.page += 1
            self._build_components()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_back(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        # Return to main matrix overview
        embed = build_matrix_embed(
            self.parent_view.matrix, self.lang, self.theme_color, self.parent_view.scope_name
        )
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Saved Filters / Smart Lists Views
# ─────────────────────────────────────────────────────────────────────────────

def build_saved_filter_embed(
    saved_filter: SavedFilter,
    tasks: list[dict],
    lang: str,
    theme_color: int,
) -> discord.Embed:
    """Build embed displaying tasks matching a saved filter."""
    crit = saved_filter.criteria
    title = f"🔖 {saved_filter.name} ({len(tasks)} {t('matrix_tasks', lang)})"

    # Build criteria summary string
    crit_parts = []
    if crit.tags:
        crit_parts.append(f"Tags: `{', '.join(crit.tags)}`")
    if crit.min_priority is not None or crit.max_priority is not None:
        min_p = crit.min_priority if crit.min_priority is not None else 0
        max_p = crit.max_priority if crit.max_priority is not None else 7
        crit_parts.append(f"Priority: `{min_p}..{max_p}`")
    if crit.status:
        crit_parts.append(f"Status: `{crit.status}`")
    if crit.due_within_days is not None:
        crit_parts.append(f"Due: `<={crit.due_within_days}d`")

    desc = f"🔍 **Criteria**: {' | '.join(crit_parts)}" if crit_parts else ""

    embed = discord.Embed(
        title=title,
        description=desc,
        color=theme_color,
    )

    if not tasks:
        embed.description = (desc + f"\n\n*{t('filter_empty', lang)}*").strip()
    else:
        for t_row in tasks[:10]:
            prio = int(t_row.get("priority") or 0)
            prio_emoji = ["⚪", "🔵", "🟡", "🟠", "🔴", "🔴", "💀", "🚨"][prio] if 0 <= prio <= 7 else "⚪"
            dl = f" | 📅 {t_row['deadline'][:16]}" if t_row.get("deadline") else ""
            embed.add_field(
                name=f"{prio_emoji} #{t_row['task_id']} {t_row['task']}",
                value=f"Status: `{t_row.get('status')}`{dl}",
                inline=False,
            )
        if len(tasks) > 10:
            embed.set_footer(text=f"Showing top 10 of {len(tasks)} {t('matrix_tasks', lang)} • {t('footer_text', lang)}")
        else:
            embed.set_footer(text=t("footer_text", lang))

    return embed


def build_filter_list_embed(
    filters: list[SavedFilter],
    lang: str,
    theme_color: int,
) -> discord.Embed:
    """Build embed listing all saved filters for a user."""
    embed = discord.Embed(
        title=f"🔖 {t('filter_list_title', lang)}",
        color=theme_color,
    )
    if not filters:
        embed.description = f"*{t('filter_list_empty', lang)}*"
    else:
        embed.description = t("filter_list_desc", lang)
        for sf in filters:
            crit = sf.criteria
            details = []
            if crit.tags:
                details.append(f"tags: `{','.join(crit.tags)}`")
            if crit.min_priority is not None:
                details.append(f"priority >={crit.min_priority}")
            if crit.status:
                details.append(f"status: `{crit.status}`")
            val_str = f"⚙️ {', '.join(details)}" if details else "⚙️ Default active"
            embed.add_field(name=f"📌 {sf.name}", value=val_str, inline=False)

    embed.set_footer(text=t("footer_text", lang))
    return embed
