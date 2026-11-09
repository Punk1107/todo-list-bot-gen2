"""
day_planner/views.py — Discord UI Views & Embed Builders for Day Planner.
"""
from __future__ import annotations

from typing import Optional
import discord
from discord import ui

from day_planner.optimizer import DayPlanResult, TimeBlock
from locales.i18n import t
from time_tracking import service as time_service


def build_day_plan_embed(plan: DayPlanResult, lang: str = "th") -> discord.Embed:
    """Constructs the visual timetable Discord embed for the daily schedule."""
    title = t("dayplan_title", lang=lang, work_date=plan.work_date)
    desc = t(
        "dayplan_desc",
        lang=lang,
        start_time=plan.start_time,
        end_time=plan.end_time,
        focus_hours=plan.total_focus_minutes // 60,
        focus_mins=plan.total_focus_minutes % 60,
        break_hours=plan.total_break_minutes // 60,
        break_mins=plan.total_break_minutes % 60,
        tasks_count=plan.tasks_count,
    )

    embed = discord.Embed(
        title=title,
        description=desc,
        color=discord.Color.from_rgb(52, 152, 219),  # Clean Blue
    )

    if not plan.blocks:
        embed.add_field(
            name="ℹ️",
            value=t("dayplan_no_tasks", lang=lang),
            inline=False,
        )
        return embed

    # Split timeline into Morning (<12:00) and Afternoon (>=12:00)
    morning_lines: list[str] = []
    afternoon_lines: list[str] = []

    for b in plan.blocks:
        start_h = int(b.start_str.split(":")[0])
        line = _format_block_line(b)
        if start_h < 12:
            morning_lines.append(line)
        else:
            afternoon_lines.append(line)

    if morning_lines:
        content = "\n".join(morning_lines)
        if len(content) > 1024:
            content = content[:1020] + "..."
        embed.add_field(
            name=t("dayplan_morning_field", lang=lang),
            value=content,
            inline=False,
        )

    if afternoon_lines:
        content = "\n".join(afternoon_lines)
        if len(content) > 1024:
            content = content[:1020] + "..."
        embed.add_field(
            name=t("dayplan_afternoon_field", lang=lang),
            value=content,
            inline=False,
        )

    embed.set_footer(text=t("dayplan_footer", lang=lang))
    return embed


def _format_block_line(b: TimeBlock) -> str:
    """Formats a single TimeBlock row with appropriate status emoji."""
    if b.block_type == "LUNCH":
        return f"🍱 **{b.start_str} - {b.end_str}** | {b.task_title}"
    elif b.block_type == "BREAK":
        return f"☕ **{b.start_str} - {b.end_str}** | {b.task_title}"
    elif b.block_type == "BUFFER":
        return f"🏁 **{b.start_str} - {b.end_str}** | {b.task_title}"
    else:
        # Focus block
        p_badge = f"[P{b.priority}]" if b.priority is not None else "[P]"
        q_badge = f" *({b.quadrant})*" if b.quadrant else ""
        tid = f"#{b.task_id} " if b.task_id else ""
        return f"🎯 **{b.start_str} - {b.end_str}** | {p_badge} {tid}{b.task_title}{q_badge}"


class DayPlanActionView(ui.View):
    """Action bar below the day plan embed with 'Start Day Plan' button."""

    def __init__(
        self,
        user_id: str,
        first_task_id: Optional[int],
        first_task_title: Optional[str],
        lang: str = "th",
    ) -> None:
        super().__init__(timeout=600)
        self.user_id = str(user_id)
        self.first_task_id = first_task_id
        self.first_task_title = first_task_title
        self.lang = lang

        # Add Start Button
        btn_label = t("dayplan_start_btn", lang=lang)
        self.start_btn = ui.Button(
            label=btn_label,
            style=discord.ButtonStyle.success,
            emoji="▶️",
            disabled=(first_task_id is None),
        )
        self.start_btn.callback = self.start_timer_callback
        self.add_item(self.start_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                "❌ คุณไม่สามารถกดปุ่มของตารางเวลานี้ได้ / Only the owner can interact.",
                ephemeral=True,
            )
            return False
        return True

    async def start_timer_callback(self, interaction: discord.Interaction) -> None:
        if self.first_task_id is None:
            await interaction.response.send_message(
                t("dayplan_no_tasks", lang=self.lang),
                ephemeral=True,
            )
            return

        try:
            await time_service.start_timer(
                user_id=self.user_id,
                task_id=self.first_task_id,
                note="Day Plan Session",
            )
            msg = t(
                "dayplan_started_msg",
                lang=self.lang,
                task_id=self.first_task_id,
                task_title=self.first_task_title or "",
            )
            # Disable button after starting
            self.start_btn.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(msg, ephemeral=True)
        except Exception as exc:
            await interaction.response.send_message(f"❌ Failed to start timer: {exc}", ephemeral=True)

