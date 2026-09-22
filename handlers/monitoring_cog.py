"""
handlers/monitoring_cog.py — Admin-only slash commands for the monitoring system.

Commands:
  /health            — Live health status (DB, memory, uptime, latency)
  /errors            — Top errors in the last 24 h
  /cmdstats          — Command usage statistics since last restart
  /monitoring setup  — Open a Modal to configure monitoring settings for this server
  /monitoring status — Show current monitoring settings for this server

All commands require Administrator permission and respond ephemerally.
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.helpers import get_user_lang
from locales.i18n import t

log = logging.getLogger(__name__)


# ── Setup Modal ───────────────────────────────────────────────────────────────

class MonitoringSetupModal(ui.Modal, title="🔧 Monitoring Setup"):
    """
    Discord Modal that lets admins configure monitoring settings
    for their server directly without touching .env.
    """

    log_channel = ui.TextInput(
        label="📢 Admin Log Channel ID",
        placeholder="e.g. 1234567890123456789",
        required=False,
        max_length=25,
        style=discord.TextStyle.short,
    )

    health_interval = ui.TextInput(
        label="🏥 Health Check Interval (minutes)",
        placeholder="e.g. 5  (default: 5)",
        required=False,
        max_length=4,
        style=discord.TextStyle.short,
    )

    alert_cooldown = ui.TextInput(
        label="⏱️ Alert Rate Limit (seconds)",
        placeholder="e.g. 300  (default: 300 = 5 min)",
        required=False,
        max_length=6,
        style=discord.TextStyle.short,
    )

    monitoring_enabled = ui.TextInput(
        label="✅ Enable Monitoring? (true / false)",
        placeholder="true",
        required=False,
        max_length=5,
        style=discord.TextStyle.short,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from core.database import db

        guild = interaction.guild
        if not guild or not interaction.guild_id:
            lang = await get_user_lang(interaction.user.id)
            await interaction.response.send_message(
                t("monitoring_guild_only", lang), ephemeral=True
            )
            return

        lang = await get_user_lang(interaction.user.id)
        guild_id = str(interaction.guild_id)
        saved: list[str] = []
        errors: list[str] = []

        # ── Validate & save each field ────────────────────────────────────────

        # Log channel ID
        ch_val = self.log_channel.value.strip()
        if ch_val:
            try:
                ch_id = int(ch_val)
                # Try to fetch the channel to verify it exists and is messageable
                channel = guild.get_channel(ch_id)
                if channel is None:
                    try:
                        channel = await interaction.client.fetch_channel(ch_id)
                    except Exception:
                        channel = None

                if channel is None:
                    errors.append(t("monitoring_channel_not_found", lang).format(ch_id=ch_id))
                elif not isinstance(channel, discord.abc.Messageable):
                    errors.append(t("monitoring_channel_unsendable", lang).format(name=channel.name))
                else:
                    await db.set_guild_setting(guild_id, "admin_log_channel_id", str(ch_id))
                    saved.append(t("monitoring_log_channel_saved", lang).format(mention=channel.mention))
                    # Hot-update the live dispatcher for this specific guild
                    if hasattr(interaction.client, "_alert_dispatcher") and interaction.client._alert_dispatcher:
                        interaction.client._alert_dispatcher.update_guild_channel(guild_id, ch_id)
            except ValueError:
                errors.append(t("monitoring_channel_numeric", lang))

        # Health check interval
        hi_val = self.health_interval.value.strip()
        if hi_val:
            try:
                hi = int(hi_val)
                if not (1 <= hi <= 60):
                    errors.append(t("monitoring_health_interval_range", lang))
                else:
                    await db.set_guild_setting(guild_id, "health_check_interval_min", str(hi))
                    saved.append(t("monitoring_health_interval_saved", lang).format(value=hi))
            except ValueError:
                errors.append(t("monitoring_health_interval_numeric", lang))

        # Alert rate limit
        ar_val = self.alert_cooldown.value.strip()
        if ar_val:
            try:
                ar = int(ar_val)
                if not (30 <= ar <= 3600):
                    errors.append(t("monitoring_alert_limit_range", lang))
                else:
                    await db.set_guild_setting(guild_id, "alert_rate_limit_sec", str(ar))
                    saved.append(t("monitoring_alert_limit_saved", lang).format(value=ar))
                    if hasattr(interaction.client, "_alert_dispatcher") and interaction.client._alert_dispatcher:
                        interaction.client._alert_dispatcher._rate_limit_sec = ar
            except ValueError:
                errors.append(t("monitoring_alert_limit_numeric", lang))

        # Enable/disable monitoring
        en_val = self.monitoring_enabled.value.strip().lower()
        if en_val:
            if en_val in ("true", "false", "1", "0", "yes", "no"):
                is_enabled = en_val in ("true", "1", "yes")
                await db.set_guild_setting(guild_id, "monitoring_enabled", str(is_enabled).lower())
                key = "monitoring_enabled_saved_on" if is_enabled else "monitoring_enabled_saved_off"
                saved.append(t(key, lang))
            else:
                errors.append(t("monitoring_enabled_boolean", lang))

        # ── Build response embed ──────────────────────────────────────────────
        if not saved and not errors:
            await interaction.response.send_message(
                t("monitoring_no_changes", lang),
                ephemeral=True,
            )
            return

        color = 0x2ECC71 if not errors else (0xF39C12 if saved else 0xE74C3C)
        embed = discord.Embed(
            title=t("monitoring_setup_results_title", lang),
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        if saved:
            embed.add_field(
                name=t("monitoring_saved_header", lang),
                value="\n".join(saved),
                inline=False,
            )
        if errors:
            embed.add_field(
                name=t("monitoring_errors_header", lang),
                value="\n".join(errors),
                inline=False,
            )
        embed.set_footer(text=t("monitoring_saved_supabase_footer", lang))

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.error("MonitoringSetupModal error: %s", error, exc_info=True)
        lang = await get_user_lang(interaction.user.id)
        try:
            await interaction.response.send_message(
                t("monitoring_save_error", lang),
                ephemeral=True,
            )
        except discord.InteractionResponded:
            await interaction.followup.send(
                t("monitoring_save_error", lang),
                ephemeral=True,
            )


# ── Cog ───────────────────────────────────────────────────────────────────────

class MonitoringCog(commands.Cog, name="Monitoring"):
    """Admin-only monitoring & health commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── Group: /monitoring ────────────────────────────────────────────────────

    monitoring_group = app_commands.Group(
        name="monitoring",
        description="🔧 [Admin] Monitoring & logging configuration",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True,
    )

    @monitoring_group.command(
        name="setup",
        description="🔧 [Admin] Configure monitoring for this server via a form",
    )
    async def monitoring_setup(self, interaction: discord.Interaction) -> None:
        """Open a Modal to configure monitoring settings."""
        await interaction.response.send_modal(MonitoringSetupModal())

    @monitoring_group.command(
        name="status",
        description="📋 [Admin] View current monitoring settings for this server",
    )
    async def monitoring_status(self, interaction: discord.Interaction) -> None:
        """Show current monitoring settings stored in Supabase for this guild."""
        lang = await get_user_lang(interaction.user.id)

        if not interaction.guild or not interaction.guild_id:
            await interaction.response.send_message(
                t("monitoring_guild_only", lang), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            from core.database import db
            guild_id = str(interaction.guild_id)
            settings = await db.get_all_guild_settings(guild_id)

            embed = discord.Embed(
                title=t("monitoring_status_title", lang),
                description=t("monitoring_status_desc", lang).format(guild=interaction.guild.name),
                color=0x3498DB,
                timestamp=discord.utils.utcnow(),
            )

            # Log channel
            ch_id_str = settings.get("admin_log_channel_id")
            if ch_id_str:
                ch = interaction.guild.get_channel(int(ch_id_str))
                if ch:
                    ch_display = ch.mention
                else:
                    ch_display = t("monitoring_channel_not_found_display", lang).format(ch_id=ch_id_str)
            else:
                ch_display = t("monitoring_not_configured_hint", lang)

            embed.add_field(
                name=t("monitoring_status_channel_label", lang),
                value=ch_display,
                inline=False,
            )
            embed.add_field(
                name=t("monitoring_status_health_label", lang),
                value=t("monitoring_status_health_value", lang).format(
                    value=settings.get("health_check_interval_min", "5")
                ),
                inline=True,
            )
            embed.add_field(
                name=t("monitoring_status_rate_label", lang),
                value=t("monitoring_status_rate_value", lang).format(
                    value=settings.get("alert_rate_limit_sec", "300")
                ),
                inline=True,
            )
            is_on = settings.get("monitoring_enabled", "true") == "true"
            embed.add_field(
                name=t("monitoring_status_enabled_label", lang),
                value=t("monitoring_status_active", lang) if is_on else t("monitoring_status_inactive", lang),
                inline=True,
            )
            embed.set_footer(text=t("monitoring_status_footer", lang))

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as exc:
            log.error("/monitoring status failed: %s", exc, exc_info=True)
            await interaction.followup.send(
                t("monitoring_status_fetch_error", lang),
                ephemeral=True,
            )

    # ── /health ───────────────────────────────────────────────────────────────

    @app_commands.command(
        name="health",
        description="🏥 [Admin] View real-time bot health: DB, memory, uptime, latency",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def health_cmd(self, interaction: discord.Interaction) -> None:
        """Display the latest health snapshot as a rich embed."""
        lang = await get_user_lang(interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        try:
            from monitoring.health_monitor import health_monitor
            embed = health_monitor.get_health_embed(lang=lang)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as exc:
            log.error("/health command failed: %s", exc, exc_info=True)
            await interaction.followup.send(
                t("monitoring_fetch_failed", lang),
                ephemeral=True,
            )

    # ── /errors ───────────────────────────────────────────────────────────────

    @app_commands.command(
        name="errors",
        description="🚨 [Admin] View errors from the last 24 hours",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def errors_cmd(self, interaction: discord.Interaction) -> None:
        """Display the error tracker summary embed."""
        lang = await get_user_lang(interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        try:
            from monitoring.error_tracker import error_tracker
            embed = error_tracker.get_summary_embed(lang=lang)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as exc:
            log.error("/errors command failed: %s", exc, exc_info=True)
            await interaction.followup.send(
                t("monitoring_fetch_failed", lang),
                ephemeral=True,
            )

    # ── /cmdstats ─────────────────────────────────────────────────────────────

    @app_commands.command(
        name="cmdstats",
        description="📊 [Admin] View command usage statistics since bot start",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def cmdstats_cmd(self, interaction: discord.Interaction) -> None:
        """Display command usage statistics."""
        lang = await get_user_lang(interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        try:
            from monitoring.commands_log import commands_logger
            embed = commands_logger.get_stats_embed(top_n=10, lang=lang)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as exc:
            log.error("/cmdstats command failed: %s", exc, exc_info=True)
            await interaction.followup.send(
                t("monitoring_fetch_failed", lang),
                ephemeral=True,
            )


# ── Cog setup ─────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MonitoringCog(bot))
    log.info("MonitoringCog loaded — commands: /health /errors /cmdstats /monitoring setup /monitoring status")
