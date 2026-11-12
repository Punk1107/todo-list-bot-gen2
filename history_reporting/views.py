"""
history_reporting/views.py — Discord UI Views for Task History and Weekly Retrospective
"""
from __future__ import annotations

import io
import logging
import math
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import ui
import pytz

from core.database import db
from history_reporting.models import TaskAuditHistory, TaskDiffResult
from locales.i18n import t
from utils.helpers import get_user_lang, get_user_timezone

log = logging.getLogger(__name__)

EVENTS_PER_PAGE = 5


# ─────────────────────────────────────────────────────────────────────────────
# 1. Task History View
# ─────────────────────────────────────────────────────────────────────────────

class TaskHistoryView(ui.View):
    """
    Paginated interactive view showing audit trail & timeline for a task.
    """

    def __init__(
        self,
        history: TaskAuditHistory,
        user_id: str,
        lang: str = "th",
        page: int = 0,
        origin_message: Optional[discord.Message] = None,
    ) -> None:
        super().__init__(timeout=180)
        self.history = history
        self.user_id = user_id
        self.lang = lang
        self.page = page
        self.origin_message = origin_message
        self._update_button_states()

    @property
    def total_pages(self) -> int:
        count = len(self.history.events)
        return max(1, math.ceil(count / EVENTS_PER_PAGE))

    def _update_button_states(self) -> None:
        self.prev_btn.disabled = (self.page <= 0)
        self.next_btn.disabled = (self.page >= self.total_pages - 1)

    def make_embed(self) -> discord.Embed:
        task_id = self.history.task_id
        tname = self.history.task_name
        status = self.history.current_status
        prio = self.history.current_priority
        cat = self.history.category_name or "General"
        snooze_cnt = self.history.snooze_count

        status_emoji = "✅" if status.lower() == "completed" else "⏳"
        embed = discord.Embed(
            title=f"📜 {t('history_title', self.lang, task_id=task_id)}",
            description=(
                f"**#{task_id} {tname}**\n"
                f"{status_emoji} Status: `{status.capitalize()}`  ·  ⚡ Priority: `P{prio}`  ·  🏷️ `{cat}`\n"
                f"👤 {t('history_creator', self.lang)}: <@{self.history.creator_id}>\n"
                f"⏰ {t('history_snooze_count', self.lang)}: **{snooze_cnt}**"
            ),
            color=0x6366f1,
        )

        events = self.history.events
        if not events:
            embed.add_field(
                name="📜 " + t("history_timeline", self.lang),
                value=f"*{t('history_empty', self.lang)}*",
                inline=False,
            )
        else:
            start = self.page * EVENTS_PER_PAGE
            page_events = events[start : start + EVENTS_PER_PAGE]

            for ev in page_events:
                created_str = (
                    ev.created_at.strftime("%d/%m/%Y %H:%M")
                    if isinstance(ev.created_at, datetime)
                    else str(ev.created_at)[:16]
                )
                embed.add_field(
                    name=f"{ev.icon} {created_str} &bull; <@{ev.user_id}>",
                    value=f"╰ {ev.format_description()}",
                    inline=False,
                )

        footer_text = f"📄 {self.page + 1}/{self.total_pages}  ·  {t('footer_text', self.lang)}"
        embed.set_footer(text=footer_text)
        return embed

    @ui.button(label="◀", style=discord.ButtonStyle.secondary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        if self.page > 0:
            self.page -= 1
            self._update_button_states()
            await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @ui.button(label="▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        if self.page < self.total_pages - 1:
            self.page += 1
            self._update_button_states()
            await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @ui.button(label="🔄 Refresh", style=discord.ButtonStyle.primary, row=0)
    async def refresh_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        from history_reporting import service as history_service

        updated = await history_service.get_task_audit_history(self.history.task_id, self.user_id)
        if updated:
            self.history = updated
            self.page = min(self.page, self.total_pages - 1)
            self._update_button_states()
            await interaction.response.edit_message(embed=self.make_embed(), view=self)
        else:
            await interaction.response.send_message(t("task_not_found", self.lang, task_id=self.history.task_id), ephemeral=True)

    @ui.button(label="🔀 Revision Diff", style=discord.ButtonStyle.secondary, row=0)
    async def diff_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        from history_reporting import service as history_service

        is_admin = bool(
            interaction.user.guild_permissions.administrator
            if (interaction.guild and hasattr(interaction.user, "guild_permissions"))
            else False
        )
        diff_res = await history_service.get_revision_diff(
            task_id=self.history.task_id,
            user_id=self.user_id,
            is_guild_admin=is_admin,
        )
        if diff_res is None:
            await interaction.followup.send(
                t("history_not_found_or_denied", self.lang, task_id=self.history.task_id),
                ephemeral=True,
            )
            return
        diff_view = TaskRevisionDiffView(
            diff_result=diff_res,
            user_id=self.user_id,
            lang=self.lang,
            is_guild_admin=is_admin,
        )
        await interaction.followup.send(
            embed=diff_view.make_embed(),
            view=diff_view,
            ephemeral=True,
        )


class _RevisionSelect(ui.Select):
    """Dropdown to choose which historical description revision to diff/rollback."""

    def __init__(self, parent_view: "TaskRevisionDiffView") -> None:
        options = []
        selected_id = parent_view.diff_result.selected_revision.revision_id if parent_view.diff_result.selected_revision else None
        for rev in parent_view.diff_result.revisions[:25]:
            ts = (
                rev.created_at.strftime("%Y-%m-%d %H:%M")
                if isinstance(rev.created_at, datetime)
                else str(rev.created_at)[:16]
            )
            source_icon = "↩️" if rev.change_source == "rollback" else "✏️"
            preview_snip = ((rev.previous_description or "(empty)").replace("\n", " "))[:45]
            options.append(
                discord.SelectOption(
                    label=f"Rev #{rev.revision_id} · {ts}"[:100],
                    value=str(rev.revision_id),
                    description=f"{source_icon} {preview_snip}"[:100],
                    default=(rev.revision_id == selected_id),
                )
            )
        super().__init__(
            placeholder=t("rev_select_placeholder", parent_view.lang)[:150],
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.parent_view.user_id:
            await interaction.response.send_message(t("permission_denied", self.parent_view.lang), ephemeral=True)
            return
        from history_reporting import service as history_service

        rev_id = int(self.values[0])
        new_diff = await history_service.get_revision_diff(
            task_id=self.parent_view.diff_result.task_id,
            user_id=self.parent_view.user_id,
            revision_id=rev_id,
            is_guild_admin=self.parent_view.is_guild_admin,
        )
        if not new_diff:
            await interaction.response.send_message(
                t("history_not_found_or_denied", self.parent_view.lang, task_id=self.parent_view.diff_result.task_id),
                ephemeral=True,
            )
            return
        updated_view = TaskRevisionDiffView(
            diff_result=new_diff,
            user_id=self.parent_view.user_id,
            lang=self.parent_view.lang,
            is_guild_admin=self.parent_view.is_guild_admin,
        )
        await interaction.response.edit_message(embed=updated_view.make_embed(), view=updated_view)


class TaskRevisionDiffView(ui.View):
    """Interactive Git-diff viewer & one-click rollback UI for task description revisions."""

    def __init__(
        self,
        diff_result: TaskDiffResult,
        user_id: str,
        lang: str = "th",
        is_guild_admin: bool = False,
    ) -> None:
        super().__init__(timeout=180)
        self.diff_result = diff_result
        self.user_id = user_id
        self.lang = lang
        self.is_guild_admin = is_guild_admin

        if diff_result.revisions:
            self.add_item(_RevisionSelect(self))
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        has_sel = self.diff_result.selected_revision is not None
        self.rollback_btn.disabled = not (has_sel and self.diff_result.can_rollback)
        self.download_diff_btn.disabled = not has_sel

    def make_embed(self) -> discord.Embed:
        d = self.diff_result
        embed = discord.Embed(
            title=f"🔀 {t('rev_diff_title', self.lang, task_id=d.task_id)}",
            color=0x5865F2 if d.selected_revision else 0x99AAB5,
        )
        if not d.selected_revision:
            embed.description = (
                f"**#{d.task_id} — {d.task_title}**\n\n"
                f"> {t('rev_diff_empty', self.lang)}"
            )
            embed.set_footer(text=t("footer_text", self.lang))
            return embed

        rev = d.selected_revision
        ts = (
            rev.created_at.strftime("%Y-%m-%d %H:%M UTC")
            if isinstance(rev.created_at, datetime)
            else str(rev.created_at)[:16]
        )
        meta = (
            f"**#{d.task_id} — {d.task_title}**\n"
            f"📌 **Revision #{rev.revision_id}** (`{rev.change_source}`) · <@{rev.edited_by}> · `{ts}`\n"
            f"`+{d.added_lines}` / `-{d.removed_lines}` · {t('rev_diff_count', self.lang, count=len(d.revisions))}"
        )
        diff_body = d.unified_diff_preview or "(no changes)"
        embed.description = f"{meta}\n```diff\n{diff_body}\n```"
        if d.truncated:
            embed.add_field(
                name="📎 Note",
                value=t("rev_diff_truncated_hint", self.lang),
                inline=False,
            )
        embed.set_footer(text=t("footer_text", self.lang))
        return embed

    @ui.button(label="↩️ Rollback", style=discord.ButtonStyle.danger, row=1)
    async def rollback_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        rev = self.diff_result.selected_revision
        if not rev:
            await interaction.response.send_message(t("rev_not_found", self.lang), ephemeral=True)
            return
        from history_reporting import service as history_service

        ok, msg_key = await history_service.rollback_task_description(
            task_id=self.diff_result.task_id,
            revision_id=rev.revision_id,
            actor_id=self.user_id,
            is_guild_admin=self.is_guild_admin,
        )
        if not ok:
            await interaction.response.send_message(
                t(msg_key, self.lang, task_id=self.diff_result.task_id),
                ephemeral=True,
            )
            return

        refreshed = await history_service.get_revision_diff(
            task_id=self.diff_result.task_id,
            user_id=self.user_id,
            is_guild_admin=self.is_guild_admin,
        )
        if refreshed:
            updated_view = TaskRevisionDiffView(
                diff_result=refreshed,
                user_id=self.user_id,
                lang=self.lang,
                is_guild_admin=self.is_guild_admin,
            )
            await interaction.response.edit_message(
                content=t("rev_rollback_success", self.lang, revision_id=rev.revision_id, task_id=self.diff_result.task_id),
                embed=updated_view.make_embed(),
                view=updated_view,
            )
        else:
            await interaction.response.send_message(
                t("rev_rollback_success", self.lang, revision_id=rev.revision_id, task_id=self.diff_result.task_id),
                ephemeral=True,
            )

    @ui.button(label="📄 Full .diff", style=discord.ButtonStyle.secondary, row=1)
    async def download_diff_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        rev = self.diff_result.selected_revision
        if not rev:
            await interaction.response.send_message(t("rev_not_found", self.lang), ephemeral=True)
            return
        buf = io.BytesIO((self.diff_result.unified_diff_full or "").encode("utf-8"))
        fname = f"task_{self.diff_result.task_id}_rev_{rev.revision_id}.diff"
        await interaction.response.send_message(
            file=discord.File(buf, filename=fname),
            ephemeral=True,
        )

    @ui.button(label="🔄 Refresh", style=discord.ButtonStyle.primary, row=1)
    async def refresh_diff_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        from history_reporting import service as history_service

        rev_id = self.diff_result.selected_revision.revision_id if self.diff_result.selected_revision else None
        refreshed = await history_service.get_revision_diff(
            task_id=self.diff_result.task_id,
            user_id=self.user_id,
            revision_id=rev_id,
            is_guild_admin=self.is_guild_admin,
        )
        if not refreshed:
            await interaction.response.send_message(
                t("history_not_found_or_denied", self.lang, task_id=self.diff_result.task_id),
                ephemeral=True,
            )
            return
        updated_view = TaskRevisionDiffView(
            diff_result=refreshed,
            user_id=self.user_id,
            lang=self.lang,
            is_guild_admin=self.is_guild_admin,
        )
        await interaction.response.edit_message(embed=updated_view.make_embed(), view=updated_view)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Weekly Retrospective View (DM Action Buttons)
# ─────────────────────────────────────────────────────────────────────────────

class WeeklyRetrospectiveView(ui.View):
    """
    Action buttons attached to the Sunday evening Retrospective DM.
    """

    def __init__(self, user_id: str, lang: str = "th") -> None:
        super().__init__(timeout=None)
        self.user_id = user_id
        self.lang = lang

    @ui.button(label="📤 Export HTML", style=discord.ButtonStyle.primary, custom_id="retro_export_html")
    async def export_html(self, interaction: discord.Interaction, button: ui.Button) -> None:
        uid = str(interaction.user.id)
        if uid != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        from history_reporting import service as history_service

        tasks = await db.afetchall(
            "SELECT * FROM tasks WHERE owner_id=$1 AND is_deleted=FALSE ORDER BY created_at DESC",
            (uid,),
        )
        if not tasks:
            await interaction.followup.send(t("export_empty", self.lang), ephemeral=True)
            return

        cats = await db.afetchall(
            "SELECT * FROM categories WHERE owner_id IN ($1, 'system')",
            (uid,),
        )
        tz_name = await get_user_timezone(uid)

        file_bytes = history_service.build_html_export_bytes(
            tasks=tasks,
            categories=cats or [],
            user_id=uid,
            tz_name=tz_name,
            lang=self.lang,
        )
        fname = f"tasks_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.html"
        await interaction.followup.send(
            t("export_success_html", self.lang, filename=fname),
            file=discord.File(file_bytes, filename=fname),
            ephemeral=True,
        )

    @ui.button(label="⚙️ Toggle Reminders", style=discord.ButtonStyle.secondary, custom_id="retro_toggle_settings")
    async def toggle_settings(self, interaction: discord.Interaction, button: ui.Button) -> None:
        uid = str(interaction.user.id)
        if uid != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return

        row = await db.afetchone("SELECT weekly_retrospective FROM users WHERE user_id=$1", (uid,))
        cur = row.get("weekly_retrospective", 1) if row else 1
        new_val = 0 if cur else 1

        await db.aexecute("UPDATE users SET weekly_retrospective=$1 WHERE user_id=$2", (new_val, uid))
        db.user_cache.invalidate(uid)

        state_msg = t("retro_enabled", self.lang) if new_val else t("retro_disabled", self.lang)
        await interaction.response.send_message(f"⚙️ {state_msg}", ephemeral=True)
