"""
time_tracking/views.py — Discord UI Views, Buttons and Embeds for Time Tracking Engine.
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

import discord

from locales.i18n import t
from time_tracking.models import (
    ActiveTimer,
    CapacityMetric,
    EstimationMetric,
    ProjectBudgetMetric,
    TimeLogEntry,
    TimesheetSummary,
)
from time_tracking import service


def _make_progress_bar(pct: float, total_blocks: int = 10) -> str:
    """Generate visual ASCII progress bar."""
    filled = max(0, min(total_blocks, int(round((pct / 100.0) * total_blocks))))
    empty = total_blocks - filled
    return f"`[{'█' * filled}{'░' * empty}]` {pct:.1f}%"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Timesheet Embed & Export View
# ─────────────────────────────────────────────────────────────────────────────

def build_timesheet_embed(
    user_name: str,
    timesheet: TimesheetSummary,
    lang: str = "th",
) -> discord.Embed:
    """Build summary embed for user timesheet."""
    embed = discord.Embed(
        title=f"⏱️ {t('time_timesheet_title', lang)} — {user_name} ({timesheet.period.upper()})",
        color=0x3498DB,
    )
    embed.add_field(
        name="📊 Total Logged",
        value=f"**{timesheet.total_hours:.2f}** hrs",
        inline=True,
    )
    embed.add_field(
        name="💼 Billable",
        value=f"**{timesheet.billable_hours:.2f}** hrs",
        inline=True,
    )
    embed.add_field(
        name="☕ Non-Billable",
        value=f"**{timesheet.non_billable_hours:.2f}** hrs",
        inline=True,
    )

    if timesheet.project_hours:
        proj_lines = [f"• **{p}**: `{h:.2f}` hrs" for p, h in sorted(timesheet.project_hours.items(), key=lambda x: x[1], reverse=True)[:5]]
        embed.add_field(
            name="📁 By Project",
            value="\n".join(proj_lines),
            inline=False,
        )

    if timesheet.entries:
        recent_lines = []
        for e in timesheet.entries[:5]:
            note_str = f" — *{e.note[:30]}*" if e.note else ""
            bill_badge = "💼" if e.is_billable else "☕"
            recent_lines.append(f"{bill_badge} **#{e.task_id}** (`{e.hours_spent:.2f}h`){note_str}")
        embed.add_field(
            name="📝 Recent Activity",
            value="\n".join(recent_lines),
            inline=False,
        )
    else:
        embed.description = "📭 No time logs recorded for this period."

    embed.set_footer(text=f"Total records: {len(timesheet.entries)} · To-Do List Bot Gen 5.0")
    return embed


class TimesheetExportView(discord.ui.View):
    """View with button to export timesheet as CSV file."""

    def __init__(self, timesheet: TimesheetSummary, user_name: str, lang: str = "th") -> None:
        super().__init__(timeout=180.0)
        self.timesheet = timesheet
        self.user_name = user_name
        self.lang = lang

    @discord.ui.button(label="📥 Export Timesheet CSV", style=discord.ButtonStyle.secondary, emoji="📊")
    async def export_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        csv_data = service.export_timesheet_csv(self.timesheet)
        csv_bytes = csv_data.encode("utf-8-sig")
        file = discord.File(
            io.BytesIO(csv_bytes),
            filename=f"timesheet_{self.timesheet.user_id}_{self.timesheet.period}.csv",
        )
        await interaction.response.send_message(
            content=f"📄 **Timesheet CSV Export** ({self.timesheet.period}) for **{self.user_name}**:",
            file=file,
            ephemeral=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Active Stopwatch Timer Embed & Controls
# ─────────────────────────────────────────────────────────────────────────────

def build_timer_embed(
    user_name: str,
    timer: ActiveTimer,
    is_stopped: bool = False,
    logged_entry: Optional[TimeLogEntry] = None,
) -> discord.Embed:
    """Build embed for stopwatch timer status or stop result."""
    if is_stopped and logged_entry:
        embed = discord.Embed(
            title="⏹️ Stopwatch Timer Stopped & Logged",
            color=0x2ECC71,
        )
        embed.add_field(
            name="📋 Task",
            value=f"**#{timer.task_id}**: {timer.task_title or 'Untitled Task'}",
            inline=False,
        )
        embed.add_field(
            name="⏱️ Logged Time",
            value=f"**{logged_entry.hours_spent:.2f}** hours",
            inline=True,
        )
        if logged_entry.note:
            embed.add_field(name="📝 Note", value=logged_entry.note, inline=True)
        embed.set_footer(text="Logged to task time records successfully.")
        return embed

    elapsed_h = timer.elapsed_hours()
    elapsed_sec = int(timer.elapsed_seconds())
    m, s = divmod(elapsed_sec, 60)
    h, m = divmod(m, 60)
    time_display = f"{h:02d}:{m:02d}:{s:02d}"

    embed = discord.Embed(
        title="⏱️ Active Stopwatch Timer",
        description=f"Timer is running for **{user_name}**...",
        color=0xF1C40F,
    )
    embed.add_field(
        name="📋 Task",
        value=f"**#{timer.task_id}**: {timer.task_title or 'Untitled Task'}",
        inline=False,
    )
    embed.add_field(
        name="⏳ Elapsed Time",
        value=f"**{time_display}** (`{elapsed_h:.2f}` hrs)",
        inline=True,
    )
    if timer.note:
        embed.add_field(name="📝 Note", value=timer.note, inline=True)
    embed.set_footer(text="Use /time timer stop to finish and record.")
    return embed


class ActiveTimerControlsView(discord.ui.View):
    """View with interactive Stop and Cancel buttons for active stopwatch timer."""

    def __init__(self, user_id: str, timer: ActiveTimer) -> None:
        super().__init__(timeout=600.0)
        self.user_id = user_id
        self.timer = timer

    @discord.ui.button(label="Stop & Log", style=discord.ButtonStyle.success, emoji="⏹️")
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ You can only control your own timer.", ephemeral=True)
            return

        res = await service.stop_timer(self.user_id)
        if not res:
            await interaction.response.send_message("❌ No active timer found.", ephemeral=True)
            return
        t_obj, log_obj = res
        embed = build_timer_embed(interaction.user.display_name, t_obj, is_stopped=True, logged_entry=log_obj)
        self.stop()
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Cancel Timer", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ You can only control your own timer.", ephemeral=True)
            return

        await service.cancel_timer(self.user_id)
        self.stop()
        await interaction.response.edit_message(content="🛑 Active timer cancelled and discarded.", embed=None, view=None)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Estimation Accuracy & Variance Analytics Embed
# ─────────────────────────────────────────────────────────────────────────────

def build_estimation_analytics_embed(
    data: Dict[str, Any],
    scope_title: str = "Guild / All Projects",
    lang: str = "th",
) -> discord.Embed:
    """Build embed visualizing time estimation accuracy and variance."""
    mean_acc = data["mean_accuracy_pct"]
    color = 0x2ECC71 if mean_acc >= 80.0 else (0xF1C40F if mean_acc >= 60.0 else 0xE74C3C)

    embed = discord.Embed(
        title=f"🎯 {t('stats_estimation_title', lang)} — {scope_title}",
        color=color,
    )
    embed.add_field(
        name="🎯 Mean Accuracy",
        value=f"**{mean_acc:.1f}%**",
        inline=True,
    )
    embed.add_field(
        name="⏱️ Estimated vs Actual",
        value=f"Est: `{data['total_estimated_hours']:.1f}h` | Act: `{data['total_actual_hours']:.1f}h`",
        inline=True,
    )
    embed.add_field(
        name="📊 Tasks Analyzed",
        value=f"**{data['count']}** task(s)",
        inline=True,
    )

    breakdown_str = (
        f"🟢 **On Target** (±15%): `{data['accurate_count']}`\n"
        f"🔴 **Underestimated** (Took Longer): `{data['underestimated_count']}`\n"
        f"🔵 **Overestimated** (Finished Quicker): `{data['overestimated_count']}`"
    )
    embed.add_field(
        name="📈 Estimation Breakdown",
        value=breakdown_str,
        inline=False,
    )

    metrics: List[EstimationMetric] = data.get("metrics", [])
    if metrics:
        task_lines = []
        for m in metrics[:6]:
            icon = "🟢" if m.category == "accurate" else ("🔴" if m.category == "underestimated" else "🔵")
            sign = "+" if m.variance_pct > 0 else ""
            task_lines.append(
                f"{icon} **#{m.task_id}** {m.task_name[:25]} — Est: `{m.estimated_hours}h` / Act: `{m.actual_hours}h` (`{sign}{m.variance_pct}%`)"
            )
        embed.add_field(
            name="📋 Task Samples",
            value="\n".join(task_lines),
            inline=False,
        )

    embed.set_footer(text="Estimation Engine v1 · Variance Analytics · To-Do List Bot Gen 5.0")
    return embed


# ─────────────────────────────────────────────────────────────────────────────
# 4. Workload Capacity & Burnout Shield Embed
# ─────────────────────────────────────────────────────────────────────────────

def build_capacity_embed(
    metrics_list: List[CapacityMetric],
    scope_title: str = "Team Workload Overview",
    lang: str = "th",
) -> discord.Embed:
    """Build embed displaying workload allocation and Burnout Shield warnings."""
    has_overloaded = any(m.is_overloaded for m in metrics_list)
    color = 0xE67E22 if has_overloaded else 0x3498DB

    embed = discord.Embed(
        title=f"🛡️ {t('workload_capacity_title', lang)} — {scope_title}",
        color=color,
    )

    if not metrics_list:
        embed.description = "📭 No active task allocations found for team members."
        return embed

    lines = []
    for m in metrics_list:
        bar = _make_progress_bar(m.workload_pct)
        status_icon = "🔴" if m.is_overloaded else ("🟡" if m.workload_pct >= 80.0 else "🟢")
        alert_text = " ⚠️ **BURNOUT RISK!**" if m.is_overloaded else ""
        lines.append(
            f"{status_icon} <@{m.user_id}>\n"
            f"   {bar} (`{m.assigned_estimated_hours:.1f}` / `{m.weekly_capacity_hours:.1f}` hrs · {m.active_task_count} tasks){alert_text}"
        )

    embed.description = "\n\n".join(lines)
    embed.set_footer(text="Burnout Shield: Warning triggers when weekly assigned workload exceeds 100%.")
    return embed


# ─────────────────────────────────────────────────────────────────────────────
# 5. Project Budget Embed
# ─────────────────────────────────────────────────────────────────────────────

def build_budget_embed(
    metric: ProjectBudgetMetric,
    lang: str = "th",
) -> discord.Embed:
    """Build embed visualizing project budget, hourly billing, and threshold alerts."""
    if metric.is_over_budget:
        color = 0xE74C3C  # Red (Over budget)
    elif metric.is_near_limit:
        color = 0xF1C40F  # Yellow (Near limit 80%)
    else:
        color = 0x2ECC71  # Green

    embed = discord.Embed(
        title=f"💰 {t('proj_budget_title', lang)}: {metric.project_name} (#{metric.project_id})",
        color=color,
    )

    if metric.is_over_budget:
        embed.description = f"🚨 **BUDGET EXCEEDED!** Project has consumed **{metric.spent_pct:.1f}%** of its total budget!"
    elif metric.is_near_limit:
        embed.description = f"⚠️ **BUDGET WARNING!** Project has consumed **{metric.spent_pct:.1f}%** of its total budget (≥ 80%)!"

    cur = metric.currency
    bar = _make_progress_bar(metric.spent_pct)

    embed.add_field(
        name="💵 Budget Status",
        value=(
            f"Total Budget: **{metric.budget:,.2f} {cur}**\n"
            f"Spent: **{metric.spent_amount:,.2f} {cur}**\n"
            f"Remaining: **{max(0.0, metric.budget - metric.spent_amount):,.2f} {cur}**\n"
            f"Consumption: {bar}"
        ),
        inline=False,
    )

    embed.add_field(
        name="⏱️ Hours Breakdown",
        value=(
            f"💼 Billable Hours: **{metric.total_billable_hours:.2f}** hrs\n"
            f"☕ Non-Billable Hours: **{metric.total_non_billable_hours:.2f}** hrs"
        ),
        inline=True,
    )

    if metric.member_costs:
        cost_lines = [f"• <@{uid}>: `{amt:,.2f} {cur}`" for uid, amt in sorted(metric.member_costs.items(), key=lambda x: x[1], reverse=True)[:5]]
        embed.add_field(
            name="👥 Member Cost Allocation",
            value="\n".join(cost_lines),
            inline=False,
        )

    embed.set_footer(text="Project Budget Engine · Real-time Cost Tracking · To-Do List Bot Gen 5.0")
    return embed

