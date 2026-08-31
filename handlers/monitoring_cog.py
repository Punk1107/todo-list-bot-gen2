"""
handlers/monitoring_cog.py — Admin-only slash commands for the monitoring system.

Commands:
  /health    — Live health status (DB, memory, uptime, latency)
  /errors    — Top errors in the last 24 h
  /cmdstats  — Command usage statistics since last restart

All commands require Administrator permission and respond ephemerally.
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)


class MonitoringCog(commands.Cog, name="Monitoring"):
    """Admin-only monitoring & health commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /health ───────────────────────────────────────────────────────────────

    @app_commands.command(
        name="health",
        description="🏥 [Admin] Show live bot health: DB, memory, uptime, latency",
    )
    @app_commands.default_member_permissions(administrator=True)
    @app_commands.guild_only()
    async def health_cmd(self, interaction: discord.Interaction) -> None:
        """Display the latest health snapshot as a rich embed."""
        await interaction.response.defer(ephemeral=True)
        try:
            from monitoring.health_monitor import health_monitor
            embed = health_monitor.get_health_embed()
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as exc:
            log.error("/health command failed: %s", exc, exc_info=True)
            await interaction.followup.send(
                "❌ Could not fetch health data. Check logs for details.",
                ephemeral=True,
            )

    # ── /errors ───────────────────────────────────────────────────────────────

    @app_commands.command(
        name="errors",
        description="🚨 [Admin] Show top errors recorded in the last 24 hours",
    )
    @app_commands.default_member_permissions(administrator=True)
    @app_commands.guild_only()
    async def errors_cmd(self, interaction: discord.Interaction) -> None:
        """Display the error tracker summary embed."""
        await interaction.response.defer(ephemeral=True)
        try:
            from monitoring.error_tracker import error_tracker
            embed = error_tracker.get_summary_embed()
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as exc:
            log.error("/errors command failed: %s", exc, exc_info=True)
            await interaction.followup.send(
                "❌ Could not fetch error data. Check logs for details.",
                ephemeral=True,
            )

    # ── /cmdstats ─────────────────────────────────────────────────────────────

    @app_commands.command(
        name="cmdstats",
        description="📊 [Admin] Show command usage stats since last restart",
    )
    @app_commands.default_member_permissions(administrator=True)
    @app_commands.guild_only()
    async def cmdstats_cmd(self, interaction: discord.Interaction) -> None:
        """Display command usage statistics."""
        await interaction.response.defer(ephemeral=True)
        try:
            from monitoring.commands_log import commands_logger
            embed = commands_logger.get_stats_embed(top_n=10)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as exc:
            log.error("/cmdstats command failed: %s", exc, exc_info=True)
            await interaction.followup.send(
                "❌ Could not fetch stats. Check logs for details.",
                ephemeral=True,
            )


# ── Cog setup ─────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MonitoringCog(bot))
    log.info("MonitoringCog loaded — commands: /health /errors /cmdstats")
