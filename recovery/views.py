"""
recovery/views.py — Discord UI Views and Embeds for the Recycle Bin (/trash)
"""
from __future__ import annotations

import math
from typing import Optional

import discord
from discord import ui

from locales.i18n import t
from recovery import service
from recovery.models import TrashTask
from utils.helpers import format_deadline


def build_trash_embed(
    tasks: list[TrashTask],
    page: int,
    total_pages: int,
    lang: str,
    selected_task_id: Optional[int] = None,
) -> discord.Embed:
    """Build the Recycle Bin embed displaying soft-deleted tasks."""
    embed = discord.Embed(
        title=f"🗑️ {t('trash_title', lang)}",
        description=t("trash_desc", lang),
        color=0xED4245,
    )

    if not tasks:
        embed.description = f"> {t('trash_empty', lang)}"
        embed.set_footer(text=f"Page 1/1 • To-Do List Bot Gen 2")
        return embed

    lines: list[str] = []
    for tk in tasks:
        is_sel = "👉 " if tk.task_id == selected_task_id else ""
        days_str = t("trash_days_left", lang, days=tk.days_remaining)
        dl_str = f" · 📅 `{format_deadline(tk.deadline, 'UTC')}`" if tk.deadline else ""
        lines.append(
            f"{is_sel}**#{tk.task_id}** `{tk.task[:45]}`{dl_str}\n"
            f"   ╰ ⏳ {days_str} · {tk.status}"
        )

    embed.add_field(
        name=t("trash_items_header", lang, count=len(tasks)),
        value="\n".join(lines),
        inline=False,
    )
    embed.set_footer(text=f"Page {page}/{max(1, total_pages)} • To-Do List Bot Gen 2")
    return embed


class TrashPaginationView(ui.View):
    """Interactive view for browsing and restoring tasks from Recycle Bin."""

    def __init__(
        self,
        tasks: list[TrashTask],
        uid: str,
        lang: str,
        page_size: int = 5,
        guild_id: Optional[str] = None,
    ) -> None:
        super().__init__(timeout=180.0)
        self.all_tasks = tasks
        self.uid = uid
        self.lang = lang
        self.guild_id = guild_id
        self.page_size = page_size
        self.current_page = 1
        self.selected_task_id: Optional[int] = None
        self._sync_components()

    @property
    def total_pages(self) -> int:
        return max(1, math.ceil(len(self.all_tasks) / self.page_size))

    def _page_tasks(self) -> list[TrashTask]:
        start = (self.current_page - 1) * self.page_size
        return self.all_tasks[start : start + self.page_size]

    def _sync_components(self) -> None:
        self.clear_items()
        page_items = self._page_tasks()

        # 1. Dropdown for selecting a task to restore/purge
        if page_items:
            options = [
                discord.SelectOption(
                    label=f"#{t_item.task_id} {t_item.task[:35]}",
                    value=str(t_item.task_id),
                    description=f"{t_item.days_remaining}d remaining · {t_item.status}",
                    default=(t_item.task_id == self.selected_task_id),
                )
                for t_item in page_items
            ]
            select = ui.Select(
                placeholder=t("trash_select_placeholder", self.lang),
                options=options,
                custom_id="trash_select_task",
                row=0,
            )
            select.callback = self._on_select_task
            self.add_item(select)

        # 2. Action buttons (Restore, Permanent Delete, Empty Bin)
        restore_btn = ui.Button(
            label=t("trash_btn_restore", self.lang),
            style=discord.ButtonStyle.success,
            emoji="♻️",
            disabled=(self.selected_task_id is None),
            row=1,
        )
        restore_btn.callback = self._on_restore
        self.add_item(restore_btn)

        purge_btn = ui.Button(
            label=t("trash_btn_purge", self.lang),
            style=discord.ButtonStyle.danger,
            emoji="💥",
            disabled=(self.selected_task_id is None),
            row=1,
        )
        purge_btn.callback = self._on_purge
        self.add_item(purge_btn)

        empty_btn = ui.Button(
            label=t("trash_btn_empty", self.lang),
            style=discord.ButtonStyle.secondary,
            emoji="🧹",
            disabled=(len(self.all_tasks) == 0),
            row=1,
        )
        empty_btn.callback = self._on_empty_bin
        self.add_item(empty_btn)

        # 3. Pagination controls (if multiple pages)
        if self.total_pages > 1:
            prev_btn = ui.Button(
                label="◀",
                style=discord.ButtonStyle.primary,
                disabled=(self.current_page <= 1),
                row=2,
            )
            prev_btn.callback = self._on_prev_page
            self.add_item(prev_btn)

            next_btn = ui.Button(
                label="▶",
                style=discord.ButtonStyle.primary,
                disabled=(self.current_page >= self.total_pages),
                row=2,
            )
            next_btn.callback = self._on_next_page
            self.add_item(next_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.uid:
            await interaction.response.send_message(
                t("permission_denied", self.lang), ephemeral=True
            )
            return False
        return True

    async def _on_select_task(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", [])
        if values:
            self.selected_task_id = int(values[0])
        self._sync_components()
        embed = build_trash_embed(
            self._page_tasks(),
            self.current_page,
            self.total_pages,
            self.lang,
            self.selected_task_id,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_restore(self, interaction: discord.Interaction) -> None:
        if not self.selected_task_id:
            return
        await interaction.response.defer()
        is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False
        ok, msg_key, tid = await service.restore_task(
            self.selected_task_id, self.uid, is_guild_admin=is_admin
        )
        if ok:
            # Refresh list
            self.all_tasks = await service.list_trash(self.uid, self.guild_id)
            self.selected_task_id = None
            if self.current_page > self.total_pages:
                self.current_page = self.total_pages
            self._sync_components()
            embed = build_trash_embed(
                self._page_tasks(),
                self.current_page,
                self.total_pages,
                self.lang,
            )
            await interaction.edit_original_response(
                content=f"✅ {t(msg_key, self.lang, task_id=tid)}",
                embed=embed,
                view=self,
            )
        else:
            await interaction.followup.send(f"❌ {t(msg_key, self.lang)}", ephemeral=True)

    async def _on_purge(self, interaction: discord.Interaction) -> None:
        if not self.selected_task_id:
            return
        await interaction.response.defer()
        is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False
        ok = await service.hard_delete_trash(
            self.selected_task_id, self.uid, is_guild_admin=is_admin
        )
        if ok:
            tid = self.selected_task_id
            self.all_tasks = await service.list_trash(self.uid, self.guild_id)
            self.selected_task_id = None
            if self.current_page > self.total_pages:
                self.current_page = self.total_pages
            self._sync_components()
            embed = build_trash_embed(
                self._page_tasks(),
                self.current_page,
                self.total_pages,
                self.lang,
            )
            await interaction.edit_original_response(
                content=f"💥 {t('trash_purge_success', self.lang, task_id=tid)}",
                embed=embed,
                view=self,
            )
        else:
            await interaction.followup.send(f"❌ {t('error', self.lang)}", ephemeral=True)

    async def _on_empty_bin(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False
        count = 0
        for tk in list(self.all_tasks):
            if await service.hard_delete_trash(tk.task_id, self.uid, is_guild_admin=is_admin):
                count += 1
        self.all_tasks = []
        self.selected_task_id = None
        self.current_page = 1
        self._sync_components()
        embed = build_trash_embed([], 1, 1, self.lang)
        await interaction.edit_original_response(
            content=f"🧹 {t('trash_purged_all', self.lang, count=count)}",
            embed=embed,
            view=self,
        )

    async def _on_prev_page(self, interaction: discord.Interaction) -> None:
        if self.current_page > 1:
            self.current_page -= 1
        self.selected_task_id = None
        self._sync_components()
        embed = build_trash_embed(
            self._page_tasks(), self.current_page, self.total_pages, self.lang
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_next_page(self, interaction: discord.Interaction) -> None:
        if self.current_page < self.total_pages:
            self.current_page += 1
        self.selected_task_id = None
        self._sync_components()
        embed = build_trash_embed(
            self._page_tasks(), self.current_page, self.total_pages, self.lang
        )
        await interaction.response.edit_message(embed=embed, view=self)
