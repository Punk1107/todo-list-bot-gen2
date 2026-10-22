"""Discord UI Views & Modals for Task Templates and Definition of Done checklists."""
from __future__ import annotations

import logging
from typing import Any, Optional

import discord
from discord import ui

from core.database import db
from gamification import service as gamification_service
from locales.i18n import t
from routine_workflows import service
from routine_workflows.models import ChecklistItem

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Definition of Done: Checklist Management View & Modals
# ─────────────────────────────────────────────────────────────────────────────

class AddChecklistItemModal(ui.Modal):
    """Modal to add a new checklist item to a task."""

    def __init__(self, task_id: int, user_id: str, lang: str, parent_view: TaskChecklistView) -> None:
        super().__init__(title=t("dod_modal_title", lang)[:45])
        self.task_id = task_id
        self.user_id = user_id
        self.lang = lang
        self.parent_view = parent_view

        self.item_title = ui.TextInput(
            label=t("dod_modal_label", lang),
            placeholder=t("dod_modal_placeholder", lang),
            min_length=1,
            max_length=100,
            required=True,
        )
        self.add_item(self.item_title)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        title = self.item_title.value.strip()
        if title:
            await service.add_checklist_item(self.task_id, title)
        await self.parent_view.refresh_content(interaction)


class _ChecklistToggleSelect(ui.Select):
    """Dropdown to toggle a checklist item's completion status."""

    def __init__(self, items: list[ChecklistItem], lang: str) -> None:
        options = [
            discord.SelectOption(
                label=f"#{item.position + 1} {item.title[:60]}",
                value=str(item.checklist_id),
                emoji="✅" if item.is_done else "⬜",
                description=t("dod_toggle_done_desc", lang) if item.is_done else t("dod_toggle_pending_desc", lang),
            )
            for item in items[:25]
        ]
        super().__init__(
            placeholder=t("dod_select_placeholder", lang),
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        checklist_id = int(self.values[0])
        view = self.view
        if isinstance(view, TaskChecklistView):
            await service.toggle_checklist_item(checklist_id, view.user_id)
            await view.refresh_content(interaction)


class TaskChecklistView(ui.View):
    """Interactive view for inspecting, toggling, and adding Definition of Done checklist items."""

    def __init__(
        self,
        task_id: int,
        task_name: str,
        user_id: str,
        lang: str,
        items: list[ChecklistItem],
    ) -> None:
        super().__init__(timeout=300)
        self.task_id = task_id
        self.task_name = task_name
        self.user_id = user_id
        self.lang = lang
        self.items = items
        self._rebuild_items()

    def _rebuild_items(self) -> None:
        self.clear_items()
        if self.items:
            self.add_item(_ChecklistToggleSelect(self.items, self.lang))

        # Add Item Button
        add_btn = ui.Button(
            label=t("dod_btn_add", self.lang),
            emoji="➕",
            style=discord.ButtonStyle.primary,
            row=1,
        )
        add_btn.callback = self._on_add_click
        self.add_item(add_btn)

        # Refresh Button
        refresh_btn = ui.Button(
            label=t("dod_btn_refresh", self.lang),
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        refresh_btn.callback = self._on_refresh_click
        self.add_item(refresh_btn)

    async def _on_add_click(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        await interaction.response.send_modal(
            AddChecklistItemModal(self.task_id, self.user_id, self.lang, self)
        )

    async def _on_refresh_click(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.refresh_content(interaction)

    def make_embed(self) -> discord.Embed:
        done_count = sum(1 for i in self.items if i.is_done)
        total_count = len(self.items)
        pct = int(done_count / total_count * 100) if total_count > 0 else 100

        color = 0x57F287 if done_count == total_count and total_count > 0 else 0xFEE75C if done_count > 0 else 0x5865F2
        embed = discord.Embed(
            title=t("dod_embed_title", self.lang, task_id=self.task_id),
            description=f"**{self.task_name}**\n\n" + t("dod_embed_progress", self.lang, done=done_count, total=total_count, pct=pct),
            color=color,
        )

        if not self.items:
            embed.add_field(
                name=t("dod_field_items", self.lang),
                value=t("dod_empty", self.lang),
                inline=False,
            )
        else:
            lines = []
            for item in self.items:
                icon = "✅" if item.is_done else "⬜"
                lines.append(f"{icon} `#{item.position + 1}` {item.title}")
            embed.add_field(
                name=t("dod_field_items", self.lang),
                value="\n".join(lines),
                inline=False,
            )

        embed.set_footer(text=t("dod_footer", self.lang))
        return embed

    async def refresh_content(self, interaction: discord.Interaction) -> None:
        self.items = await service.get_checklists(self.task_id)
        self._rebuild_items()
        embed = self.make_embed()
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Definition of Done: Force Complete Confirmation Dialog
# ─────────────────────────────────────────────────────────────────────────────

class DoDForceConfirmView(ui.View):
    """
    Prompt shown when user clicks Mark Done on a task that still has pending checklist items.
    Allows user to force complete or go back to complete the remaining checklist items.
    """

    def __init__(
        self,
        task_id: int,
        task_name: str,
        user_id: str,
        lang: str,
        pending_items: list[ChecklistItem],
        origin_view: Optional[ui.View] = None,
    ) -> None:
        super().__init__(timeout=180)
        self.task_id = task_id
        self.task_name = task_name
        self.user_id = user_id
        self.lang = lang
        self.pending_items = pending_items
        self.origin_view = origin_view

    def make_embed(self) -> discord.Embed:
        lines = [f"• ❌ {item.title}" for item in self.pending_items[:5]]
        if len(self.pending_items) > 5:
            lines.append(t("dod_more_pending", self.lang, count=len(self.pending_items) - 5))

        embed = discord.Embed(
            title=t("dod_confirm_title", self.lang),
            description=t(
                "dod_confirm_desc",
                self.lang,
                count=len(self.pending_items),
                items="\n".join(lines),
            ),
            color=0xED4245,
        )
        embed.set_footer(text=t("dod_confirm_footer", self.lang))
        return embed

    @ui.button(label="⚡ Force Complete", style=discord.ButtonStyle.danger, custom_id="dod_force_done")
    async def force_complete(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        if str(interaction.user.id) != self.user_id:
            await interaction.followup.send(t("permission_denied", self.lang), ephemeral=True)
            return

        completed = await gamification_service.complete_personal_task(self.task_id, self.user_id)
        if completed is None:
            await interaction.followup.send(t("task_already_done", self.lang), ephemeral=True)
            return

        await db.alog_action(
            self.user_id,
            "task_completed_force_dod",
            str(self.task_id),
            f"pending_checklists={len(self.pending_items)}",
        )
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
        self.stop()

        await interaction.edit_original_response(
            content=t("task_done_with_name", self.lang, task_id=self.task_id, task_name=self.task_name),
            embed=None,
            view=self,
        )

        if self.origin_view:
            self.origin_view.stop()

    @ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary, custom_id="dod_cancel_done")
    async def cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
        self.stop()
        await interaction.response.edit_message(
            content=t("dod_cancelled_hint", self.lang),
            embed=None,
            view=self,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Task Templates: Creation Modal & Selection Views
# ─────────────────────────────────────────────────────────────────────────────

class TemplateCreateModal(ui.Modal):
    """Modal to define a custom template with relative offsets and subtasks."""

    def __init__(self, user_id: str, lang: str, guild_id: Optional[str] = None) -> None:
        super().__init__(title=t("template_create_modal_title", lang)[:45])
        self.user_id = user_id
        self.lang = lang
        self.guild_id = guild_id

        self.name_input = ui.TextInput(
            label=t("template_create_name_label", lang),
            placeholder="e.g. dev_onboarding",
            min_length=2,
            max_length=50,
            required=True,
        )
        self.task_input = ui.TextInput(
            label=t("template_create_task_label", lang),
            placeholder="e.g. Developer Onboarding",
            min_length=2,
            max_length=100,
            required=True,
        )
        self.rel_days_input = ui.TextInput(
            label=t("template_create_days_label", lang),
            placeholder="3",
            default="3",
            min_length=1,
            max_length=3,
            required=True,
        )
        self.subtasks_input = ui.TextInput(
            label=t("template_create_subtasks_label", lang),
            style=discord.TextStyle.paragraph,
            placeholder="+1d Setup Git\n+2d Read Guidelines\n+3d Join Team Sync",
            required=False,
            max_length=1000,
        )
        self.checklists_input = ui.TextInput(
            label=t("template_create_checklists_label", lang),
            style=discord.TextStyle.paragraph,
            placeholder="Submit Intro\nVerify Access",
            required=False,
            max_length=500,
        )

        self.add_item(self.name_input)
        self.add_item(self.task_input)
        self.add_item(self.rel_days_input)
        self.add_item(self.subtasks_input)
        self.add_item(self.checklists_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        name = self.name_input.value.strip().lower()
        task_title = self.task_input.value.strip()

        try:
            rel_days = max(1, min(365, int(self.rel_days_input.value.strip())))
        except ValueError:
            rel_days = 3

        # Parse checklists
        checklists: list[str] = [
            line.strip() for line in self.checklists_input.value.splitlines() if line.strip()
        ]

        # Parse subtasks (e.g. "+1d Subtask Name")
        subtasks: list[dict[str, Any]] = []
        for line in self.subtasks_input.value.splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue
            s_days = 1
            s_title = cleaned
            if cleaned.startswith("+") and "d" in cleaned[:6]:
                parts = cleaned.split(" ", 1)
                day_str = parts[0][1:].replace("d", "")
                try:
                    s_days = int(day_str)
                    s_title = parts[1] if len(parts) > 1 else cleaned
                except Exception:
                    pass
            subtasks.append({
                "task": s_title,
                "priority": 0,
                "relative_days": s_days,
            })

        items = {
            "task": task_title,
            "category": "Custom",
            "priority": 0,
            "relative_days": rel_days,
            "checklists": checklists,
            "subtasks": subtasks,
        }

        try:
            tmpl = await service.create_custom_template(
                name=name,
                items=items,
                owner_id=self.user_id,
                guild_id=self.guild_id,
                description=f"Custom template: {task_title}",
            )
            await interaction.followup.send(
                t("template_create_success", self.lang, name=tmpl.name), ephemeral=True
            )
        except Exception as exc:
            log.error("Failed to create template: %s", exc)
            await interaction.followup.send(t("err_generic", self.lang), ephemeral=True)
