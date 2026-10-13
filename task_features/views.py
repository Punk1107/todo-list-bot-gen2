"""Discord views and modals for task comments and progress."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import discord
from discord import ui

from locales.i18n import t
from task_features import service
from utils.helpers import percentage_progress_bar

log = logging.getLogger(__name__)
COMMENTS_PER_PAGE = 5


def _comments_embed(
    task_id: int,
    task_name: str,
    comments: list[Any],
    total: int,
    page: int,
    lang: str,
) -> discord.Embed:
    total_pages = max(1, (total + COMMENTS_PER_PAGE - 1) // COMMENTS_PER_PAGE)
    embed = discord.Embed(
        title=t("comments_title", lang, task_id=task_id),
        description=f"**{task_name[:180]}**",
        color=0x5865F2,
    )
    if not comments:
        embed.add_field(
            name=t("comments_empty_title", lang),
            value=t("comments_empty", lang),
            inline=False,
        )
    else:
        for comment in comments:
            content = comment["content"]
            if len(content) > 900:
                content = content[:897] + "..."
            created_at = comment["created_at"]
            if isinstance(created_at, datetime):
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                timestamp = discord.utils.format_dt(created_at, style="R")
            else:
                timestamp = str(created_at)
            embed.add_field(
                name=f"<@{comment['user_id']}> · {timestamp}",
                value=content,
                inline=False,
            )
    embed.set_footer(text=t("comments_page", lang, page=page + 1, total=total_pages))
    return embed


class TaskCommentsView(ui.View):
    """Ephemeral, paginated task discussion controls."""

    def __init__(
        self,
        task_id: int,
        user_id: str,
        lang: str,
        task_name: str,
        page: int,
        total: int,
    ) -> None:
        super().__init__(timeout=300)
        self.task_id = task_id
        self.user_id = user_id
        self.lang = lang
        self.task_name = task_name
        self.page = page
        self.total = total
        self.previous_page.disabled = page <= 0
        self.next_page.disabled = (page + 1) * COMMENTS_PER_PAGE >= total

    def make_embed(self, comments: list[Any]) -> discord.Embed:
        return _comments_embed(
            self.task_id, self.task_name, comments, self.total, self.page, self.lang
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                t("permission_denied", self.lang), ephemeral=True
            )
            return False
        try:
            await service.get_accessible_task(self.task_id, self.user_id)
        except service.TaskFeatureError:
            await interaction.response.send_message(
                t("permission_denied", self.lang), ephemeral=True
            )
            return False
        return True

    async def _show_page(self, interaction: discord.Interaction, page: int) -> None:
        task, comments, total = await service.get_comments(
            self.task_id, self.user_id, page, COMMENTS_PER_PAGE
        )
        self.page = min(max(page, 0), max(0, (total - 1) // COMMENTS_PER_PAGE))
        self.total = total
        self.task_name = task["task"]
        self.previous_page.disabled = self.page <= 0
        self.next_page.disabled = (self.page + 1) * COMMENTS_PER_PAGE >= total
        await interaction.response.edit_message(
            embed=self.make_embed(comments), view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @ui.button(label="◀", style=discord.ButtonStyle.secondary, row=0)
    async def previous_page(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._show_page(interaction, self.page - 1)

    @ui.button(label="💬 Add comment", style=discord.ButtonStyle.primary, row=0)
    async def add_comment_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        try:
            task = await service.get_accessible_task(
                self.task_id, self.user_id, minimum_role="member"
            )
        except service.TaskFeatureError:
            await interaction.response.send_message(
                t("permission_denied", self.lang), ephemeral=True
            )
            return
        await interaction.response.send_modal(
            TaskCommentModal(self.task_id, self.user_id, self.lang, task["task"])
        )

    @ui.button(label="▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_page(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._show_page(interaction, self.page + 1)

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: ui.Item[Any],
    ) -> None:
        log.error(
            "Task comments view failed (task_id=%s item=%s): %s",
            self.task_id, getattr(item, "custom_id", "?"), error, exc_info=True,
        )
        message = t("err_generic", self.lang)
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


class TaskCommentModal(ui.Modal):
    """Modal for adding a comment to a task discussion."""

    def __init__(self, task_id: int, user_id: str, lang: str, task_name: str) -> None:
        super().__init__(title=t("comments_title", lang, task_id=task_id)[:45])
        self.task_id = task_id
        self.user_id = user_id
        self.lang = lang
        self.task_name = task_name
        self.content = ui.TextInput(
            label=t("comment_input_label", lang),
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True,
        )
        self.add_item(self.content)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                t("permission_denied", self.lang), ephemeral=True
            )
            return
        try:
            await service.add_comment(self.task_id, self.user_id, self.content.value)
            task, comments, total = await service.get_comments(
                self.task_id, self.user_id, 0, COMMENTS_PER_PAGE
            )
        except service.InvalidComment:
            await interaction.response.send_message(t("err_input_invalid", self.lang), ephemeral=True)
            return
        except service.TaskFeatureError:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        view = TaskCommentsView(
            self.task_id, self.user_id, self.lang, task["task"], 0, total
        )
        await interaction.response.send_message(
            t("comment_added", self.lang),
            embed=view.make_embed(comments),
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.error(
            "Task comment modal failed (task_id=%s): %s",
            self.task_id, error, exc_info=True,
        )
        message = t("err_generic", self.lang)
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


class TaskProgressModal(ui.Modal):
    """Modal for setting a task's progress percentage."""

    def __init__(
        self,
        task_id: int,
        user_id: str,
        lang: str,
        current_progress: int,
        message: discord.Message | None,
    ) -> None:
        super().__init__(title=t("progress_modal_title", lang)[:45])
        self.task_id = task_id
        self.user_id = user_id
        self.lang = lang
        self.message = message
        self.progress = ui.TextInput(
            label=t("progress_input_label", lang),
            placeholder="0 - 100",
            default=str(current_progress),
            max_length=3,
            required=True,
        )
        self.add_item(self.progress)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                t("permission_denied", self.lang), ephemeral=True
            )
            return
        value = self.progress.value.strip()
        if not value.isascii() or not value.isdigit() or not 0 <= int(value) <= 100:
            await interaction.response.send_message(t("err_input_invalid", self.lang), ephemeral=True)
            return

        try:
            updated = await service.update_progress(self.task_id, self.user_id, int(value))
        except service.InvalidProgress:
            await interaction.response.send_message(t("err_input_invalid", self.lang), ephemeral=True)
            return
        except service.TaskFeatureError:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return

        refreshed = True
        if self.message and self.message.embeds:
            embed = discord.Embed.from_dict(self.message.embeds[0].to_dict())
            field_name = t("task_detail_progress", self.lang)
            progress_value = percentage_progress_bar(int(updated["progress_pct"]))
            field_index = next(
                (index for index, field in enumerate(embed.fields) if field.name == field_name),
                None,
            )
            if field_index is None:
                embed.add_field(name=field_name, value=progress_value, inline=False)
            else:
                embed.set_field_at(
                    field_index, name=field_name, value=progress_value, inline=False
                )
            try:
                await self.message.edit(embed=embed)
            except discord.HTTPException:
                refreshed = False
                log.warning(
                    "Progress saved but task embed refresh failed (task_id=%s)",
                    self.task_id,
                    exc_info=True,
                )

        response = t(
            "progress_updated",
            self.lang,
            progress=updated["progress_pct"],
        )
        if not refreshed:
            response += "\n" + t("progress_refresh_failed", self.lang)
        await interaction.response.send_message(response, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.error(
            "Task progress modal failed (task_id=%s): %s",
            self.task_id, error, exc_info=True,
        )
        message = t("err_generic", self.lang)
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
