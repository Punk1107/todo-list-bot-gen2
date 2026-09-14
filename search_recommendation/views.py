"""
search_recommendation/views.py — Discord UI Views

Provides rich interactive Discord embeds and UI components for:
  1. SearchResultsView  — paginated FTS search results with filter chips
  2. RecommendationView — scored task recommendations with breakdown badges
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import discord
from discord import ui
import pytz

from locales.i18n import t
from utils.helpers import format_deadline, time_left_str
from search_recommendation.models import (
    SearchQuery,
    SearchResultPage,
    SortBy,
    TaskRecommendation,
    WeightConfig,
)

log = logging.getLogger(__name__)

# Priority level → emoji
_PRIORITY_EMOJIS = ["⬜", "🟦", "🟩", "🟨", "🟧", "🟥", "🔴", "🆘"]

# Status → emoji
_STATUS_EMOJIS = {
    "Pending":     "⏳",
    "In_Progress": "🏃",
    "Completed":   "✅",
    "Cancelled":   "❌",
}


def _priority_emoji(level: int) -> str:
    return _PRIORITY_EMOJIS[max(0, min(7, level))]


def _status_emoji(status: str) -> str:
    return _STATUS_EMOJIS.get(status, "❓")


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build search result embed
# ─────────────────────────────────────────────────────────────────────────────

def build_search_embed(
    result_page: SearchResultPage,
    lang: str,
    tz_name: str,
    scope_label: str = "",
    active_filters: Optional[list[str]] = None,
) -> discord.Embed:
    """Build a Discord embed for a SearchResultPage."""
    now = datetime.now(pytz.utc)

    # Title
    title = t("search_fts_title", lang)
    if result_page.query_text:
        title += f": `{result_page.query_text[:60]}`"

    # Color based on results
    color = 0x5865F2 if result_page.total > 0 else 0x747F8D

    embed = discord.Embed(title=title, color=color)

    # Description: filter chips + stats
    desc_parts: list[str] = []
    if active_filters:
        desc_parts.append("  ".join(f"`{f}`" for f in active_filters))
    if result_page.total == 0:
        desc_parts.append(f"> {t('search_fts_empty', lang)}")
    else:
        desc_parts.append(f"> {t('search_fts_total', lang, total=result_page.total)}")

    embed.description = "\n".join(desc_parts)

    # Result items
    if result_page.items:
        lines: list[str] = []
        for item in result_page.items:
            try:
                dl_dt = datetime.fromisoformat(str(item.deadline))
                if dl_dt.tzinfo is None:
                    dl_dt = dl_dt.replace(tzinfo=pytz.utc)
                is_overdue = dl_dt < now and item.status == "Pending"
            except Exception:
                is_overdue = False

            status_icon = "🚨" if is_overdue else _status_emoji(item.status)
            prio_icon   = _priority_emoji(item.priority)
            pin_icon    = " 📌" if item.is_pinned else ""
            task_name   = item.task[:55]
            if len(item.task) > 55:
                task_name += "…"

            dl_str = format_deadline(item.deadline, tz_name)
            tl_str = time_left_str(item.deadline)

            score_str = ""
            if item.rank_score > 0.0:
                score_str = f"  `⭐{item.rank_score:.3f}`"

            line = (
                f"{status_icon} {prio_icon} `#{item.task_id}`{pin_icon} **{task_name}**{score_str}\n"
                f"   ╰ 📅 `{dl_str}` · ⏱️ `{tl_str}`"
            )
            if item.snippet:
                line += f"\n   ╰ 💬 *{item.snippet[:70]}*"
            lines.append(line)

        embed.add_field(name="", value="\n\n".join(lines), inline=False)

    # Footer: page indicator + FTS note
    page_str = t("search_page_indicator", lang,
                 page=result_page.page, total=result_page.total_pages)
    embed.set_footer(text=f"{page_str}  ·  {t('search_fts_powered', lang)}")

    return embed


# ─────────────────────────────────────────────────────────────────────────────
# SearchResultsView — Interactive paginated view
# ─────────────────────────────────────────────────────────────────────────────

class SearchResultsView(ui.View):
    """
    Paginated Discord UI view for search results.
    Supports ⏮ ◀ [indicator] ▶ ⏭ navigation and 🔄 Refresh.
    """

    def __init__(
        self,
        *,
        uid: str,
        lang: str,
        tz_name: str,
        query: SearchQuery,
        initial_result: SearchResultPage,
        scope_label: str = "",
        active_filters: Optional[list[str]] = None,
    ) -> None:
        super().__init__(timeout=300)
        self.uid            = uid
        self.lang           = lang
        self.tz_name        = tz_name
        self.query          = query
        self.current_result = initial_result
        self.scope_label    = scope_label
        self.active_filters = active_filters or []
        self._message: Optional[discord.Message] = None

        self._update_buttons()

    def _update_buttons(self) -> None:
        """Enable/disable nav buttons based on current page."""
        r = self.current_result
        for item in self.children:
            if isinstance(item, ui.Button):
                cid = getattr(item, "custom_id", "")
                if cid == "sr_first":
                    item.disabled = (r.page <= 1)
                elif cid == "sr_prev":
                    item.disabled = (r.page <= 1)
                elif cid == "sr_page":
                    item.label = t("search_page_indicator", self.lang,
                                   page=r.page, total=r.total_pages)
                elif cid == "sr_next":
                    item.disabled = (r.page >= r.total_pages)
                elif cid == "sr_last":
                    item.disabled = (r.page >= r.total_pages)

    async def _go_to_page(self, interaction: discord.Interaction, page: int) -> None:
        """Navigate to a specific page and update the embed."""
        from search_recommendation.service import search_svc

        self.query = SearchQuery(
            text=self.query.text,
            filter=self.query.filter,
            sort_by=self.query.sort_by,
            page=page,
            page_size=self.query.page_size,
        )
        try:
            self.current_result = await search_svc.search(self.query)
        except Exception as exc:
            log.error("SearchResultsView pagination error: %s", exc)

        self._update_buttons()
        embed = build_search_embed(
            self.current_result, self.lang, self.tz_name,
            self.scope_label, self.active_filters
        )
        await interaction.edit_original_response(embed=embed, view=self)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]
        if self._message:
            try:
                await self._message.edit(view=self)
            except Exception:
                pass

    # ── Buttons ───────────────────────────────────────────────────────────────

    @ui.button(emoji="⏮", style=discord.ButtonStyle.secondary, custom_id="sr_first", row=0)
    async def btn_first(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if str(interaction.user.id) != self.uid:
            await interaction.response.send_message(
                t("permission_denied", self.lang), ephemeral=True)
            return
        await interaction.response.defer()
        await self._go_to_page(interaction, 1)

    @ui.button(emoji="◀", style=discord.ButtonStyle.primary, custom_id="sr_prev", row=0)
    async def btn_prev(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if str(interaction.user.id) != self.uid:
            await interaction.response.send_message(
                t("permission_denied", self.lang), ephemeral=True)
            return
        await interaction.response.defer()
        await self._go_to_page(interaction, max(1, self.current_result.page - 1))

    @ui.button(label="📄 1 / 1", style=discord.ButtonStyle.secondary,
               disabled=True, custom_id="sr_page", row=0)
    async def btn_page(self, interaction: discord.Interaction, button: ui.Button) -> None:
        pass  # display-only

    @ui.button(emoji="▶", style=discord.ButtonStyle.primary, custom_id="sr_next", row=0)
    async def btn_next(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if str(interaction.user.id) != self.uid:
            await interaction.response.send_message(
                t("permission_denied", self.lang), ephemeral=True)
            return
        await interaction.response.defer()
        await self._go_to_page(
            interaction,
            min(self.current_result.total_pages, self.current_result.page + 1)
        )

    @ui.button(emoji="⏭", style=discord.ButtonStyle.secondary, custom_id="sr_last", row=0)
    async def btn_last(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if str(interaction.user.id) != self.uid:
            await interaction.response.send_message(
                t("permission_denied", self.lang), ephemeral=True)
            return
        await interaction.response.defer()
        await self._go_to_page(interaction, self.current_result.total_pages)

    @ui.button(label="🔄 Refresh", style=discord.ButtonStyle.secondary, custom_id="sr_refresh", row=1)
    async def btn_refresh(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if str(interaction.user.id) != self.uid:
            await interaction.response.send_message(
                t("permission_denied", self.lang), ephemeral=True)
            return
        await interaction.response.defer()
        await self._go_to_page(interaction, self.current_result.page)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build recommendation embed
# ─────────────────────────────────────────────────────────────────────────────

def build_recommendation_embed(
    recommendations: list[TaskRecommendation],
    lang: str,
    tz_name: str,
    scope_label: str,
    weights: WeightConfig,
) -> discord.Embed:
    """Build a Discord embed for task recommendations."""
    if not recommendations:
        embed = discord.Embed(
            title=t("recommend_title", lang),
            description=f"> {t('recommend_empty', lang)}",
            color=0x57F287,
        )
        embed.set_footer(text=t("recommend_footer", lang))
        return embed

    embed = discord.Embed(
        title=t("recommend_title", lang),
        description=(
            f"> {t('recommend_desc', lang, count=len(recommendations))}\n"
            f"> `{scope_label}`"
        ),
        color=0xF59E0B,  # amber — "get to work"
    )

    for rec in recommendations:
        # Score badges
        badges = rec.breakdown.summary_badges()
        badges_str = "  ".join(badges) if badges else ""

        # Deadline formatting
        dl_str = format_deadline(rec.deadline, tz_name)
        tl_str = time_left_str(rec.deadline)

        # Priority + status icons
        prio_icon   = _priority_emoji(rec.priority)
        status_icon = _status_emoji(rec.status)

        # Action hint
        action = t(rec.action_hint, lang)

        field_name = (
            f"#{rec.rank}  {status_icon} {prio_icon}  "
            f"`#{rec.task_id}` {rec.task[:45]}"
        )
        if len(rec.task) > 45:
            field_name = field_name[:77] + "…"

        field_value = (
            f"**{t('recommend_score', lang, score=rec.total_score)}**\n"
            f"📅 `{dl_str}` · ⏱️ `{tl_str}`\n"
        )
        if badges_str:
            field_value += f"{badges_str}\n"
        field_value += f"*{action}*"

        embed.add_field(name=field_name, value=field_value, inline=False)

    # Footer with weights summary
    embed.set_footer(text=(
        t("recommend_footer", lang) + "  ·  " +
        t("recommend_weights_info", lang,
          priority=int(weights.priority * 100),
          urgency=int(weights.urgency * 100),
          overdue=int(weights.overdue * 100))
    ))
    return embed


# ─────────────────────────────────────────────────────────────────────────────
# RecommendationView — interactive view with quick action buttons
# ─────────────────────────────────────────────────────────────────────────────

class RecommendationView(ui.View):
    """
    Shows task recommendations with a 'Refresh' button.
    Future: add inline ✅ Complete / 🏃 In-Progress buttons per task.
    """

    def __init__(
        self,
        *,
        uid: str,
        lang: str,
        tz_name: str,
        guild_id: Optional[str],
        recommendations: list[TaskRecommendation],
        weights: WeightConfig,
        scope_label: str,
    ) -> None:
        super().__init__(timeout=180)
        self.uid             = uid
        self.lang            = lang
        self.tz_name         = tz_name
        self.guild_id        = guild_id
        self.recommendations = recommendations
        self.weights         = weights
        self.scope_label     = scope_label
        self._message: Optional[discord.Message] = None

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]
        if self._message:
            try:
                await self._message.edit(view=self)
            except Exception:
                pass

    @ui.button(label="🔄 Refresh", style=discord.ButtonStyle.secondary,
               custom_id="rv_refresh", row=0)
    async def btn_refresh(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if str(interaction.user.id) != self.uid:
            await interaction.response.send_message(
                t("permission_denied", self.lang), ephemeral=True)
            return
        await interaction.response.defer()

        from search_recommendation.service import search_svc
        try:
            self.recommendations = await search_svc.recommend(
                user_id=self.uid,
                guild_id=self.guild_id,
                limit=len(self.recommendations) or 5,
                weights=self.weights,
            )
        except Exception as exc:
            log.error("RecommendationView refresh error: %s", exc)

        embed = build_recommendation_embed(
            self.recommendations, self.lang, self.tz_name,
            self.scope_label, self.weights
        )
        await interaction.edit_original_response(embed=embed, view=self)
