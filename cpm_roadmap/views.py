"""
cpm_roadmap/views.py — Discord UI Views, Embed Builders, and Modals for CPM, Gantt & Roadmaps.
"""
from __future__ import annotations

from datetime import datetime, timezone
import io
import logging
from typing import Any, Dict, List, Optional

import discord
from discord import ui

from cpm_roadmap import gantt_renderer, roadmap_service
from cpm_roadmap.models import CPMGraphResult, HealthStatus, MilestoneHealth, ProjectMilestone
from locales.i18n import t

log = logging.getLogger(__name__)


def _progress_bar(pct: int, length: int = 10) -> str:
    """Format ASCII/Emoji progress bar."""
    pct = max(0, min(100, int(pct)))
    filled = int(round(length * pct / 100))
    empty = length - filled
    return f"`[{'█' * filled}{'░' * empty}]` **{pct}%**"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Embed Builders
# ─────────────────────────────────────────────────────────────────────────────

def build_cpm_embed(result: CPMGraphResult, project_name: str, lang: str = "th") -> discord.Embed:
    """Build the Critical Path Method analysis embed."""
    color = 0xED4245 if result.is_at_risk else 0x5865F2
    embed = discord.Embed(
        title=f"🕸️ Critical Path Method (CPM): {project_name}",
        color=color,
    )

    if result.has_cycle:
        embed.description = (
            "❌ **ตรวจพบ Circular Dependency (ความสัมพันธ์วนลูป)**\n"
            "งานในโครงการมีการตั้งเงื่อนไขรองรับกันเป็นวงกลม (A ➔ B ➔ A) "
            "ทำให้ไม่สามารถคำนวณสายงานวิกฤตได้ กรุณาตรวจสอบ Task Dependencies"
        )
        return embed

    crit_count = len(result.critical_path)
    embed.description = (
        f"**ระยะเวลาโครงการรวม:** `⏱️ {result.total_duration_days} วัน` ({result.total_duration_hours} ชั่วโมงทำงาน)\n"
        f"**จำนวนงานบน Critical Path:** `{crit_count}` งาน (งานที่ห้ามช้าเด็ดขาด)\n"
    )

    # Lead Risk Warning Alert
    if result.is_at_risk and result.risk_reason:
        embed.add_field(
            name="🚨 คำเตือนความเสี่ยงโครงการ (Lead Alert)",
            value=result.risk_reason,
            inline=False,
        )

    # Critical Path Sequence
    if result.critical_path:
        path_str = " ➔ ".join(f"`#{tid}`" for tid in result.critical_path)
        embed.add_field(name="🎯 ลำดับสายงานวิกฤต (Critical Path Sequence)", value=path_str, inline=False)

        # Critical tasks details
        crit_lines = []
        for tid in result.critical_path:
            node = result.nodes[tid]
            crit_lines.append(
                f"• `#{node.task_id}` **{node.task_name[:35]}** "
                f"({node.duration_days}d) | ES:`{node.early_start}h` ➔ EF:`{node.early_finish}h`"
            )
        embed.add_field(name="🚨 รายละเอียดงานบนสายงานวิกฤต", value="\n".join(crit_lines[:8]), inline=False)

    # Non-critical tasks with Slack (Float Time)
    non_crit = [n for n in result.nodes.values() if not n.is_critical]
    if non_crit:
        non_crit_sorted = sorted(non_crit, key=lambda x: x.slack, reverse=True)
        slack_lines = []
        for n in non_crit_sorted[:6]:
            slack_days = round(n.slack / 8.0, 1)
            slack_lines.append(f"• `#{n.task_id}` {n.task_name[:30]}: มีเวลาเผื่อ **+{slack_days} วัน** (`{n.slack}h`)")
        embed.add_field(name="⏳ งานที่มีเวลาเผื่อ (Float / Slack Time)", value="\n".join(slack_lines), inline=False)

    embed.set_footer(text=f"Project #{result.project_id} · Formula: Slack = LS - ES = LF - EF (Critical if Slack=0)")
    return embed


def build_gantt_embed(ascii_text: str, project_name: str, lang: str = "th") -> discord.Embed:
    """Build the ASCII Gantt Chart codeblock embed."""
    embed = discord.Embed(
        title=f"📊 In-Discord Gantt Chart: {project_name}",
        description=f"```text\n{ascii_text}\n```",
        color=0x5865F2,
    )
    embed.set_footer(text="คลิกปุ่ม '🖼️ High-Res PNG' เพื่อรับรูปภาพความละเอียดสูงพร้อมลูกศร Dependencies")
    return embed


def build_roadmap_embed(
    project_name: str,
    project_id: int,
    milestones: List[ProjectMilestone],
    health_map: Dict[int, MilestoneHealth],
    lang: str = "th",
) -> discord.Embed:
    """Build the Strategic Milestone Roadmap & Health Predictor embed."""
    embed = discord.Embed(
        title=f"🗺️ Strategic Milestone Roadmap: {project_name} (#{project_id})",
        description="แผนผังไทม์ไลน์เชิงยุทธศาสตร์และระบบทำนายสุขภาพโครงการแบบเรียลไทม์",
        color=0x5865F2,
    )

    if not milestones:
        embed.description += "\n\n*ยังไม่มี Milestone ในโครงการนี้ สร้างได้ด้วยคำสั่ง `/roadmap create`*"
        return embed

    for m in milestones:
        health = health_map.get(m.milestone_id)
        status_badge = health.status.emoji if health else "⚪"
        status_label = health.status.label_th if health else "ไม่ทราบสถานะ"
        ts = int(m.target_date.timestamp())

        field_title = f"{status_badge} Milestone: {m.title} (#{m.milestone_id})"
        val_lines = [
            f"🎯 **วันส่งมอบ:** <t:{ts}:D> (<t:{ts}:R>)",
            f"📊 **ความคืบหน้า:** {_progress_bar(m.completion_pct)} ({m.completed_tasks}/{m.total_tasks} Tasks)",
            f"🩺 **สถานะสุขภาพ:** `{status_label}`",
        ]

        if health:
            val_lines.append(f"⏱️ **เวลาที่ผ่านไป:** `{health.elapsed_pct}%` · **ส่วนต่าง (Gap):** `{health.gap_pct}%`")
            val_lines.append(f"💡 **คำแนะนำ:** *{health.recommendation}*")

            # Bottleneck alerts for At Risk or Delayed
            if health.status in (HealthStatus.AT_RISK, HealthStatus.DELAYED) and health.bottleneck_tasks:
                b_lines = []
                for b in health.bottleneck_tasks[:3]:
                    b_lines.append(f"  ⚠️ `#{b['task_id']}` {b['task'][:30]} (บล็อกงานอื่น {b.get('blocked_dependents_count', 0)} งาน)")
                val_lines.append("**งานคอขวดที่ต้องแก้ไขด่วน (Bottlenecks):**\n" + "\n".join(b_lines))

        embed.add_field(name=field_title, value="\n".join(val_lines), inline=False)

    embed.set_footer(text=f"Health Thresholds: 🟢 On Track (<10% lag) · 🟡 At Risk (10-25% lag) · 🔴 Delayed (>25% lag)")
    return embed


# ─────────────────────────────────────────────────────────────────────────────
# 2. Interactive Views & Modals
# ─────────────────────────────────────────────────────────────────────────────

class GanttSwitchView(ui.View):
    """View allowing switching between ASCII Embed View and High-Res Pillow PNG."""

    def __init__(self, cpm_result: CPMGraphResult, project_name: str) -> None:
        super().__init__(timeout=300)
        self.cpm_result = cpm_result
        self.project_name = project_name

    @ui.button(label="🖼️ High-Res PNG Chart", style=discord.ButtonStyle.primary, row=0)
    async def btn_png(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            buf = gantt_renderer.render_png_gantt(self.cpm_result, self.project_name)
            file = discord.File(fp=buf, filename=f"gantt_proj_{self.cpm_result.project_id}.png")
            await interaction.followup.send(
                content=f"📊 **High-Res Gantt Chart for {self.project_name}** (100% In-Memory Pure Pillow Render):",
                file=file,
                ephemeral=True,
            )
        except Exception as exc:
            log.warning("Gantt PNG render failed: %s", exc)
            await interaction.followup.send(
                f"⚠️ ไม่สามารถเรนเดอร์รูปภาพ Gantt ได้: {exc}",
                ephemeral=True,
            )

    @ui.button(label="🕸️ View Critical Path", style=discord.ButtonStyle.secondary, row=0)
    async def btn_cpm(self, interaction: discord.Interaction, button: ui.Button) -> None:
        embed = build_cpm_embed(self.cpm_result, self.project_name)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class MilestoneCreateModal(ui.Modal):
    """Modal for creating a new Strategic Milestone."""

    def __init__(self, project_id: int, lang: str = "th") -> None:
        super().__init__(title="🎯 Create Strategic Milestone")
        self.project_id = project_id
        self.lang = lang

        self.title_input = ui.TextInput(
            label="Milestone Title",
            placeholder="e.g. Q1 Beta Release, MVP Launch, Mobile App v1.0",
            max_length=100,
            required=True,
        )
        self.date_input = ui.TextInput(
            label="Target Date (YYYY-MM-DD)",
            placeholder="e.g. 2026-12-31 or 2027-03-31",
            max_length=10,
            required=True,
        )
        self.add_item(self.title_input)
        self.add_item(self.date_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        title = self.title_input.value.strip()
        date_str = self.date_input.value.strip()

        try:
            target_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            await interaction.response.send_message("❌ รูปแบบวันที่ไม่ถูกต้อง กรุณาใช้รูปแบบ `YYYY-MM-DD` เช่น `2026-12-31`", ephemeral=True)
            return

        try:
            ms = await roadmap_service.create_milestone(self.project_id, title, target_dt)
            ts = int(target_dt.timestamp())
            await interaction.response.send_message(
                f"{t('milestone_created', self.lang, milestone_id=ms.milestone_id, title=ms.title)}\n"
                f"🎯 วันส่งมอบ: <t:{ts}:D> (<t:{ts}:R>)\n"
                f"ผูกงานเข้ากับ Milestone นี้ได้ด้วยคำสั่ง `/roadmap attach`",
                ephemeral=False,
            )
        except Exception as exc:
            log.error("MilestoneCreateModal error: %s", exc)
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาดในการสร้าง Milestone: {exc}", ephemeral=True)

