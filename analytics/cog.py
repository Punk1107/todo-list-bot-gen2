"""
analytics/cog.py — Discord Slash Commands for Analytics Snapshot

Commands:
  /analytics snapshot  — On-demand weekly report → sent directly to user DM
  /analytics weekly    — Toggle weekly auto-digest (enable/disable)

This cog is intentionally lightweight: all heavy computation lives in the
Supabase Edge Function. The cog just triggers the Edge Function and relays
the response feedback to the user.
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from analytics.client import AnalyticsClient
from core.config import config
from core.database import db
from locales.i18n import t
from utils.helpers import get_user_lang

log = logging.getLogger(__name__)

# Initialise the client lazily — only if Supabase credentials are present
_analytics_client: AnalyticsClient | None = None


def _get_client() -> AnalyticsClient | None:
    """Returns the shared AnalyticsClient, or None if not configured."""
    global _analytics_client
    if _analytics_client is None:
        url = config.realtime.url  # SUPABASE_URL already in realtime config
        key = config.realtime.key  # SUPABASE_KEY already in realtime config
        if not url or not key:
            return None
        _analytics_client = AnalyticsClient(supabase_url=url, service_key=key)
    return _analytics_client


class AnalyticsCog(commands.Cog, name="Analytics"):
    """Weekly productivity analytics powered by Supabase Edge Functions."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── Slash Command Group ───────────────────────────────────────────────────

    analytics_group = app_commands.Group(
        name="analytics",
        description="📊 View your productivity stats and manage weekly reports",
    )

    @analytics_group.command(name="snapshot", description="📊 Send your weekly productivity report to your DM now")
    @app_commands.describe()
    async def analytics_snapshot(self, interaction: discord.Interaction) -> None:
        """Triggers an on-demand weekly analytics snapshot."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        user_id = str(interaction.user.id)
        lang    = await get_user_lang(user_id)
        client  = _get_client()

        if client is None:
            await interaction.followup.send(t("analytics_not_configured", lang), ephemeral=True)
            return

        # Send processing acknowledgement
        embed = discord.Embed(
            title=t("analytics_snapshot_title", lang),
            description=t("analytics_snapshot_desc", lang),
            color=0x5865F2,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        # Call the Edge Function
        metrics, chart_url = await client.request_snapshot(user_id, lang=lang, send_dm=True)

        if metrics is None:
            err_msg = chart_url or "Unknown error"
            err_embed = discord.Embed(
                title=t("error", lang),
                description=t("analytics_snapshot_failed", lang, error=err_msg),
                color=0xED4245,
            )
            await interaction.edit_original_response(embed=err_embed)
            return

        # Check if DM was sent or blocked
        dm_sent = chart_url is not None  # chart_url is non-None on success
        if dm_sent:
            success_embed = discord.Embed(
                title=t("success", lang),
                description=t("analytics_snapshot_sent", lang),
                color=0x57F287,
            )
            success_embed.add_field(
                name=t("analytics_field_score", lang),
                value=f"**{metrics.productivity_score}/100** {metrics.productivity_emoji}",
                inline=True,
            )
            success_embed.add_field(
                name=t("analytics_field_completed", lang),
                value=f"**{metrics.completed_count}** / {metrics.total_tasks}",
                inline=True,
            )
            success_embed.add_field(
                name=t("analytics_field_ontime", lang),
                value=f"**{metrics.on_time_rate_percent:.1f}%**",
                inline=True,
            )
            await interaction.edit_original_response(embed=success_embed)
        else:
            warn_embed = discord.Embed(
                description=t("analytics_snapshot_dm_disabled", lang),
                color=0xFEE75C,
            )
            await interaction.edit_original_response(embed=warn_embed)

    @analytics_group.command(
        name="weekly",
        description="🔔 Enable or disable your weekly productivity digest sent to your DM",
    )
    @app_commands.describe(enabled="Set to True to enable, False to disable")
    async def analytics_weekly(
        self, interaction: discord.Interaction, enabled: bool
    ) -> None:
        """Toggles the weekly digest auto-delivery for the user."""
        await interaction.response.defer(ephemeral=True)

        user_id = str(interaction.user.id)
        lang    = await get_user_lang(user_id)
        client  = _get_client()

        if client is None:
            await interaction.followup.send(t("analytics_not_configured", lang), ephemeral=True)
            return

        # Persist preference to DB (users.weekly_digest)
        try:
            await db.execute(
                "UPDATE users SET weekly_digest = $1 WHERE user_id = $2",
                (1 if enabled else 0, user_id),
            )
        except Exception as exc:
            log.warning("Could not persist weekly_digest for user %s: %s", user_id, exc)

        key = "analytics_weekly_enabled" if enabled else "analytics_weekly_disabled"
        embed = discord.Embed(
            description=t(key, lang),
            color=0x57F287 if enabled else 0x4F545C,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        log.info(
            "[analytics] User %s (%s) %s weekly digest",
            interaction.user, user_id, "enabled" if enabled else "disabled",
        )



async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AnalyticsCog(bot))
    log.info("[OK] AnalyticsCog loaded — /analytics group registered")
