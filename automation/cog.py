"""
automation/cog.py — Discord Slash Commands and Background Worker for:
- Event-Condition-Action (ECA) Automation Builder (/automation)
- Automated Escalation Policies (/automation escalation)
- Service Level Agreement (SLA) Monitoring & Breaches (/sla)
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.database import db
from locales.i18n import t
from utils.helpers import ensure_user, get_user_lang
from automation import engine
from automation.views import (
    build_escalation_embed,
    build_rules_embed,
    build_sla_breaches_embed,
    build_sla_status_embed,
)

log = logging.getLogger(__name__)


class AutomationCog(commands.Cog, name="Automation"):
    """No-Code Workflow Automations, Task Escalations & SLA Management."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.escalation_and_sla_loop.start()

    def cog_unload(self) -> None:
        self.escalation_and_sla_loop.cancel()

    # ─────────────────────────────────────────────────────────────────────────
    # Background Task Loop (Every 5 minutes)
    # ─────────────────────────────────────────────────────────────────────────

    @tasks.loop(minutes=5)
    async def escalation_and_sla_loop(self) -> None:
        """Periodic background evaluation for critical task escalations and SLA breaches."""
        try:
            # 1. Escalation checks (12h L1 ping, 18h L2 lead alert)
            escalations = await engine.check_and_escalate_tasks(self.bot)
            if escalations:
                log.info("Evaluated %d task escalations", len(escalations))

            # 2. SLA deadline & early warning checks (75% warning, 100% breach)
            sla_alerts = await engine.check_sla_deadlines(self.bot)
            if sla_alerts:
                log.info("Evaluated %d SLA alerts", len(sla_alerts))
        except Exception as e:
            log.exception("Unhandled error in escalation_and_sla_loop: %s", e)

    @escalation_and_sla_loop.before_loop
    async def before_escalation_and_sla_loop(self) -> None:
        await self.bot.wait_until_ready()

    # ─────────────────────────────────────────────────────────────────────────
    # Slash Command Group: /automation
    # ─────────────────────────────────────────────────────────────────────────

    automation = app_commands.Group(
        name="automation",
        description="⚡ No-Code Workflow Automations & Escalation Policies",
    )

    escalation = app_commands.Group(
        name="escalation",
        description="🚨 Automated Task Escalation Policies",
        parent=automation,
    )

    @automation.command(
        name="list",
        description="📜 ดูรายการกฎอัตโนมัติ ECA ทั้งหมดของเซิร์ฟเวอร์ / List all server automation rules",
    )
    async def auto_list(self, interaction: discord.Interaction) -> None:
        user_id = str(interaction.user.id)
        await ensure_user(user_id, interaction.user.name)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "DM"

        rules = await engine.list_rules(guild_id)
        embed = build_rules_embed(rules, interaction.guild.name if interaction.guild else "Direct Messages")
        await interaction.response.send_message(embed=embed)

    @automation.command(
        name="create",
        description="➕ สร้างกฎอัตโนมัติ ECA ใหม่ / Create a new ECA automation rule",
    )
    @app_commands.describe(
        name="ชื่อกฎอัตโนมัติ / Rule name",
        trigger_event="อีเวนต์ที่กระตุ้น / Trigger event",
        condition_json="เงื่อนไขแบบ JSON (เช่น {'priority_gte': 5, 'has_tag': 'bug'})",
        action_json="แอ็กชันแบบ JSON (เช่น {'notify_channel': {'channel_id': '123'}})",
    )
    @app_commands.choices(
        trigger_event=[
            app_commands.Choice(name="Task Created (เมื่องานถูกสร้าง)", value="task_created"),
            app_commands.Choice(name="Task Completed (เมื่องานเสร็จสมบูรณ์)", value="task_completed"),
            app_commands.Choice(name="Checklist Completed (เมื่อเช็กลิสต์ครบ)", value="checklist_completed"),
            app_commands.Choice(name="Task Overdue (เมื่องานเลยกำหนด)", value="task_overdue"),
        ]
    )
    async def auto_create(
        self,
        interaction: discord.Interaction,
        name: str,
        trigger_event: app_commands.Choice[str],
        condition_json: str = "{}",
        action_json: str = "{}",
    ) -> None:
        user_id = str(interaction.user.id)
        await ensure_user(user_id, interaction.user.name)
        lang = await get_user_lang(user_id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "DM"

        try:
            cond_dict = json.loads(condition_json) if condition_json.strip() else {}
            if not isinstance(cond_dict, dict):
                raise ValueError("condition_json must be a JSON object.")
        except Exception as e:
            await interaction.response.send_message(f"❌ รูปแบบ condition_json ไม่ถูกต้อง: {e}", ephemeral=True)
            return

        try:
            act_dict = json.loads(action_json) if action_json.strip() else {}
            if not isinstance(act_dict, dict):
                raise ValueError("action_json must be a JSON object.")
        except Exception as e:
            await interaction.response.send_message(f"❌ รูปแบบ action_json ไม่ถูกต้อง: {e}", ephemeral=True)
            return

        rule_id = await engine.create_rule(
            guild_id=guild_id,
            name=name,
            trigger_event=trigger_event.value,
            condition_json=cond_dict,
            action_json=act_dict,
            created_by=user_id,
        )

        msg = t("auto_rule_created", lang, rule_id=rule_id, name=name)
        await interaction.response.send_message(msg)

    @automation.command(
        name="delete",
        description="🗑️ ลบกฎอัตโนมัติ ECA ตาม ID / Delete an automation rule",
    )
    @app_commands.describe(rule_id="รหัสของกฎที่ต้องการลบ / Rule ID")
    async def auto_delete(self, interaction: discord.Interaction, rule_id: int) -> None:
        user_id = str(interaction.user.id)
        await ensure_user(user_id, interaction.user.name)
        lang = await get_user_lang(user_id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "DM"

        success = await engine.delete_rule(rule_id, guild_id)
        if success:
            msg = t("auto_rule_deleted", lang, rule_id=rule_id)
            await interaction.response.send_message(msg)
        else:
            await interaction.response.send_message(f"❌ ไม่พบ Rule #{rule_id} ในเซิร์ฟเวอร์นี้", ephemeral=True)

    @automation.command(
        name="toggle",
        description="🔄 สลับเปิด/ปิดกฎอัตโนมัติ ECA / Toggle enable/disable of an automation rule",
    )
    @app_commands.describe(rule_id="รหัสของกฎที่ต้องการสลับ / Rule ID")
    async def auto_toggle(self, interaction: discord.Interaction, rule_id: int) -> None:
        user_id = str(interaction.user.id)
        await ensure_user(user_id, interaction.user.name)
        lang = await get_user_lang(user_id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "DM"

        new_status = await engine.toggle_rule(rule_id, guild_id)
        if new_status is not None:
            status_text = "เปิดใช้งาน (Active)" if new_status else "ปิดใช้งาน (Paused)"
            msg = t("auto_rule_toggled", lang, rule_id=rule_id, status=status_text)
            await interaction.response.send_message(msg)
        else:
            await interaction.response.send_message(f"❌ ไม่พบ Rule #{rule_id} ในเซิร์ฟเวอร์นี้", ephemeral=True)

    # Subgroup: /automation escalation
    @escalation.command(
        name="status",
        description="🚨 ตรวจสอบสถานะงานที่ถูกยกระดับการแจ้งเตือน / View escalated critical tasks",
    )
    async def esc_status(self, interaction: discord.Interaction) -> None:
        user_id = str(interaction.user.id)
        await ensure_user(user_id, interaction.user.name)
        guild_id = str(interaction.guild_id) if interaction.guild_id else None

        escalations = await engine.get_escalation_status(guild_id)
        embed = build_escalation_embed(escalations, interaction.guild.name if interaction.guild else "Direct Messages")
        await interaction.response.send_message(embed=embed)

    @escalation.command(
        name="set",
        description="⚙️ ตั้งค่านโยบาย Escalation สำหรับงานวิกฤต / Configure escalation policy",
    )
    @app_commands.describe(
        project_id="รหัสโปรเจกต์ / Project ID",
        lead_mention="หัวหน้าทีมที่รับการแจ้งเตือน Level 2 / Project Lead to mention",
    )
    async def esc_set(
        self,
        interaction: discord.Interaction,
        project_id: int,
        lead_mention: Optional[discord.Member] = None,
    ) -> None:
        user_id = str(interaction.user.id)
        await ensure_user(user_id, interaction.user.name)
        lang = await get_user_lang(user_id)

        proj = await db.fetchone("SELECT * FROM projects WHERE project_id = $1", project_id)
        if not proj:
            await interaction.response.send_message(f"❌ ไม่พบโปรเจกต์ #{project_id}", ephemeral=True)
            return

        if lead_mention:
            try:
                await db.execute("UPDATE projects SET lead_id = $1 WHERE project_id = $2", str(lead_mention.id), project_id)
            except Exception as e:
                log.warning("Could not update lead_id on project %s: %s", project_id, e)

        msg = t("auto_escalation_set", lang, project_id=project_id, lead=lead_mention.mention if lead_mention else "Current Lead")
        await interaction.response.send_message(msg)

    # ─────────────────────────────────────────────────────────────────────────
    # Slash Command Group: /sla (Feature 23 - Zero 25-Command limit conflict)
    # ─────────────────────────────────────────────────────────────────────────

    sla = app_commands.Group(
        name="sla",
        description="⏱️ Service Level Agreement (SLA) Monitoring & Breaches",
    )

    @sla.command(
        name="config",
        description="⚙️ กำหนดกรอบเวลา SLA ประจำโปรเจกต์ / Configure SLA policy thresholds for a project",
    )
    @app_commands.describe(
        project_id="รหัสโปรเจกต์ / Project ID",
        p7_hours="กรอบเวลาสำหรับ P7 Critical (ชม. เช่น 2.0)",
        p6_hours="กรอบเวลาสำหรับ P6 High (ชม. เช่น 8.0)",
        p5_hours="กรอบเวลาสำหรับ P5 Medium (ชม. เช่น 24.0)",
        p4_hours="กรอบเวลาสำหรับ P4 Low (ชม. เช่น 48.0)",
    )
    async def sla_config_cmd(
        self,
        interaction: discord.Interaction,
        project_id: int,
        p7_hours: float = 2.0,
        p6_hours: float = 8.0,
        p5_hours: float = 24.0,
        p4_hours: float = 48.0,
    ) -> None:
        user_id = str(interaction.user.id)
        await ensure_user(user_id, interaction.user.name)
        lang = await get_user_lang(user_id)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "DM"

        proj = await db.fetchone("SELECT name FROM projects WHERE project_id = $1", project_id)
        if not proj:
            await interaction.response.send_message(f"❌ ไม่พบโปรเจกต์ #{project_id}", ephemeral=True)
            return

        await engine.upsert_project_sla_policy(
            project_id=project_id,
            guild_id=guild_id,
            p7_hours=p7_hours,
            p6_hours=p6_hours,
            p5_hours=p5_hours,
            p4_hours=p4_hours,
        )

        msg = t("sla_config_updated", lang, project_name=proj.get("name", f"#{project_id}"))
        await interaction.response.send_message(msg)

    @sla.command(
        name="status",
        description="📊 ดูแดชบอร์ดความสอดคล้องตามข้อตกลง SLA / View project SLA compliance dashboard",
    )
    @app_commands.describe(project_id="รหัสโปรเจกต์ / Project ID")
    async def sla_status_cmd(self, interaction: discord.Interaction, project_id: int) -> None:
        user_id = str(interaction.user.id)
        await ensure_user(user_id, interaction.user.name)

        proj = await db.fetchone("SELECT name FROM projects WHERE project_id = $1", project_id)
        if not proj:
            await interaction.response.send_message(f"❌ ไม่พบโปรเจกต์ #{project_id}", ephemeral=True)
            return

        status_data = await engine.get_sla_status(project_id)
        embed = build_sla_status_embed(proj.get("name", f"Project #{project_id}"), status_data)
        await interaction.response.send_message(embed=embed)

    @sla.command(
        name="breaches",
        description="💥 รายงานงานที่ผิดข้อตกลง SLA / View breached SLA tasks",
    )
    @app_commands.describe(project_id="รหัสโปรเจกต์ (เว้นว่างเพื่อดูทั้งเซิร์ฟเวอร์) / Optional Project ID")
    async def sla_breaches_cmd(
        self,
        interaction: discord.Interaction,
        project_id: Optional[int] = None,
    ) -> None:
        user_id = str(interaction.user.id)
        await ensure_user(user_id, interaction.user.name)
        guild_id = str(interaction.guild_id) if interaction.guild_id else "DM"

        breaches = await engine.get_sla_breaches(guild_id, project_id)
        embed = build_sla_breaches_embed(breaches, interaction.guild.name if interaction.guild else "Direct Messages")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutomationCog(bot))

