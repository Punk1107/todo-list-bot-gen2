"""Discord UI confirmation Views & Modal for GDPR erasure (Feature 42)."""
from __future__ import annotations

import discord
from discord import ui

from locales.i18n import t
from privacy import service
from privacy.models import GdprImpactSummary


class ConfirmGdprModal(ui.Modal):
    """Requires typing DELETE explicitly to confirm irreversible personal data erasure."""

    def __init__(self, user_id: str, lang: str) -> None:
        super().__init__(title=t("privacy_confirm_modal_title", lang)[:45])
        self.user_id = user_id
        self.lang = lang
        self.confirm_input = ui.TextInput(
            label=t("privacy_confirm_input_label", lang)[:45],
            placeholder="DELETE",
            required=True,
            max_length=12,
        )
        self.add_item(self.confirm_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        if (self.confirm_input.value or "").strip().upper() != "DELETE":
            await interaction.response.send_message(
                t("privacy_confirm_mismatch", self.lang), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        report = await service.execute_gdpr_deletion(self.user_id)
        embed = discord.Embed(
            title=t("privacy_deleted_title", self.lang),
            description=t(
                "privacy_deleted_desc",
                self.lang,
                personal=report.personal_tasks_deleted,
                anonymized=report.shared_tasks_anonymized,
                transferred=report.projects_transferred,
            ),
            color=0x57F287,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


class PrivacyDeleteView(ui.View):
    """Interactive impact confirmation view with Delete & Cancel buttons."""

    def __init__(self, user_id: str, lang: str, impact: GdprImpactSummary) -> None:
        super().__init__(timeout=180)
        self.user_id = user_id
        self.lang = lang
        self.impact = impact
        self.btn_confirm.label = t("privacy_btn_delete", lang)
        self.btn_cancel.label = t("privacy_btn_cancel", lang)

    def make_embed(self) -> discord.Embed:
        return discord.Embed(
            title=t("privacy_impact_title", self.lang),
            description=t(
                "privacy_impact_desc",
                self.lang,
                personal=self.impact.personal_tasks,
                shared=self.impact.shared_project_tasks,
                projects=self.impact.owned_projects,
                docs=self.impact.comments_and_docs,
                timelogs=self.impact.time_logs,
            ),
            color=0xED4245,
        )

    @ui.button(label="Delete My Data", emoji="⚠️", style=discord.ButtonStyle.danger)
    async def btn_confirm(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        await interaction.response.send_modal(ConfirmGdprModal(self.user_id, self.lang))

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def btn_cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        await interaction.response.edit_message(content=t("privacy_cancelled", self.lang), embed=None, view=None)
