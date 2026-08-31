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
            await interaction.response.send_message(
                "❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์เท่านั้น", ephemeral=True
            )
            return

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
                    errors.append(f"❌ **Channel ID `{ch_id}`** ไม่พบในเซิร์ฟเวอร์นี้")
                elif not isinstance(channel, discord.abc.Messageable):
                    errors.append(f"❌ Channel `{channel.name}` ไม่สามารถส่งข้อความได้")
                else:
                    await db.set_guild_setting(guild_id, "admin_log_channel_id", str(ch_id))
                    saved.append(f"📢 **Log Channel** → {channel.mention}")
                    # Hot-update the live dispatcher for this specific guild
                    if hasattr(interaction.client, "_alert_dispatcher") and interaction.client._alert_dispatcher:
                        interaction.client._alert_dispatcher.update_guild_channel(guild_id, ch_id)
            except ValueError:
                errors.append("❌ **Channel ID** ต้องเป็นตัวเลขเท่านั้น")

        # Health check interval
        hi_val = self.health_interval.value.strip()
        if hi_val:
            try:
                hi = int(hi_val)
                if not (1 <= hi <= 60):
                    errors.append("❌ **Health Interval** ต้องอยู่ระหว่าง 1–60 นาที")
                else:
                    await db.set_guild_setting(guild_id, "health_check_interval_min", str(hi))
                    saved.append(f"🏥 **Health Interval** → {hi} นาที")
            except ValueError:
                errors.append("❌ **Health Interval** ต้องเป็นตัวเลขเท่านั้น")

        # Alert rate limit
        ar_val = self.alert_cooldown.value.strip()
        if ar_val:
            try:
                ar = int(ar_val)
                if not (30 <= ar <= 3600):
                    errors.append("❌ **Alert Rate Limit** ต้องอยู่ระหว่าง 30–3600 วินาที")
                else:
                    await db.set_guild_setting(guild_id, "alert_rate_limit_sec", str(ar))
                    saved.append(f"⏱️ **Alert Rate Limit** → {ar} วินาที")
                    if hasattr(interaction.client, "_alert_dispatcher") and interaction.client._alert_dispatcher:
                        interaction.client._alert_dispatcher._rate_limit_sec = ar
            except ValueError:
                errors.append("❌ **Alert Rate Limit** ต้องเป็นตัวเลขเท่านั้น")

        # Enable/disable monitoring
        en_val = self.monitoring_enabled.value.strip().lower()
        if en_val:
            if en_val in ("true", "false", "1", "0", "yes", "no"):
                is_enabled = en_val in ("true", "1", "yes")
                await db.set_guild_setting(guild_id, "monitoring_enabled", str(is_enabled).lower())
                saved.append(f"✅ **Monitoring** → {'เปิดใช้งาน ✓' if is_enabled else 'ปิดใช้งาน ✗'}")
            else:
                errors.append("❌ **Enable Monitoring** ต้องเป็น `true` หรือ `false`")

        # ── Build response embed ──────────────────────────────────────────────
        if not saved and not errors:
            await interaction.response.send_message(
                "ℹ️ ไม่มีการเปลี่ยนแปลง — กรอกอย่างน้อยหนึ่งช่องเพื่อบันทึกการตั้งค่า",
                ephemeral=True,
            )
            return

        color = 0x2ECC71 if not errors else (0xF39C12 if saved else 0xE74C3C)
        embed = discord.Embed(
            title="🔧 Monitoring Setup — Results",
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        if saved:
            embed.add_field(
                name="✅ บันทึกสำเร็จ",
                value="\n".join(saved),
                inline=False,
            )
        if errors:
            embed.add_field(
                name="⚠️ พบข้อผิดพลาด",
                value="\n".join(errors),
                inline=False,
            )
        embed.set_footer(text="การตั้งค่าถูกบันทึกใน Supabase — มีผลทันที")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.error("MonitoringSetupModal error: %s", error, exc_info=True)
        await interaction.response.send_message(
            "❌ เกิดข้อผิดพลาดระหว่างบันทึก — ดู logs สำหรับรายละเอียด",
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
        description="🔧 [Admin] กำหนดค่า Monitoring สำหรับเซิร์ฟเวอร์นี้ผ่านแบบฟอร์ม",
    )
    async def monitoring_setup(self, interaction: discord.Interaction) -> None:
        """Open a Modal to configure monitoring settings."""
        await interaction.response.send_modal(MonitoringSetupModal())

    @monitoring_group.command(
        name="status",
        description="📋 [Admin] ดูการตั้งค่า Monitoring ปัจจุบันของเซิร์ฟเวอร์นี้",
    )
    async def monitoring_status(self, interaction: discord.Interaction) -> None:
        """Show current monitoring settings stored in Supabase for this guild."""
        if not interaction.guild or not interaction.guild_id:
            await interaction.response.send_message(
                "❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์เท่านั้น", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            from core.database import db
            guild_id = str(interaction.guild_id)
            settings = await db.get_all_guild_settings(guild_id)

            embed = discord.Embed(
                title="📋 Monitoring Settings",
                description=f"การตั้งค่าปัจจุบันของเซิร์ฟเวอร์ **{interaction.guild.name}**",
                color=0x3498DB,
                timestamp=discord.utils.utcnow(),
            )

            # Log channel
            ch_id_str = settings.get("admin_log_channel_id")
            if ch_id_str:
                ch = interaction.guild.get_channel(int(ch_id_str))
                ch_display = ch.mention if ch else f"`{ch_id_str}` (ไม่พบช่อง)"
            else:
                ch_display = "⚠️ ยังไม่ได้ตั้งค่า — ใช้ `/monitoring setup` เพื่อกำหนด"

            embed.add_field(
                name="📢 Admin Log Channel",
                value=ch_display,
                inline=False,
            )
            embed.add_field(
                name="🏥 Health Check Interval",
                value=f"{settings.get('health_check_interval_min', '5')} นาที",
                inline=True,
            )
            embed.add_field(
                name="⏱️ Alert Rate Limit",
                value=f"{settings.get('alert_rate_limit_sec', '300')} วินาที",
                inline=True,
            )
            embed.add_field(
                name="✅ Monitoring Enabled",
                value="เปิดใช้งาน ✓" if settings.get("monitoring_enabled", "true") == "true" else "ปิดใช้งาน ✗",
                inline=True,
            )
            embed.set_footer(text="แก้ไขด้วย /monitoring setup · บันทึกใน Supabase")

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as exc:
            log.error("/monitoring status failed: %s", exc, exc_info=True)
            await interaction.followup.send(
                "❌ ไม่สามารถดึงข้อมูลได้ — ดู logs สำหรับรายละเอียด",
                ephemeral=True,
            )

    # ── /health ───────────────────────────────────────────────────────────────

    @app_commands.command(
        name="health",
        description="🏥 [Admin] ดูสถานะสุขภาพบอทแบบ Real-time: DB, memory, uptime, latency",
    )
    @app_commands.default_permissions(administrator=True)
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
                "❌ ไม่สามารถดึงข้อมูลได้ — ดู logs สำหรับรายละเอียด",
                ephemeral=True,
            )

    # ── /errors ───────────────────────────────────────────────────────────────

    @app_commands.command(
        name="errors",
        description="🚨 [Admin] ดู Error ที่เกิดขึ้นใน 24 ชั่วโมงที่ผ่านมา",
    )
    @app_commands.default_permissions(administrator=True)
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
                "❌ ไม่สามารถดึงข้อมูลได้ — ดู logs สำหรับรายละเอียด",
                ephemeral=True,
            )

    # ── /cmdstats ─────────────────────────────────────────────────────────────

    @app_commands.command(
        name="cmdstats",
        description="📊 [Admin] ดูสถิติการใช้คำสั่งตั้งแต่เริ่มบอท",
    )
    @app_commands.default_permissions(administrator=True)
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
                "❌ ไม่สามารถดึงข้อมูลได้ — ดู logs สำหรับรายละเอียด",
                ephemeral=True,
            )


# ── Cog setup ─────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MonitoringCog(bot))
    log.info("MonitoringCog loaded — commands: /health /errors /cmdstats /monitoring setup /monitoring status")
