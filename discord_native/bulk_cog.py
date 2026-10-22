"""Multi-select bulk actions for personal tasks."""
from __future__ import annotations

import logging

import discord
from discord import app_commands, ui
from discord.ext import commands

from core.database import db
from core.security import rate_limit_check
from gamification import service as gamification_service
from handlers.task_views import calculate_defensive_snooze
from locales.i18n import t
from utils.helpers import ensure_user, get_user_lang

log = logging.getLogger(__name__)
_PAGE_SIZE = 25


class BulkTaskSelect(ui.Select):
    def __init__(self, view: "BulkTaskView", rows: list) -> None:
        self.bulk_view = view
        options = [
            discord.SelectOption(
                label=f"#{row['task_id']} · {row['task'][:75]}",
                value=str(row["task_id"]),
                description=f"{row['status']} · {str(row['deadline'])[:40]}",
                default=row["task_id"] in view.selected_ids,
            )
            for row in rows
        ]
        super().__init__(
            placeholder=t("bulk_select_placeholder", view.lang),
            min_values=0,
            max_values=len(options),
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.bulk_view
        if str(interaction.user.id) != view.uid:
            await interaction.response.send_message(t("permission_denied", view.lang), ephemeral=True)
            return
        page_ids = {int(option.value) for option in self.options}
        view.selected_ids.difference_update(page_ids)
        view.selected_ids.update(int(value) for value in self.values)
        await view.refresh(interaction)


class BulkTaskView(ui.View):
    def __init__(self, uid: str, lang: str, action: str, rows: list, total: int) -> None:
        super().__init__(timeout=180)
        self.uid = uid
        self.lang = lang
        self.action = action
        self.rows = rows
        self.total = total
        self.page = 0
        self.selected_ids: set[int] = set()
        self.confirming_delete = False
        self._build_items()

    def _build_items(self) -> None:
        for item in list(self.children):
            if isinstance(item, BulkTaskSelect):
                self.remove_item(item)
        start = self.page * _PAGE_SIZE
        page_rows = self.rows[start:start + _PAGE_SIZE]
        if page_rows:
            self.add_item(BulkTaskSelect(self, page_rows))
        self.previous.disabled = self.page == 0
        self.next.disabled = start + _PAGE_SIZE >= self.total
        self.apply.label = (
            t("bulk_delete_confirm", self.lang)
            if self.action == "delete" and self.confirming_delete
            else t("bulk_apply", self.lang)
        )
        self.apply.style = (
            discord.ButtonStyle.danger
            if self.action == "delete"
            else discord.ButtonStyle.success
        )
        self.cancel.label = t("cancel", self.lang)

    async def refresh(self, interaction: discord.Interaction) -> None:
        self._build_items()
        await interaction.response.edit_message(
            content=t(
                "bulk_picker_description", self.lang,
                selected=len(self.selected_ids),
                page=self.page + 1,
                pages=max(1, (self.total + _PAGE_SIZE - 1) // _PAGE_SIZE),
            ),
            view=self,
        )

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True

    @ui.button(label="◀", style=discord.ButtonStyle.secondary, row=1)
    async def previous(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if str(interaction.user.id) != self.uid:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        self.page = max(0, self.page - 1)
        await self.refresh(interaction)

    @ui.button(label="▶", style=discord.ButtonStyle.secondary, row=1)
    async def next(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if str(interaction.user.id) != self.uid:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        self.page = min(max(0, (self.total - 1) // _PAGE_SIZE), self.page + 1)
        await self.refresh(interaction)

    @ui.button(label="Apply", style=discord.ButtonStyle.success, row=2)
    async def apply(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if str(interaction.user.id) != self.uid:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        if not self.selected_ids:
            await interaction.response.send_message(t("bulk_select_at_least_one", self.lang), ephemeral=True)
            return
        if self.action == "delete" and not self.confirming_delete:
            self.confirming_delete = True
            self._build_items()
            await interaction.response.edit_message(
                content=t("bulk_delete_warning", self.lang, count=len(self.selected_ids)),
                view=self,
            )
            return
        await interaction.response.defer(ephemeral=True)
        succeeded = 0
        failed = 0
        for task_id in sorted(self.selected_ids):
            try:
                if self.action == "done":
                    awarded = await gamification_service.complete_personal_task(task_id, self.uid)
                    if awarded is None:
                        failed += 1
                        continue
                    await db.alog_action(self.uid, "task_completed", str(task_id))
                elif self.action == "snooze":
                    row = await db.afetchone(
                        """SELECT deadline FROM tasks
                           WHERE task_id=$1 AND owner_id=$2 AND parent_task_id IS NULL
                             AND status IN ('Pending','In_Progress')""",
                        (task_id, self.uid),
                    )
                    if row is None:
                        failed += 1
                        continue
                    new_deadline = calculate_defensive_snooze(row["deadline"])
                    updated = await db.afetchone(
                        """UPDATE tasks SET deadline=$1, updated_at=NOW()
                           WHERE task_id=$2 AND owner_id=$3 AND parent_task_id IS NULL
                             AND status IN ('Pending','In_Progress')
                           RETURNING task_id""",
                        (new_deadline, task_id, self.uid),
                    )
                    if updated is None:
                        failed += 1
                        continue
                    await db.alog_action(self.uid, "task_snoozed", str(task_id))
                    db.query_cache.invalidate_tables(["tasks"])
                    db.invalidate_stats(self.uid)
                else:
                    from recovery import service as recovery_service
                    deleted = await recovery_service.soft_delete_task(task_id, self.uid)
                    if not deleted:
                        failed += 1
                        continue
                succeeded += 1
            except Exception:
                failed += 1
                log.exception("Bulk %s failed for task_id=%s user_id=%s", self.action, task_id, self.uid)
        self.stop()
        await interaction.edit_original_response(
            content=t("bulk_result", self.lang, succeeded=succeeded, failed=failed),
            view=None,
        )

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=2)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if str(interaction.user.id) != self.uid:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        self.stop()
        await interaction.response.edit_message(content=t("cancel", self.lang), view=None)


class BulkActionsCog(commands.Cog, name="Bulk Actions"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    bulk = app_commands.Group(name="bulk", description="Apply an action to multiple personal tasks")

    @bulk.command(name="done", description="Complete multiple tasks")
    @rate_limit_check("command")
    async def bulk_done(self, interaction: discord.Interaction) -> None:
        await self._open_picker(interaction, "done")

    @bulk.command(name="snooze", description="Snooze multiple tasks by one day")
    @rate_limit_check("command")
    async def bulk_snooze(self, interaction: discord.Interaction) -> None:
        await self._open_picker(interaction, "snooze")

    @bulk.command(name="delete", description="Delete multiple tasks")
    @rate_limit_check("command")
    async def bulk_delete(self, interaction: discord.Interaction) -> None:
        await self._open_picker(interaction, "delete")

    async def _open_picker(self, interaction: discord.Interaction, action: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        rows = await db.afetchall(
            """SELECT task_id, task, deadline, status FROM tasks
               WHERE owner_id=$1 AND parent_task_id IS NULL
                 AND status IN ('Pending','In_Progress')
               ORDER BY priority DESC, deadline ASC""",
            (uid,),
        ) or []
        if not rows:
            await interaction.followup.send(t("bulk_no_tasks", lang), ephemeral=True)
            return
        view = BulkTaskView(uid, lang, action, rows, len(rows))
        await interaction.followup.send(
            t(
                "bulk_picker_description", lang,
                selected=0,
                page=1,
                pages=max(1, (len(rows) + _PAGE_SIZE - 1) // _PAGE_SIZE),
            ),
            view=view,
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BulkActionsCog(bot))
