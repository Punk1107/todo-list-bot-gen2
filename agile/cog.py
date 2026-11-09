"""
agile/cog.py — Discord Slash Command Groups for Agile & Scrum Full Suite.

Commands:
  /sprint create       — สร้าง Sprint ใหม่ในโปรเจกต์
  /sprint start        — เริ่มต้น Sprint (Active ได้ทีละ 1 Sprint ต่อโปรเจกต์)
  /sprint close        — ปิด Sprint พร้อมคำนวณและย้ายงานค้างเข้า Backlog
  /sprint view         — ดู Dashboard รายละเอียดของ Sprint
  /sprint backlog      — ดู Backlog งานที่ยังไม่ถูกดึงเข้า Sprint
  /sprint velocity     — คำนวณความเร็วเฉลี่ย (Velocity) และพยากรณ์รอบการเคลียร์ Backlog
  /sprint retro        — เปิดบอร์ด Sprint Retrospective พร้อมระบบ Dot Voting (3 โหวต/คน)
  /sprint set-points   — กำหนด Story Points (ลำดับ Fibonacci: 1, 2, 3, 5, 8, 13, 21)
  /sprint assign       — ดึง Task เข้าสู่ Sprint
  /poker start         — ประชุมประเมิน Story Points ด้วย Interactive Planning Poker (โหวตลับ)
  /epic create         — สร้าง Epic ใหม่สำหรับแบ่งกลุ่มงานระดับสูง
  /epic list           — แสดงรายชื่อ Epics ทั้งหมดในโปรเจกต์
  /epic attach         — แนบ Task เข้ากับ Epic
  /epic view           — ดูโครงสร้างลำดับชั้นงาน (Epic -> Task -> Subtasks) และ % ความคืบหน้า
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from agile import service
from agile.models import FIBONACCI_POINTS
from agile.views import (
    PlanningPokerView,
    RetroBoardView,
    SprintCloseConfirmView,
    build_epic_embed,
    build_poker_embed,
    build_retro_embed,
    build_sprint_embed,
    build_velocity_embed,
)
from collaboration import service as collab_service
from core.database import db
from core.security import rate_limit_check
from locales.i18n import t
from utils.helpers import ensure_user, get_user_lang
from visualization import (
    render_block_sparkline,
    render_braille_sparkline,
    render_braille_wave,
    render_burndown_chart,
    render_cfd_chart,
    render_velocity_chart,
)
from visualization import service as viz_service

log = logging.getLogger(__name__)


async def _guild_only(interaction: discord.Interaction, lang: str = "th") -> bool:
    """Ensure command is run inside a guild."""
    if not interaction.guild:
        await interaction.response.send_message(t("proj_guild_only", lang), ephemeral=True)
        return False
    return True


def _is_admin(interaction: discord.Interaction) -> bool:
    """Check if member has guild administrator privileges."""
    if isinstance(interaction.user, discord.Member):
        return interaction.user.guild_permissions.administrator
    return False


class AgileCog(commands.Cog, name="Agile"):
    """Agile & Scrum Full Suite Cog for Discord."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    sprint = app_commands.Group(
        name="sprint",
        description="🏉 Agile Sprint Lifecycle, Story Points & Retrospective",
    )

    poker = app_commands.Group(
        name="poker",
        description="🃏 Interactive Planning Poker for Story Points estimation",
    )

    epic = app_commands.Group(
        name="epic",
        description="👑 Epics & Multi-tier Task Hierarchy management",
    )

    # ─────────────────────────────────────────────────────────────────────────
    # /sprint create
    # ─────────────────────────────────────────────────────────────────────────

    @sprint.command(name="create", description="สร้าง Sprint ใหม่ในโปรเจกต์ / Create a new sprint")
    @app_commands.describe(
        project_id="Project ID",
        name="ชื่อ Sprint เช่น Sprint 1 หรือ Release v2.0",
        duration="ระยะเวลาในหน่วยวัน (default: 14 วัน)",
        goal="เป้าหมายหลักของ Sprint (Optional)",
    )
    @rate_limit_check("command")
    async def sprint_create(
        self,
        interaction: discord.Interaction,
        project_id: int,
        name: str,
        duration: Optional[int] = 14,
        goal: Optional[str] = None,
    ) -> None:
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

        is_admin = _is_admin(interaction)
        role = await collab_service.get_member_role(project_id, uid)
        if not (is_admin or role in ("owner", "lead", "member")):
            await interaction.followup.send("❌ คุณต้องเป็นสมาชิกในโปรเจกต์นี้จึงจะสร้าง Sprint ได้", ephemeral=True)
            return

        duration_days = duration if duration and duration > 0 else 14
        try:
            sprint_obj = await service.create_sprint(
                project_id=project_id,
                name=name,
                goal=goal,
                duration_days=duration_days,
            )
            embed = build_sprint_embed(sprint_obj, lang)
            await interaction.followup.send(
                t("sprint_created", lang, sprint_id=sprint_obj.sprint_id),
                embed=embed,
            )
        except Exception as exc:
            log.error("sprint_create error: %s", exc)
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาดในการสร้าง Sprint: {exc}", ephemeral=True)

    # ─────────────────────────────────────────────────────────────────────────
    # /sprint start
    # ─────────────────────────────────────────────────────────────────────────

    @sprint.command(name="start", description="เริ่มต้น Sprint / Start a planned sprint")
    @app_commands.describe(
        sprint_id="Sprint ID ที่ต้องการเริ่มต้น",
        project_id="Project ID ของโปรเจกต์",
    )
    @rate_limit_check("command")
    async def sprint_start(
        self,
        interaction: discord.Interaction,
        sprint_id: int,
        project_id: int,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await ensure_user(uid, lang)
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        try:
            await collab_service.get_project(project_id, guild_id)
        except collab_service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=project_id), ephemeral=True)
            return

        try:
            sprint_obj = await service.start_sprint(sprint_id, project_id)
            embed = build_sprint_embed(sprint_obj, lang)
            await interaction.followup.send(
                t("sprint_started", lang, sprint_id=sprint_id, name=sprint_obj.name),
                embed=embed,
            )
        except service.SprintAlreadyActiveError as exc:
            await interaction.followup.send(t("sprint_already_active", lang, sprint_id=sprint_id), ephemeral=True)
        except service.SprintNotFoundError as exc:
            await interaction.followup.send(t("sprint_not_found", lang, sprint_id=sprint_id, project_id=project_id), ephemeral=True)
        except Exception as exc:
            log.error("sprint_start error: %s", exc)
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาด: {exc}", ephemeral=True)

    # ─────────────────────────────────────────────────────────────────────────
    # /sprint close
    # ─────────────────────────────────────────────────────────────────────────

    @sprint.command(name="close", description="ปิดรอบ Sprint และย้ายงานที่ยังไม่เสร็จ / Close active sprint")
    @app_commands.describe(
        sprint_id="Sprint ID ที่ต้องการปิด",
        project_id="Project ID ของโปรเจกต์",
    )
    @rate_limit_check("command")
    async def sprint_close(
        self,
        interaction: discord.Interaction,
        sprint_id: int,
        project_id: int,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await ensure_user(uid, lang)

        sprint_obj = await service.get_sprint(sprint_id)
        if not sprint_obj or sprint_obj.project_id != project_id:
            await interaction.response.send_message(f"❌ ไม่พบ Sprint #{sprint_id} ในโปรเจกต์ #{project_id}", ephemeral=True)
            return

        if sprint_obj.is_closed:
            await interaction.response.send_message(f"ℹ️ Sprint #{sprint_id} ถูกปิดไปแล้ว", ephemeral=True)
            return

        view = SprintCloseConfirmView(sprint_id, project_id, lang)
        embed = discord.Embed(
            title=f"🏁 ยืนยันการปิด Sprint #{sprint_id} ({sprint_obj.name})",
            description=(
                f"คุณกำลังจะปิด Sprint นี้\n"
                f"• งานทั้งหมดใน Sprint: `{sprint_obj.total_tasks}` งาน\n"
                f"• เสร็จสิ้นแล้ว: `{sprint_obj.completed_tasks}` งาน ({sprint_obj.completion_pct}%)\n"
                f"• งานที่ยังค้างอยู่: `{sprint_obj.total_tasks - sprint_obj.completed_tasks}` งาน\n\n"
                f"กรุณากดปุ่มด้านล่างเพื่อเลือกวิธีการจัดการงานที่ค้างอยู่:"
            ),
            color=0xFEE75C,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ─────────────────────────────────────────────────────────────────────────
    # /sprint view
    # ─────────────────────────────────────────────────────────────────────────

    @sprint.command(name="view", description="ดูแดชบอร์ดความคืบหน้าของ Sprint / View sprint dashboard")
    @app_commands.describe(sprint_id="Sprint ID")
    @rate_limit_check("command")
    async def sprint_view(self, interaction: discord.Interaction, sprint_id: int) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer()

        sprint_obj = await service.get_sprint(sprint_id)
        if not sprint_obj:
            await interaction.followup.send(f"❌ ไม่พบ Sprint #{sprint_id}", ephemeral=True)
            return

        embed = build_sprint_embed(sprint_obj, lang)
        tasks = await service.get_sprint_tasks(sprint_id)
        if tasks:
            task_lines = []
            for t_item in tasks[:10]:
                status_ico = "✅" if t_item["status"] == "Completed" else ("⚡" if t_item["status"] == "In_Progress" else "📋")
                pts = f"`[{t_item['story_points']} pts]`" if t_item.get("story_points") else ""
                task_lines.append(f"{status_ico} `#{t_item['task_id']}` {t_item['task'][:40]} {pts}")
            if len(tasks) > 10:
                task_lines.append(f"... และอีก {len(tasks) - 10} งาน")
            embed.add_field(name=f"📋 รายการงานใน Sprint ({len(tasks)})", value="\n".join(task_lines), inline=False)

            # Sparkline focus & progress indicator
            completed_cnt = sum(1 for t in tasks if t["status"] == "Completed")
            in_prog_cnt = sum(1 for t in tasks if t["status"] in ("In_Progress", "In Progress"))
            pend_cnt = len(tasks) - completed_cnt - in_prog_cnt
            wave = render_braille_wave(count=8)
            spark = render_block_sparkline([pend_cnt, in_prog_cnt, completed_cnt])
            embed.add_field(
                name="📈 Flow Dynamics",
                value=f"Flow: `{spark}` | Focus: {wave}",
                inline=False,
            )

        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # /sprint burndown
    # ─────────────────────────────────────────────────────────────────────────

    @sprint.command(
        name="burndown",
        description="📉 กราฟ Sprint Burndown Chart แสดงงานที่เหลือเทียบกับเส้นอุดมคติ",
    )
    @app_commands.describe(sprint_id="Sprint ID number")
    @rate_limit_check("command")
    async def sprint_burndown(self, interaction: discord.Interaction, sprint_id: int) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer()

        data = await viz_service.get_sprint_burndown_data(sprint_id)
        if not data:
            await interaction.followup.send(f"❌ ไม่พบ Sprint #{sprint_id}", ephemeral=True)
            return

        buf = render_burndown_chart(
            sprint_name=data["sprint_name"],
            total_points=data["total_points"],
            ideal_burn=data["ideal_burn"],
            actual_burn=data["actual_burn"],
            day_labels=data["day_labels"],
        )
        file = discord.File(fp=buf, filename="burndown.png")
        embed = discord.Embed(
            title=f"📉 Sprint Burndown Chart — {data['sprint_name']}",
            description=(
                f"**Total Scope:** {data['total_points']:.1f} pts\n"
                f"**Current Remaining:** {data['actual_burn'][-1]:.1f} pts\n"
                f"💡 *กราฟเส้นตรง (เทา) คือ Ideal Burn Line และเส้นจุด (เขียว) คือ Actual Remaining*"
            ),
            color=0x57F287,
        )
        embed.set_image(url="attachment://burndown.png")
        await interaction.followup.send(embed=embed, file=file)

    # ─────────────────────────────────────────────────────────────────────────
    # /sprint cfd
    # ─────────────────────────────────────────────────────────────────────────

    @sprint.command(
        name="cfd",
        description="🌊 กราฟ Cumulative Flow Diagram (CFD) วิเคราะห์จุดคอขวดของงาน",
    )
    @app_commands.describe(sprint_id="Sprint ID number")
    @rate_limit_check("command")
    async def sprint_cfd(self, interaction: discord.Interaction, sprint_id: int) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer()

        data = await viz_service.get_sprint_cfd_data(sprint_id)
        if not data:
            await interaction.followup.send(f"❌ ไม่พบ Sprint #{sprint_id}", ephemeral=True)
            return

        buf = render_cfd_chart(
            title=data["title"],
            dates=data["dates"],
            pending_series=data["pending_series"],
            in_progress_series=data["in_progress_series"],
            completed_series=data["completed_series"],
        )
        file = discord.File(fp=buf, filename="cfd.png")
        embed = discord.Embed(
            title=f"🌊 Cumulative Flow Diagram — {data['title']}",
            description="วิเคราะห์ Work In Progress (WIP) และการสะสมงานในแต่ละสถานะ",
            color=0x5865F2,
        )
        embed.set_image(url="attachment://cfd.png")
        await interaction.followup.send(embed=embed, file=file)

    # ─────────────────────────────────────────────────────────────────────────
    # /sprint backlog
    # ─────────────────────────────────────────────────────────────────────────

    @sprint.command(name="backlog", description="ดู Backlog งานที่ยังไม่ได้ดึงเข้า Sprint / View project backlog")
    @app_commands.describe(project_id="Project ID")
    @rate_limit_check("command")
    async def sprint_backlog(self, interaction: discord.Interaction, project_id: int) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        try:
            project = await collab_service.get_project(project_id, guild_id)
        except collab_service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=project_id), ephemeral=True)
            return

        backlog_tasks = await service.get_sprint_backlog(project_id)
        embed = discord.Embed(
            title=f"📦 Product Backlog: {project.emoji} {project.name} (#{project_id})",
            description=f"งานที่เปิดอยู่ทั้งหมดที่ยังไม่ถูกมอบหมายเข้า Sprint (`sprint_id IS NULL`)",
            color=0x5865F2,
        )
        if not backlog_tasks:
            embed.description += "\n\n*🎉 ยอดเยี่ยมมาก! ไม่มีงานค้างใน Backlog เลย*"
        else:
            lines = []
            total_points = 0
            for t_item in backlog_tasks[:15]:
                pts = t_item.get("story_points")
                if pts:
                    total_points += int(pts)
                    pts_str = f"`[{pts} pts]`"
                else:
                    pts_str = "`[- pts]`"
                lines.append(f"• `#{t_item['task_id']}` {t_item['task'][:45]} {pts_str}")
            if len(backlog_tasks) > 15:
                lines.append(f"... และอีก {len(backlog_tasks) - 15} งาน")
            embed.add_field(name=f"📋 รายการงาน ({len(backlog_tasks)} งาน · รวม {total_points} แต้ม)", value="\n".join(lines), inline=False)

        embed.set_footer(text=f"ใช้ `/sprint assign` เพื่อดึงงานเข้า Sprint")
        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # /sprint velocity
    # ─────────────────────────────────────────────────────────────────────────

    @sprint.command(name="velocity", description="วิเคราะห์ Team Velocity และพยากรณ์การเคลียร์ Backlog")
    @app_commands.describe(project_id="Project ID")
    @rate_limit_check("command")
    async def sprint_velocity(self, interaction: discord.Interaction, project_id: int) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        try:
            await collab_service.get_project(project_id, guild_id)
        except collab_service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=project_id), ephemeral=True)
            return

        stats = await service.get_velocity_stats(project_id)
        embed = build_velocity_embed(stats, lang)

        vel_data = await viz_service.get_project_velocity_history(project_id)
        if vel_data.get("sprint_names"):
            buf = render_velocity_chart(
                project_name=vel_data["project_name"],
                sprint_names=vel_data["sprint_names"],
                planned_points=vel_data["planned_points"],
                completed_points=vel_data["completed_points"],
            )
            file = discord.File(fp=buf, filename="velocity.png")
            embed.set_image(url="attachment://velocity.png")
            await interaction.followup.send(embed=embed, file=file)
        else:
            await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # /sprint retro
    # ─────────────────────────────────────────────────────────────────────────

    @sprint.command(name="retro", description="เปิดบอร์ด Sprint Retrospective และระบบ Dot Voting")
    @app_commands.describe(
        sprint_id="Sprint ID",
        project_id="Project ID",
    )
    @rate_limit_check("command")
    async def sprint_retro(
        self,
        interaction: discord.Interaction,
        sprint_id: int,
        project_id: int,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await ensure_user(uid, lang)
        await interaction.response.defer()

        sprint_obj = await service.get_sprint(sprint_id)
        if not sprint_obj or sprint_obj.project_id != project_id:
            await interaction.followup.send(f"❌ ไม่พบ Sprint #{sprint_id} ในโปรเจกต์ #{project_id}", ephemeral=True)
            return

        board = await service.get_retro_board(sprint_id)
        embed = build_retro_embed(sprint_id, board, lang, user_id=uid)
        view = RetroBoardView(sprint_id, project_id, lang)
        await interaction.followup.send(embed=embed, view=view)

    # ─────────────────────────────────────────────────────────────────────────
    # /sprint set-points
    # ─────────────────────────────────────────────────────────────────────────

    @sprint.command(name="set-points", description="กำหนด Story Points (ลำดับ Fibonacci 1,2,3,5,8,13,21)")
    @app_commands.describe(
        task_id="Task ID number",
        points="ลำดับคะแนน Fibonacci",
    )
    @app_commands.choices(points=[
        app_commands.Choice(name="1 pt (ง่ายมาก / Trivial)", value=1),
        app_commands.Choice(name="2 pts (ง่าย / Simple)", value=2),
        app_commands.Choice(name="3 pts (ปานกลาง / Medium)", value=3),
        app_commands.Choice(name="5 pts (ท้าทาย / Significant)", value=5),
        app_commands.Choice(name="8 pts (ซับซ้อน / Complex)", value=8),
        app_commands.Choice(name="13 pts (ใหญ่มาก / Large Epic)", value=13),
        app_commands.Choice(name="21 pts (วิกฤตความยาก / Huge)", value=21),
    ])
    @rate_limit_check("command")
    async def sprint_set_points(
        self,
        interaction: discord.Interaction,
        task_id: int,
        points: int,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)

        try:
            ok = await service.set_task_story_points(task_id, points)
            if ok:
                await interaction.followup.send(f"✅ บันทึก Story Points ให้กับงาน `#{task_id}` เป็น **{points} คะแนน** สำเร็จ!", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ ไม่พบงาน `#{task_id}`", ephemeral=True)
        except service.InvalidStoryPointError as exc:
            await interaction.followup.send(f"⚠️ {exc}", ephemeral=True)
        except Exception as exc:
            log.error("sprint_set_points error: %s", exc)
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาด: {exc}", ephemeral=True)

    # ─────────────────────────────────────────────────────────────────────────
    # /sprint assign
    # ─────────────────────────────────────────────────────────────────────────

    @sprint.command(name="assign", description="ดึง Task เข้าสู่ Sprint / Attach task to a sprint")
    @app_commands.describe(
        task_id="Task ID number",
        sprint_id="Sprint ID",
        project_id="Project ID",
    )
    @rate_limit_check("command")
    async def sprint_assign(
        self,
        interaction: discord.Interaction,
        task_id: int,
        sprint_id: int,
        project_id: int,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)

        sprint_obj = await service.get_sprint(sprint_id)
        if not sprint_obj or sprint_obj.project_id != project_id:
            await interaction.followup.send(f"❌ ไม่พบ Sprint #{sprint_id} ในโปรเจกต์ #{project_id}", ephemeral=True)
            return

        ok = await service.add_task_to_sprint(task_id, sprint_id, project_id)
        if ok:
            await interaction.followup.send(f"✅ ดึงงาน `#{task_id}` เข้าสู่ **Sprint #{sprint_id} ({sprint_obj.name})** สำเร็จ!", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ ไม่พบงาน `#{task_id}` ในโปรเจกต์ #{project_id}", ephemeral=True)

    # ─────────────────────────────────────────────────────────────────────────
    # /poker start
    # ─────────────────────────────────────────────────────────────────────────

    @poker.command(name="start", description="เริ่มห้องประชุมประเมินคะแนน Planning Poker แบบเรียลไทม์")
    @app_commands.describe(task_id="Task ID number ที่ต้องการประเมินแต้ม")
    @rate_limit_check("command")
    async def poker_start(self, interaction: discord.Interaction, task_id: int) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await ensure_user(uid, lang)
        await interaction.response.defer()

        row = await db.fetchone(
            "SELECT task_id, task, project_id FROM tasks WHERE task_id = $1 AND is_deleted = FALSE",
            (task_id,),
        )
        if not row:
            await interaction.followup.send(f"❌ ไม่พบงาน `#{task_id}`", ephemeral=True)
            return

        task_title = row["task"]
        session = service.start_poker(task_id, uid, task_title)
        embed = build_poker_embed(session, lang)
        view = PlanningPokerView(task_id, uid, lang)
        await interaction.followup.send(embed=embed, view=view)

    # ─────────────────────────────────────────────────────────────────────────
    # /epic create
    # ─────────────────────────────────────────────────────────────────────────

    @epic.command(name="create", description="สร้าง Epic ใหม่สำหรับโครงสร้างงานระดับสูง / Create an Epic")
    @app_commands.describe(
        project_id="Project ID number",
        name="ชื่อ Epic เช่น Authentication System หรือ Payment Gateway",
        description="คำอธิบายขอบเขตของ Epic (Optional)",
        color="Hex color code เช่น #5865F2 (Optional)",
    )
    @rate_limit_check("command")
    async def epic_create(
        self,
        interaction: discord.Interaction,
        project_id: int,
        name: str,
        description: Optional[str] = None,
        color: Optional[str] = None,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await ensure_user(uid, lang)
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        try:
            await collab_service.get_project(project_id, guild_id)
        except collab_service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=project_id), ephemeral=True)
            return

        try:
            epic_obj = await service.create_epic(
                project_id=project_id,
                name=name,
                description=description,
                color=color,
            )
            embed = build_epic_embed(epic_obj, [], lang)
            await interaction.followup.send(
                f"👑 สร้าง Epic **#{epic_obj.epic_id} ({epic_obj.name})** สำเร็จ!",
                embed=embed,
            )
        except Exception as exc:
            log.error("epic_create error: %s", exc)
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาดในการสร้าง Epic: {exc}", ephemeral=True)

    # ─────────────────────────────────────────────────────────────────────────
    # /epic list
    # ─────────────────────────────────────────────────────────────────────────

    @epic.command(name="list", description="ดูรายชื่อ Epics ทั้งหมดในโปรเจกต์ / List epics in project")
    @app_commands.describe(project_id="Project ID number")
    @rate_limit_check("command")
    async def epic_list(self, interaction: discord.Interaction, project_id: int) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer()

        guild_id = str(interaction.guild.id)
        try:
            project = await collab_service.get_project(project_id, guild_id)
        except collab_service.ProjectNotFound:
            await interaction.followup.send(t("proj_not_found", lang, project_id=project_id), ephemeral=True)
            return

        epics = await service.get_project_epics(project_id)
        embed = discord.Embed(
            title=f"👑 Epics: {project.emoji} {project.name} (#{project_id})",
            color=0x5865F2,
        )
        if not epics:
            embed.description = "*ยังไม่มี Epic ในโปรเจกต์นี้ สร้างได้ด้วย `/epic create`*"
        else:
            lines = []
            for ep in epics:
                status_ico = "🟢" if ep.status == "in_progress" else ("✅" if ep.status == "completed" else "📋")
                lines.append(
                    f"{status_ico} **`#{ep.epic_id}` {ep.name}** · `{ep.progress_pct}%` "
                    f"({ep.completed_tasks}/{ep.total_tasks} Tasks · {ep.completed_points}/{ep.total_points} Pts)"
                )
            embed.description = "\n".join(lines)

        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # /epic attach
    # ─────────────────────────────────────────────────────────────────────────

    @epic.command(name="attach", description="ผูก Task เข้ากับ Epic / Attach a task to an epic")
    @app_commands.describe(
        task_id="Task ID number",
        epic_id="Epic ID number",
        project_id="Project ID number",
    )
    @rate_limit_check("command")
    async def epic_attach(
        self,
        interaction: discord.Interaction,
        task_id: int,
        epic_id: int,
        project_id: int,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await ensure_user(uid, lang)
        await interaction.response.defer(ephemeral=True)

        try:
            ok = await service.attach_task_to_epic(task_id, epic_id, project_id)
            if ok:
                await interaction.followup.send(f"✅ ผูกงาน `#{task_id}` เข้ากับ **Epic #{epic_id}** สำเร็จ!", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ ไม่พบงาน `#{task_id}` หรือ Epic `#{epic_id}` ในโปรเจกต์ #{project_id}", ephemeral=True)
        except service.EpicNotFoundError as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
        except Exception as exc:
            log.error("epic_attach error: %s", exc)
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาด: {exc}", ephemeral=True)

    # ─────────────────────────────────────────────────────────────────────────
    # /epic view
    # ─────────────────────────────────────────────────────────────────────────

    @epic.command(name="view", description="ดูลำดับชั้นงาน (Epic Tree) และความคืบหน้า / View epic hierarchy tree")
    @app_commands.describe(epic_id="Epic ID number")
    @rate_limit_check("command")
    async def epic_view(self, interaction: discord.Interaction, epic_id: int) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        if not await _guild_only(interaction, lang):
            return
        await interaction.response.defer()

        epic_obj = await service.get_epic(epic_id)
        if not epic_obj:
            await interaction.followup.send(f"❌ ไม่พบ Epic #{epic_id}", ephemeral=True)
            return

        tasks = await service.get_epic_tasks_tree(epic_id)
        embed = build_epic_embed(epic_obj, tasks, lang)
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Setup hook to register Agile Cog."""
    await bot.add_cog(AgileCog(bot))

