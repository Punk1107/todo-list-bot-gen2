"""
cpm_roadmap/cog.py — Discord Slash Commands for Strategic Roadmap & Health Predictor.

Commands:
  /roadmap view project_id:[id]       — ดูแผนผังยุทธศาสตร์พร้อมสถานะสุขภาพ (On Track / At Risk / Delayed)
  /roadmap create project_id:[id]     — สร้าง Milestone เชิงยุทธศาสตร์ใหม่ (ผ่าน Modal)
  /roadmap attach task_id:[id] ...    — ผูก Task เข้ากับ Milestone
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands

from collaboration import service as collab_service
from core.security import rate_limit_check
from cpm_roadmap import cpm_engine, gantt_renderer, roadmap_service
from cpm_roadmap.models import MilestoneHealth
from cpm_roadmap.views import (
    GanttSwitchView,
    MilestoneCreateModal,
    build_cpm_embed,
    build_gantt_embed,
    build_roadmap_embed,
)
from locales.i18n import t
from utils.helpers import ensure_user, get_user_lang

log = logging.getLogger(__name__)


async def _guild_only(interaction: discord.Interaction, lang: str = "th") -> bool:
    """Ensure interaction is run inside a guild."""
    if not interaction.guild:
        await interaction.response.send_message(t("proj_guild_only", lang), ephemeral=True)
        return False
    return True


class RoadmapCog(commands.Cog, name="Strategic Roadmap"):
    """Strategic Milestone Roadmap & Health Predictor Cog."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    roadmap = app_commands.Group(
        name="roadmap",
        description="🗺️ Strategic Milestone Roadmap & Health Predictor",
    )

    # ─────────────────────────────────────────────────────────────────────────
    # /roadmap view
    # ─────────────────────────────────────────────────────────────────────────

    @roadmap.command(name="view", description="ดูแผนผัง Roadmap เชิงยุทธศาสตร์และสถานะสุขภาพโครงการ")
    @app_commands.describe(project_id="Project ID number")
    @rate_limit_check("command")
    async def roadmap_view(self, interaction: discord.Interaction, project_id: int) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await ensure_user(uid, lang)
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        try:
            project = await collab_service.get_project(project_id, guild_id)
        except collab_service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=project_id), ephemeral=True)
            return

        milestones = await roadmap_service.get_project_milestones(project_id)
        health_map: Dict[int, MilestoneHealth] = {}
        for m in milestones:
            try:
                h = await roadmap_service.predict_milestone_health(m.milestone_id)
                health_map[m.milestone_id] = h
            except Exception as exc:
                log.warning("Could not predict health for milestone %d: %s", m.milestone_id, exc)

        embed = build_roadmap_embed(
            project_name=f"{project.emoji} {project.name}",
            project_id=project_id,
            milestones=milestones,
            health_map=health_map,
            lang=lang,
        )
        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # /roadmap create
    # ─────────────────────────────────────────────────────────────────────────

    @roadmap.command(name="create", description="สร้าง Strategic Milestone ใหม่ในโครงการ")
    @app_commands.describe(project_id="Project ID number")
    @rate_limit_check("command")
    async def roadmap_create(self, interaction: discord.Interaction, project_id: int) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await ensure_user(uid, lang)

        guild_id = str(interaction.guild.id)
        try:
            await collab_service.get_project(project_id, guild_id)
        except collab_service.ProjectNotFound:
            await interaction.response.send_message(t("proj_not_found", lang, project_id=project_id), ephemeral=True)
            return

        modal = MilestoneCreateModal(project_id, lang)
        await interaction.response.send_modal(modal)

    # ─────────────────────────────────────────────────────────────────────────
    # /roadmap attach
    # ─────────────────────────────────────────────────────────────────────────

    @roadmap.command(name="attach", description="ผูก Task เข้ากับ Milestone / Attach task to a milestone")
    @app_commands.describe(
        task_id="Task ID number",
        milestone_id="Milestone ID number",
        project_id="Project ID number",
    )
    @rate_limit_check("command")
    async def roadmap_attach(
        self,
        interaction: discord.Interaction,
        task_id: int,
        milestone_id: int,
        project_id: int,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)

        milestone = await roadmap_service.get_milestone(milestone_id)
        if not milestone or milestone.project_id != project_id:
            await interaction.followup.send(f"❌ ไม่พบ Milestone #{milestone_id} ในโครงการ #{project_id}", ephemeral=True)
            return

        ok = await roadmap_service.attach_task_to_milestone(task_id, milestone_id, project_id)
        if ok:
            await interaction.followup.send(
                t("milestone_attached", lang, task_id=task_id, milestone_id=milestone_id, title=milestone.title),
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"❌ #{task_id}",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    """Setup hook to register Roadmap Cog."""
    await bot.add_cog(RoadmapCog(bot))

