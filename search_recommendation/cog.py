"""
search_recommendation/cog.py — Discord Slash Commands

Provides two new slash commands:
  /search  — Full Text Search with filters, sorting, and pagination
  /recommend — AI-ready rule-based task prioritization

Registers as a Cog loaded via main.py COGS list.
"""
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.security import rate_limit_check, validator
from locales.i18n import t
from utils.helpers import get_user_lang, get_user_timezone, ensure_user
from search_recommendation.models import (
    SearchFilter,
    SearchQuery,
    SortBy,
    WeightConfig,
)
from search_recommendation.service import search_svc
from search_recommendation.views import (
    SearchResultsView,
    RecommendationView,
    build_search_embed,
    build_recommendation_embed,
)

log = logging.getLogger(__name__)

# ── Sort order choices for the /search sort parameter ────────────────────────
_SORT_CHOICES = [
    app_commands.Choice(name="📊 Best Match (relevance)",   value="relevance"),
    app_commands.Choice(name="📅 Earliest Deadline",        value="deadline_asc"),
    app_commands.Choice(name="📅 Latest Deadline",          value="deadline_desc"),
    app_commands.Choice(name="🔴 Highest Priority",         value="priority_desc"),
    app_commands.Choice(name="🆕 Newest First",             value="created_desc"),
]

# ── Status choices ────────────────────────────────────────────────────────────
_STATUS_CHOICES = [
    app_commands.Choice(name="⏳ Pending",     value="Pending"),
    app_commands.Choice(name="🏃 In Progress", value="In_Progress"),
    app_commands.Choice(name="✅ Completed",   value="Completed"),
]

# ── Scope choices for /search ─────────────────────────────────────────────────
_SCOPE_CHOICES = [
    app_commands.Choice(name="📋 Personal Tasks",  value="personal"),
    app_commands.Choice(name="🏛️ Guild Tasks",     value="guild"),
]


class SearchRecommendationCog(commands.Cog, name="SearchRecommendation"):
    """Cog providing /search (FTS) and /recommend (task prioritization) commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ──────────────────────────────────────────────────────────────────────────
    # /search
    # ──────────────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="search",
        description="🔍 ค้นหา Task แบบ Full Text Search / Search tasks with advanced FTS"
    )
    @app_commands.describe(
        query      = "คำค้นหา / Search keyword (title, tags, description)",
        status     = "กรองตามสถานะ / Filter by status",
        priority   = "กรองตาม Priority ขั้นต่ำ (0–7) / Min priority level",
        sort       = "เรียงลำดับ / Sort order",
        scope      = "ขอบเขต / Search scope (personal or guild tasks)",
        page_size  = "จำนวนผลลัพธ์ต่อหน้า (1–25) / Results per page",
    )
    @app_commands.choices(status=_STATUS_CHOICES, sort=_SORT_CHOICES, scope=_SCOPE_CHOICES)
    @rate_limit_check("search")
    async def search(
        self,
        interaction: discord.Interaction,
        query:      str  = "",
        status:     Optional[app_commands.Choice[str]] = None,
        priority:   Optional[int] = None,
        sort:       Optional[app_commands.Choice[str]] = None,
        scope:      Optional[app_commands.Choice[str]] = None,
        page_size:  int = 10,
    ) -> None:
        uid      = str(interaction.user.id)
        lang     = await get_user_lang(uid)
        tz_name  = await get_user_timezone(uid)
        await ensure_user(uid, lang)

        # Sanitize query text
        clean_query = validator.sanitize(query, 200) if query else ""
        if clean_query and validator.is_suspicious(clean_query):
            await interaction.response.send_message(
                t("err_suspicious", lang), ephemeral=True)
            return

        await interaction.response.defer()

        # Determine scope
        guild_id_val: Optional[str] = None
        owner_id_val: Optional[str] = None
        scope_val = scope.value if scope else "personal"

        if scope_val == "guild" and interaction.guild:
            guild_id_val = str(interaction.guild.id)
            scope_label  = t("recommend_scope_guild", lang)
        else:
            owner_id_val = uid
            scope_label  = t("recommend_scope_personal", lang)

        # Build sort
        sort_by = SortBy.RELEVANCE
        if sort:
            try:
                sort_by = SortBy(sort.value)
            except ValueError:
                pass

        # Page size bounds
        page_size = max(1, min(page_size, 25))

        # Build active filter chips for display
        active_filters: list[str] = []
        if clean_query:
            active_filters.append(f"🔍 \"{clean_query[:30]}\"")
        if status:
            active_filters.append(f"Status: {status.value}")
        if priority is not None:
            active_filters.append(f"P{priority}+")

        # Build SearchQuery
        search_query = SearchQuery(
            text=clean_query,
            filter=SearchFilter(
                owner_id=owner_id_val,
                guild_id=guild_id_val,
                status=status.value if status else None,
                priority_min=priority,
            ),
            sort_by=sort_by,
            page=1,
            page_size=page_size,
        )

        try:
            result_page = await search_svc.search(search_query)
        except Exception as exc:
            log.error("Search command error: %s", exc, exc_info=True)
            await interaction.followup.send(t("err_db", lang), ephemeral=True)
            return

        embed = build_search_embed(result_page, lang, tz_name, scope_label, active_filters)
        view  = SearchResultsView(
            uid=uid,
            lang=lang,
            tz_name=tz_name,
            query=search_query,
            initial_result=result_page,
            scope_label=scope_label,
            active_filters=active_filters,
        )

        await interaction.followup.send(embed=embed, view=view)
        view._message = await interaction.original_response()

    # ──────────────────────────────────────────────────────────────────────────
    # /recommend
    # ──────────────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="recommend",
        description="🎯 แนะนำงานที่ควรทำก่อน (จัดลำดับอัจฉริยะ) / Get AI-ready task recommendations"
    )
    @app_commands.describe(
        limit   = "จำนวน Task ที่ต้องการแนะนำ (1–10) / Number of recommendations (1–10)",
        scope   = "ขอบเขต / Scope: personal tasks or guild shared tasks",
        preset  = "โหมดน้ำหนักคะแนน / Scoring preset",
    )
    @app_commands.choices(
        scope=[
            app_commands.Choice(name="📋 Personal Tasks",  value="personal"),
            app_commands.Choice(name="🏛️ Guild Tasks",     value="guild"),
        ],
        preset=[
            app_commands.Choice(name="⚖️ Balanced (default)",     value="default"),
            app_commands.Choice(name="⚡ Urgency-focused",         value="urgency"),
            app_commands.Choice(name="🔴 Priority-focused",        value="priority"),
        ],
    )
    @rate_limit_check("command")
    async def recommend(
        self,
        interaction: discord.Interaction,
        limit:  int = 5,
        scope:  Optional[app_commands.Choice[str]] = None,
        preset: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        uid     = str(interaction.user.id)
        lang    = await get_user_lang(uid)
        tz_name = await get_user_timezone(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer()

        # Clamp limit
        limit = max(1, min(limit, 10))

        # Determine scope
        guild_id_val: Optional[str] = None
        scope_val = scope.value if scope else "personal"

        if scope_val == "guild" and interaction.guild:
            guild_id_val = str(interaction.guild.id)
            scope_label  = t("recommend_scope_guild", lang)
        else:
            scope_label  = t("recommend_scope_personal", lang)

        # Select weight preset
        preset_val = preset.value if preset else "default"
        if preset_val == "urgency":
            weights = WeightConfig.urgency_focused()
        elif preset_val == "priority":
            weights = WeightConfig.priority_focused()
        else:
            weights = WeightConfig.default()

        try:
            recommendations = await search_svc.recommend(
                user_id=uid,
                guild_id=guild_id_val,
                limit=limit,
                weights=weights,
            )
        except Exception as exc:
            log.error("Recommend command error: %s", exc, exc_info=True)
            await interaction.followup.send(t("err_db", lang), ephemeral=True)
            return

        embed = build_recommendation_embed(
            recommendations, lang, tz_name, scope_label, weights
        )
        view = RecommendationView(
            uid=uid,
            lang=lang,
            tz_name=tz_name,
            guild_id=guild_id_val,
            recommendations=recommendations,
            weights=weights,
            scope_label=scope_label,
        )

        await interaction.followup.send(embed=embed, view=view)
        view._message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SearchRecommendationCog(bot))
