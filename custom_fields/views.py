"""
custom_fields/views.py — Interactive Select dropdowns & Dynamic Modals for Task Meta-Fields.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import discord
from discord import ui

from custom_fields import service as field_service
from custom_fields.models import CustomFieldType, ProjectCustomField
from locales.i18n import t
from utils.helpers import get_user_lang

log = logging.getLogger(__name__)


class CustomFieldTextModal(ui.Modal):
    """Dynamic Modal generated for up to 5 text/number/date custom fields of a task."""

    def __init__(
        self,
        task_id: int,
        task_title: str,
        guild_id: str,
        input_fields: list[ProjectCustomField],
        current_values: dict[str, Any],
        lang: str,
        origin_view: Optional["TaskCustomFieldsView"] = None,
    ) -> None:
        super().__init__(title=t("field_modal_edit_title", lang, task_id=task_id)[:45])
        self.task_id = task_id
        self.task_title = task_title
        self.guild_id = guild_id
        self.input_fields = input_fields[:5]
        self.lang = lang
        self.origin_view = origin_view
        self._inputs: dict[str, ui.TextInput] = {}

        for fd in self.input_fields:
            placeholder = {
                CustomFieldType.NUMBER.value: "e.g. 5 or 1200.50",
                CustomFieldType.DATE.value: "YYYY-MM-DD (e.g. 2026-12-31)",
                CustomFieldType.TEXT.value: "Enter value or https://...",
            }.get(fd.field_type, "")
            cur_val = current_values.get(fd.field_key)
            inp = ui.TextInput(
                label=f"{fd.type_emoji} {fd.field_label}"[:45],
                default=str(cur_val)[:500] if cur_val is not None else None,
                placeholder=placeholder[:100] or None,
                max_length=500,
                required=fd.is_required,
            )
            self._inputs[fd.field_key] = inp
            self.add_item(inp)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        is_admin = bool(
            interaction.guild
            and hasattr(interaction.user, "guild_permissions")
            and interaction.user.guild_permissions.administrator
        )
        updates: dict[str, Optional[str]] = {
            k: inp.value.strip() or None for k, inp in self._inputs.items()
        }
        try:
            new_vals = await field_service.set_task_custom_fields_batch(
                task_id=self.task_id,
                guild_id=self.guild_id,
                updates=updates,
                actor_id=uid,
                is_guild_admin=is_admin,
            )
        except field_service.CustomFieldError as exc:
            await interaction.response.send_message(t(str(exc), self.lang), ephemeral=True)
            return
        except Exception as exc:
            log.error("CustomFieldTextModal error: %s", exc, exc_info=True)
            await interaction.response.send_message(t("err_db", self.lang), ephemeral=True)
            return

        if self.origin_view is not None:
            self.origin_view.current_values = new_vals
            await interaction.response.edit_message(
                content=t("field_values_saved", self.lang, task_id=self.task_id),
                embed=self.origin_view.make_embed(),
                view=self.origin_view,
            )
        else:
            await interaction.response.send_message(
                t("field_values_saved", self.lang, task_id=self.task_id),
                ephemeral=True,
            )


class _SelectFieldDropdown(ui.Select):
    """Single-select Discord Dropdown mapped to a ``select`` custom field definition."""

    def __init__(
        self,
        parent_view: "TaskCustomFieldsView",
        field_def: ProjectCustomField,
        current_value: Any,
        row: int,
    ) -> None:
        options = [
            discord.SelectOption(
                label=opt[:100],
                value=opt[:100],
                default=(str(current_value).lower() == opt.lower()) if current_value is not None else False,
            )
            for opt in field_def.options[:25]
        ]
        super().__init__(
            placeholder=f"{field_def.type_emoji} {field_def.field_label}"[:150],
            min_values=1,
            max_values=1,
            options=options,
            row=row,
        )
        self.parent_view = parent_view
        self.field_def = field_def

    async def callback(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        is_admin = bool(
            interaction.guild
            and hasattr(interaction.user, "guild_permissions")
            and interaction.user.guild_permissions.administrator
        )
        try:
            new_vals = await field_service.set_task_custom_fields_batch(
                task_id=self.parent_view.task_id,
                guild_id=self.parent_view.guild_id,
                updates={self.field_def.field_key: self.values[0]},
                actor_id=uid,
                is_guild_admin=is_admin,
            )
        except field_service.CustomFieldError as exc:
            await interaction.response.send_message(t(str(exc), self.parent_view.lang), ephemeral=True)
            return

        refreshed = TaskCustomFieldsView(
            task_id=self.parent_view.task_id,
            task_title=self.parent_view.task_title,
            project_id=self.parent_view.project_id,
            guild_id=self.parent_view.guild_id,
            field_defs=self.parent_view.field_defs,
            current_values=new_vals,
            lang=self.parent_view.lang,
        )
        await interaction.response.edit_message(
            content=t("field_values_saved", self.parent_view.lang, task_id=self.parent_view.task_id),
            embed=refreshed.make_embed(),
            view=refreshed,
        )


class TaskCustomFieldsView(ui.View):
    """Interactive manager for viewing & updating all custom meta-fields of a project task."""

    def __init__(
        self,
        task_id: int,
        task_title: str,
        project_id: int,
        guild_id: str,
        field_defs: list[ProjectCustomField],
        current_values: dict[str, Any],
        lang: str = "th",
    ) -> None:
        super().__init__(timeout=240)
        self.task_id = task_id
        self.task_title = task_title
        self.project_id = project_id
        self.guild_id = guild_id
        self.field_defs = field_defs
        self.current_values = current_values
        self.lang = lang

        select_fields = [f for f in field_defs if f.field_type == CustomFieldType.SELECT.value and f.options][:4]
        for idx, sf in enumerate(select_fields):
            self.add_item(_SelectFieldDropdown(self, sf, current_values.get(sf.field_key), row=idx))

        input_fields = [f for f in field_defs if f.field_type != CustomFieldType.SELECT.value]
        self._input_fields = input_fields
        self.edit_inputs_btn.disabled = (len(input_fields) == 0)

    def make_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"🧩 {t('field_task_panel_title', self.lang, task_id=self.task_id)}",
            description=f"**#{self.task_id} — {self.task_title}**",
            color=0x8B5CF6,
        )
        if not self.field_defs:
            embed.add_field(
                name=t("field_schema_label", self.lang),
                value=t("field_list_empty", self.lang),
                inline=False,
            )
        else:
            for fd in self.field_defs[:15]:
                val = self.current_values.get(fd.field_key)
                req_badge = " *" if fd.is_required else ""
                val_disp = f"`{val}`" if val is not None else f"*{t('field_unset', self.lang)}*"
                embed.add_field(
                    name=f"{fd.type_emoji} {fd.field_label}{req_badge}",
                    value=f"{val_disp}\n`key: {fd.field_key} · {fd.field_type}`",
                    inline=True,
                )
        embed.set_footer(text=t("footer_text", self.lang))
        return embed

    @ui.button(label="📝 Edit Input Fields", style=discord.ButtonStyle.primary, row=4)
    async def edit_inputs_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = await get_user_lang(str(interaction.user.id))
        if not self._input_fields:
            await interaction.response.send_message(t("field_no_input_fields", lang), ephemeral=True)
            return
        modal = CustomFieldTextModal(
            task_id=self.task_id,
            task_title=self.task_title,
            guild_id=self.guild_id,
            input_fields=self._input_fields,
            current_values=self.current_values,
            lang=lang,
            origin_view=self,
        )
        await interaction.response.send_modal(modal)


def build_fields_list_embed(
    project_name: str,
    defs: list[ProjectCustomField],
    lang: str = "th",
) -> discord.Embed:
    """Build a summary Embed listing all custom meta-field definitions for a project."""
    embed = discord.Embed(
        title=f"🧩 {t('field_list_title', lang, project=project_name)}",
        color=0x8B5CF6,
    )
    if not defs:
        embed.description = f"> {t('field_list_empty', lang)}"
    else:
        for fd in defs:
            extra = f"\nOptions: {', '.join(f'`{o}`' for o in fd.options[:8])}" if fd.options else ""
            req = " · `required`" if fd.is_required else ""
            embed.add_field(
                name=f"{fd.type_emoji} {fd.field_label} (`{fd.field_key}`)",
                value=f"Type: `{fd.field_type}`{req}{extra}",
                inline=False,
            )
    embed.set_footer(text=t("footer_text", lang))
    return embed
