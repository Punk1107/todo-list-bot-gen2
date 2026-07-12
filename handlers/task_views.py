"""
handlers/task_views.py — Discord UI Views and Modals v3 (System Upgrade)
Changes:
  - All helper calls now properly awaited (async helpers)
  - TaskActionView: fixed pin_toggle logic bug (action logged incorrectly)
  - TaskActionView: added inline Category select dropdown
  - build_task_embed calls now pass pre-fetched subtasks/category (async safe)
  - DeleteConfirmView.on_timeout disables buttons and edits message
  - TaskListView: better page navigation (jump to first/last)
  - All on_timeout handlers properly disable buttons
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import discord
from discord import ui
import pytz

from core.database import db
from core.security import rate_limiter, validator
from core.config import config
from locales.i18n import t
from utils.helpers import (
    get_user_lang, get_user_timezone, parse_deadline,
    build_task_embed, build_task_list_embed,
    ensure_user, format_deadline,
)

log = logging.getLogger(__name__)

TASKS_PER_PAGE = 6


# ─────────────────────────────────────────────────────────────────────────────
# Helper: safe respond
# ─────────────────────────────────────────────────────────────────────────────

async def _safe_respond(
    interaction: discord.Interaction, content: str, ephemeral: bool = True
) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(content, ephemeral=ephemeral)
    except Exception as exc:
        log.warning("safe_respond failed: %s", exc)


async def _send_dm(
    user: discord.User | discord.Member,
    content: str = "",
    embed: discord.Embed | None = None,
) -> None:
    """Send a DM silently — ignores Forbidden (DMs disabled)."""
    try:
        if embed:
            await user.send(content=content or None, embed=embed)
        else:
            await user.send(content=content)
    except discord.Forbidden:
        log.debug("DM to %s blocked (DMs disabled)", user.id)
    except Exception as exc:
        log.warning("_send_dm failed for %s: %s", user.id, exc)


def _disable_all(view: ui.View) -> None:
    """Disable every item in a view."""
    for item in view.children:
        try:
            item.disabled = True  # type: ignore[attr-defined]
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Modals
# ─────────────────────────────────────────────────────────────────────────────

class AddTaskModal(ui.Modal):
    """Modal for creating a new task (or subtask).
    Priority is chosen via PrioritySelectView BEFORE this modal opens.
    """

    def __init__(
        self,
        lang: str,
        priority: int = 0,
        category_id: Optional[int] = None,
        parent_task_id: Optional[int] = None,
    ) -> None:
        title_key = "subtask_add_title" if parent_task_id else "task_add_title"
        super().__init__(title=t(title_key, lang))
        self.lang           = lang
        self.priority       = priority
        self.category_id    = category_id
        self.parent_task_id = parent_task_id

        self.task_name = ui.TextInput(
            label=t("task_name_label", lang),
            placeholder=t("task_name_placeholder", lang),
            max_length=200, required=True,
        )
        self.deadline = ui.TextInput(
            label=t("task_deadline_label", lang),
            placeholder=t("task_deadline_placeholder", lang),
            max_length=20, required=True,
        )
        self.description = ui.TextInput(
            label=t("task_desc_label", lang),
            placeholder=t("task_desc_placeholder", lang),
            style=discord.TextStyle.paragraph,
            max_length=1000, required=False,
        )
        self.tags = ui.TextInput(
            label=t("task_tags_label", lang),
            placeholder=t("task_tags_placeholder", lang),
            max_length=200, required=False,
        )
        self.add_item(self.task_name)
        self.add_item(self.deadline)
        self.add_item(self.description)
        self.add_item(self.tags)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        uid  = str(interaction.user.id)
        lang = self.lang

        # ── Rate-limit ──────────────────────────────────────────────────────
        if rate_limiter.check_task_creation(uid):
            secs = rate_limiter.remaining_block_seconds(uid)
            await _safe_respond(
                interaction,
                t("task_rate_limited", lang, limit=config.rate_limit.tasks_per_hour, seconds=secs),
            )
            return

        # ── Validate name ───────────────────────────────────────────────────
        ok, name_or_err = validator.validate_task_name(self.task_name.value)
        if not ok:
            err_msg = t(name_or_err, lang)
            await _safe_respond(interaction, err_msg)
            await _send_dm(interaction.user, f"⚠️ **Input Error**\n{err_msg}")
            return
        task_name = name_or_err

        # ── Priority already validated in Select View ──────────────
        priority = self.priority

        # ── Validate description ─────────────────────────────────────────────
        description: Optional[str] = None
        if self.description.value:
            ok_d, desc_or_err = validator.validate_description(self.description.value)
            if not ok_d:
                await _safe_respond(interaction, t(desc_or_err, lang))
                return
            description = desc_or_err

        # ── Validate tags ────────────────────────────────────────────────────
        tags: Optional[str] = None
        if self.tags.value:
            ts = validator.sanitize(self.tags.value, 200)
            if validator.is_suspicious(ts):
                await _safe_respond(interaction, t("err_suspicious", lang))
                return
            tags = ts

        # ── Validate deadline ────────────────────────────────────────────────
        tz_name = await get_user_timezone(uid)
        dt = parse_deadline(self.deadline.value, tz_name)
        if dt is None:
            err_msg = t("task_invalid_deadline", lang)
            await _safe_respond(interaction, err_msg)
            await _send_dm(
                interaction.user,
                f"⚠️ **Invalid Deadline**\n{err_msg}\n"
                "💡 Format: `DD/MM/YYYY HH:MM` e.g. `31/12/2026 23:59`",
            )
            return
        if dt < datetime.now(pytz.utc):
            await _safe_respond(interaction, t("task_past_deadline", lang))
            return

        # ── Insert ───────────────────────────────────────────────────────────
        await ensure_user(uid, lang)
        try:
            cur = await db.aexecute(
                """INSERT INTO tasks
                   (task, deadline, priority, description, tags,
                    category_id, parent_task_id, owner_id)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (task_name, dt.isoformat(), priority, description, tags,
                 self.category_id, self.parent_task_id, uid),
            )
            task_id = cur.lastrowid
            await db.alog_action(uid, "task_created", str(task_id), task_name)
            db.invalidate_stats(uid)
        except Exception as exc:
            log.error("Task insert failed: %s", exc)
            await _safe_respond(interaction, t("err_db", lang))
            return

        row = await db.afetchone("SELECT * FROM tasks WHERE task_id=?", (task_id,))
        embed = build_task_embed(row, lang, tz_name)
        view  = TaskActionView(task_id, uid, lang,
                               current_priority=priority)
        success_key = "subtask_created" if self.parent_task_id else "task_created"
        success_msg = t(success_key, lang, task_id=task_id)

        if interaction.message:
            # Replaces the public Dropdown message with the Task Details!
            await interaction.response.edit_message(
                content=success_msg, embed=embed, view=view,
            )
        else:
            await interaction.response.send_message(
                success_msg, embed=embed, view=view,
            )
        dm_embed = discord.Embed(
            title="✅ " + ("สร้าง Task สำเร็จ!" if lang == "th" else "Task Created!"),
            description=f"**#{task_id} — {task_name[:80]}**",
            color=0x57F287,
        )
        dm_embed.set_footer(text="To-Do List Bot Gen 2")
        await _send_dm(interaction.user, embed=dm_embed)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.error("AddTaskModal.on_error: %s", error, exc_info=True)
        lang = await get_user_lang(interaction.user.id)
        await _safe_respond(interaction, t("err_generic", lang))


class EditTaskModal(ui.Modal):
    """Modal for editing an existing task — pre-fills current values."""

    def __init__(self, task_row, lang: str) -> None:
        super().__init__(title=t("task_edit_title", lang, task_id=task_row["task_id"]))
        self.lang    = lang
        self.task_id           = task_row["task_id"]
        self.uid               = task_row["owner_id"]
        self._current_priority = task_row["priority"]  # kept from DB; changed via PriorityEditSelect

        # Pre-fill in user-friendly format (sync is fine here — it's pure string ops)
        tz_name = "Asia/Bangkok"   # fallback; we'll properly fetch in on_submit
        current_dl = format_deadline(task_row["deadline"], tz_name) if task_row["deadline"] else ""

        self.task_name = ui.TextInput(
            label=t("task_name_label", lang),
            default=task_row["task"], max_length=200,
        )
        self.deadline = ui.TextInput(
            label=t("task_deadline_label", lang),
            default=current_dl,
            placeholder=t("task_deadline_placeholder", lang),
            max_length=20,
        )
        self.priority = ui.TextInput(
            label=t("task_priority_label", lang),
            default=str(task_row["priority"]), max_length=1,
        )
        self.description = ui.TextInput(
            label=t("task_desc_label", lang),
            default=(task_row["description"] or "")[:1000],
            style=discord.TextStyle.paragraph,
            max_length=1000, required=False,
        )
        self.tags = ui.TextInput(
            label=t("task_tags_label", lang),
            default=(task_row["tags"] or "")[:200],
            max_length=200, required=False,
        )
        self.add_item(self.task_name)
        self.add_item(self.deadline)
        self.add_item(self.priority)
        self.add_item(self.description)
        self.add_item(self.tags)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        uid  = str(interaction.user.id)
        lang = self.lang

        ok, name_or_err = validator.validate_task_name(self.task_name.value)
        if not ok:
            await _safe_respond(interaction, t(name_or_err, lang))
            return

        prio_raw = self.priority.value.strip()
        if not prio_raw.isdigit() or int(prio_raw) not in range(8):
            await _safe_respond(interaction, t("task_invalid_priority", lang))
            return
        prio_val = int(prio_raw)

        tz_name = await get_user_timezone(uid)
        dt = parse_deadline(self.deadline.value, tz_name)
        if dt is None:
            await _safe_respond(interaction, t("task_invalid_deadline", lang))
            return

        description: Optional[str] = None
        if self.description.value:
            ok_d, desc_or_err = validator.validate_description(self.description.value)
            if not ok_d:
                await _safe_respond(interaction, t(desc_or_err, lang))
                return
            description = desc_or_err

        tags: Optional[str] = None
        if self.tags.value:
            ts = validator.sanitize(self.tags.value, 200)
            if validator.is_suspicious(ts):
                await _safe_respond(interaction, t("err_suspicious", lang))
                return
            tags = ts

        try:
            await db.aexecute(
                """UPDATE tasks SET task=?, deadline=?, priority=?, description=?,
                   tags=?, dm_reminded=0, updated_at=CURRENT_TIMESTAMP
                   WHERE task_id=? AND owner_id=?""",
                (name_or_err, dt.isoformat(), prio_val,
                 description, tags, self.task_id, uid),
            )
            await db.alog_action(uid, "task_edited", str(self.task_id), name_or_err)
            db.invalidate_stats(uid)
        except Exception as exc:
            log.error("Task edit failed: %s", exc)
            await _safe_respond(interaction, t("err_db", lang))
            return

        row   = await db.afetchone("SELECT * FROM tasks WHERE task_id=?", (self.task_id,))
        embed = build_task_embed(row, lang, tz_name)
        view  = TaskActionView(self.task_id, uid, lang,
                               current_priority=prio_val)
        await interaction.response.send_message(
            t("task_edit_success", lang), embed=embed, view=view,
        )
        dm_embed = discord.Embed(
            title="✏️ " + ("แก้ไข Task สำเร็จ" if lang == "th" else "Task Updated"),
            description=f"**#{self.task_id} — {name_or_err[:80]}**",
            color=0x5865F2,
        )
        dm_embed.set_footer(text="To-Do List Bot Gen 2")
        await _send_dm(interaction.user, embed=dm_embed)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.error("EditTaskModal.on_error: %s", error, exc_info=True)
        lang = await get_user_lang(interaction.user.id)
        await _safe_respond(interaction, t("err_generic", lang))


# ─────────────────────────────────────────────────────────────────────────────
# Delete Confirmation
# ─────────────────────────────────────────────────────────────────────────────

class DeleteConfirmView(ui.View):
    """30-second confirmation dialog before permanent deletion."""

    def __init__(self, task_id: int, uid: str, lang: str) -> None:
        super().__init__(timeout=30)
        self.task_id  = task_id
        self.uid      = uid
        self.lang     = lang
        self._message: Optional[discord.Message] = None

    async def on_timeout(self) -> None:
        _disable_all(self)
        if self._message:
            try:
                await self._message.edit(
                    content=f"⌛ {'หมดเวลายืนยัน' if self.lang == 'th' else 'Confirmation timed out.'}",
                    view=self,
                )
            except Exception:
                pass

    @ui.button(label="🗑️ Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if str(interaction.user.id) != self.uid:
            await _safe_respond(interaction, t("permission_denied", self.lang))
            return
        try:
            await db.aexecute(
                "DELETE FROM tasks WHERE task_id=? AND owner_id=?",
                (self.task_id, self.uid),
            )
            await db.alog_action(self.uid, "task_deleted", str(self.task_id))
            db.invalidate_stats(self.uid)
        except Exception as exc:
            log.error("Task delete failed: %s", exc)
            await _safe_respond(interaction, t("err_db", self.lang))
            return
        self.stop()
        await interaction.response.edit_message(
            content=t("task_deleted", self.lang, task_id=self.task_id),
            embed=None, view=None,
        )
        dm_embed = discord.Embed(
            title="🗑️ " + ("ลบ Task เรียบร้อย" if self.lang == "th" else "Task Deleted"),
            description=(
                f"Task **#{self.task_id}** ถูกลบแล้ว"
                if self.lang == "th"
                else f"Task **#{self.task_id}** has been permanently deleted."
            ),
            color=0xED4245,
        )
        dm_embed.set_footer(text="To-Do List Bot Gen 2")
        await _send_dm(interaction.user, embed=dm_embed)

    @ui.button(label="✖ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(
            content=t("cancel", self.lang), embed=None, view=None,
        )


# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# Priority constants — single source of truth for labels + colors
# ─────────────────────────────────────────────────────────────────────────────

# (value, emoji, color_name) — used by both PrioritySelect and PriorityEditSelect
_PRIORITY_OPTIONS = [
    (0, "⬜", "priority_0"),
    (1, "🟦", "priority_1"),
    (2, "🟩", "priority_2"),
    (3, "🟨", "priority_3"),
    (4, "🟧", "priority_4"),
    (5, "🟥", "priority_5"),
    (6, "🔴", "priority_6"),
    (7, "🆘", "priority_7"),
]


def _build_priority_options(lang: str, current: int = -1) -> list[discord.SelectOption]:
    """Build the 8 priority SelectOptions with label + description from i18n."""
    return [
        discord.SelectOption(
            label=t(f"priority_{v}", lang),
            description=t(f"priority_{v}_desc", lang)[:100],
            value=str(v),
            emoji=emoji,
            default=(v == current),
        )
        for v, emoji, _ in _PRIORITY_OPTIONS
    ]


# ─────────────────────────────────────────────────────────────────────────────
# PrioritySelectView  (shown BEFORE AddTaskModal — step 1 of /add flow)
# ─────────────────────────────────────────────────────────────────────────────

class _PriorityForAddSelect(ui.Select):
    """Priority dropdown used in PrioritySelectView (step 1 of /add)."""

    def __init__(self, author_id: str, lang: str, category_id: Optional[int], parent_task_id: Optional[int]) -> None:
        super().__init__(
            placeholder=t("priority_select_placeholder", lang),
            options=_build_priority_options(lang, current=0),
            min_values=1,
            max_values=1,
            row=0,
        )
        self.author_id      = author_id
        self.lang           = lang
        self.category_id    = category_id
        self.parent_task_id = parent_task_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.author_id:
            await _safe_respond(interaction, t("permission_denied", self.lang))
            return

        priority = int(self.values[0])
        # Open AddTaskModal with the chosen priority
        await interaction.response.send_modal(
            AddTaskModal(self.lang, priority=priority,
                         category_id=self.category_id,
                         parent_task_id=self.parent_task_id)
        )
        # Stop the view so it doesn't trigger on_timeout and overwrite the message later!
        self.view.stop()


class PrioritySelectView(ui.View):
    """
    Step 1 of the /add flow: show a rich Priority dropdown.
    After the user selects a priority, AddTaskModal opens automatically.
    """

    def __init__(self, author_id: str, lang: str,
                 category_id: Optional[int] = None,
                 parent_task_id: Optional[int] = None) -> None:
        super().__init__(timeout=120)
        self.lang = lang
        self.author_id = author_id
        self.add_item(_PriorityForAddSelect(author_id, lang, category_id, parent_task_id))

    async def on_timeout(self) -> None:
        # Edit the message to say it timed out instead of leaving the dropdown
        for child in self.children:
            child.disabled = True
        # Note: on_timeout in a View can't directly edit the message without storing it,
        # but since we want to keep it simple, we just disable the view.
        # It's better to store `self.message` when sending.
        if hasattr(self, "message") and self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# PriorityEditSelect  (shown inside TaskActionView — change priority inline)
# ─────────────────────────────────────────────────────────────────────────────

class PriorityEditSelect(ui.Select):
    """
    Inline priority dropdown inside TaskActionView.
    Immediately updates the task's priority in the DB when the user picks a level.
    Shown on row 3 (below the Subtask button).
    """

    def __init__(self, task_id: int, current_priority: int, lang: str) -> None:
        super().__init__(
            custom_id=f"task_{task_id}_psel",
            placeholder=t("priority_select_placeholder", lang),
            options=_build_priority_options(lang, current=current_priority),
            min_values=1,
            max_values=1,
            row=3,
        )
        self.lang = lang

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TaskActionView = self.view  # type: ignore[assignment]
        lang = self.lang
        if str(interaction.user.id) != view.uid:
            await _safe_respond(interaction, t("permission_denied", lang))
            return

        new_priority = int(self.values[0])
        try:
            await db.aexecute(
                "UPDATE tasks SET priority=?, updated_at=CURRENT_TIMESTAMP WHERE task_id=? AND owner_id=?",
                (new_priority, view.task_id, view.uid),
            )
            await db.alog_action(view.uid, "task_priority_changed",
                                 str(view.task_id), str(new_priority))
            db.invalidate_stats(view.uid)
        except Exception as exc:
            log.error("Priority update failed task_id=%d: %s", view.task_id, exc)
            await _safe_respond(interaction, t("err_db", lang))
            return

        prio_label = t(f"priority_{new_priority}", lang)
        await _safe_respond(
            interaction,
            t("priority_changed", lang, task_id=view.task_id, priority=prio_label),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Category Select  (shown inside TaskActionView)
# ─────────────────────────────────────────────────────────────────────────────

class CategorySelect(ui.Select):
    """Dropdown to quickly reassign a task's category."""

    def __init__(self, task_id: int, categories: list, current_cat_id: Optional[int], lang: str) -> None:
        options = [
            discord.SelectOption(
                label="— " + ("ไม่มีหมวดหมู่" if lang == "th" else "No Category"),
                value="0",
                default=(current_cat_id is None),
            )
        ]
        for cat in categories[:24]:   # Discord max 25 options
            options.append(
                discord.SelectOption(
                    label=f"{cat['emoji']} {cat['name']}"[:100],
                    value=str(cat["category_id"]),
                    default=(cat["category_id"] == current_cat_id),
                )
            )
        placeholder = "🏷️ เปลี่ยนหมวดหมู่..." if lang == "th" else "🏷️ Change category..."
        super().__init__(
            custom_id=f"task_{task_id}_csel",
            placeholder=placeholder, options=options,
            row=2, min_values=1, max_values=1,
        )
        self.lang = lang

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TaskActionView = self.view  # type: ignore[assignment]
        lang = self.lang
        if str(interaction.user.id) != view.uid:
            await _safe_respond(interaction, t("permission_denied", lang))
            return
        new_cat = int(self.values[0])
        cat_val: Optional[int] = None if new_cat == 0 else new_cat
        try:
            await db.aexecute(
                "UPDATE tasks SET category_id=?, updated_at=CURRENT_TIMESTAMP WHERE task_id=? AND owner_id=?",
                (cat_val, view.task_id, view.uid),
            )
            await db.alog_action(view.uid, "task_category_changed", str(view.task_id), str(cat_val))
        except Exception as exc:
            log.error("Category update failed: %s", exc)
            await _safe_respond(interaction, t("err_db", lang))
            return
        msg = (
            f"🏷️ เปลี่ยนหมวดหมู่สำเร็จ!" if lang == "th"
            else "🏷️ Category updated!"
        )
        await _safe_respond(interaction, msg)


# ─────────────────────────────────────────────────────────────────────────────
# Task Action View
# ─────────────────────────────────────────────────────────────────────────────

class TaskActionView(ui.View):
    """
    Full-featured action view attached to a task embed.
    Row 0: Done | Edit | Pin/Unpin
    Row 1: Delete | Snooze +1d
    Row 2: + Subtask | [Category Select]
    """

    def __init__(
        self,
        task_id: int,
        uid: str,
        lang: str,
        is_pinned: bool = False,
        categories: Optional[list] = None,
        current_cat_id: Optional[int] = None,
        current_priority: int = 0,
    ) -> None:
        super().__init__(timeout=None)  # Persistent — buttons never expire
        self.task_id   = task_id
        self.uid       = uid
        self.lang      = lang
        self.is_pinned = is_pinned

        # Encode task_id into every button's custom_id so interactions survive bot restarts.
        # Buttons defined via @ui.button get short ids ("done", "edit", …) which we prefix here.
        for child in self.children:
            if hasattr(child, "custom_id") and child.custom_id:
                child.custom_id = f"task_{task_id}_{child.custom_id}"

        self._update_pin_label()

        # Priority edit dropdown — always shown on row 3
        self.add_item(PriorityEditSelect(task_id, current_priority, lang))

        # Category select on row 2 — only when categories provided
        if categories is not None:
            self.add_item(CategorySelect(task_id, categories, current_cat_id, lang))


    def _update_pin_label(self) -> None:
        pin_cid = f"task_{self.task_id}_pin"
        for item in self.children:
            if getattr(item, "custom_id", None) == pin_cid:
                item.label = "📌 Unpin" if self.is_pinned else "📌 Pin"  # type: ignore[attr-defined]

    async def on_timeout(self) -> None:
        pass  # timeout=None — persistent views never expire; kept as no-op for safety

    def _check_owner(self, interaction: discord.Interaction) -> bool:
        return str(interaction.user.id) == self.uid

    # ── Mark Done ─────────────────────────────────────────────────────────────

    @ui.button(label="✅ Done", style=discord.ButtonStyle.success, row=0, custom_id="done")
    async def mark_done(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = await get_user_lang(interaction.user.id)
        if not self._check_owner(interaction):
            await _safe_respond(interaction, t("permission_denied", lang))
            return
        row = await db.afetchone("SELECT status FROM tasks WHERE task_id=?", (self.task_id,))
        if not row:
            await _safe_respond(interaction, t("task_not_found", lang, task_id=self.task_id))
            return
        if row["status"] == "Completed":
            await _safe_respond(interaction, t("task_already_done", lang))
            return
        if row["status"] == "Cancelled":
            await _safe_respond(interaction, t("task_already_cancelled", lang))
            return
        await db.aexecute(
            "UPDATE tasks SET status='Completed', updated_at=CURRENT_TIMESTAMP WHERE task_id=?",
            (self.task_id,),
        )
        await db.alog_action(self.uid, "task_completed", str(self.task_id))
        db.invalidate_stats(self.uid)
        button.disabled = True
        button.style    = discord.ButtonStyle.secondary
        self.stop()
        await _safe_respond(interaction, t("task_marked_done", lang, task_id=self.task_id))
        dm_embed = discord.Embed(
            title="✅ " + ("Task เสร็จแล้ว!" if lang == "th" else "Task Completed!"),
            description=(
                f"Task **#{self.task_id}** ถูกทำเครื่องหมายว่าเสร็จแล้ว"
                if lang == "th"
                else f"Task **#{self.task_id}** marked as completed."
            ),
            color=0x57F287,
        )
        dm_embed.set_footer(text="To-Do List Bot Gen 2")
        await _send_dm(interaction.user, embed=dm_embed)

    # ── Edit ──────────────────────────────────────────────────────────────────

    @ui.button(label="✏️ Edit", style=discord.ButtonStyle.blurple, row=0, custom_id="edit")
    async def edit(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = await get_user_lang(interaction.user.id)
        if not self._check_owner(interaction):
            await _safe_respond(interaction, t("permission_denied", lang))
            return
        row = await db.afetchone("SELECT * FROM tasks WHERE task_id=?", (self.task_id,))
        if not row:
            await _safe_respond(interaction, t("task_not_found", lang, task_id=self.task_id))
            return
        await interaction.response.send_modal(EditTaskModal(row, lang))

    # ── Pin / Unpin ───────────────────────────────────────────────────────────

    @ui.button(label="📌 Pin", style=discord.ButtonStyle.secondary, row=0, custom_id="pin")
    async def pin_toggle(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = await get_user_lang(interaction.user.id)
        if not self._check_owner(interaction):
            await _safe_respond(interaction, t("permission_denied", lang))
            return
        # Re-fetch current pin state from DB — self.is_pinned can be stale after bot restart
        pin_row = await db.afetchone(
            "SELECT is_pinned FROM tasks WHERE task_id=? AND owner_id=?",
            (self.task_id, self.uid),
        )
        if not pin_row:
            await _safe_respond(interaction, t("task_not_found", lang, task_id=self.task_id))
            return
        current_pinned = bool(pin_row["is_pinned"])
        new_val = 0 if current_pinned else 1
        await db.aexecute(
            "UPDATE tasks SET is_pinned=? WHERE task_id=? AND owner_id=?",
            (new_val, self.task_id, self.uid),
        )
        self.is_pinned = bool(new_val)
        action_str = "task_pinned" if self.is_pinned else "task_unpinned"
        await db.alog_action(self.uid, action_str, str(self.task_id))
        self._update_pin_label()
        msg_key = "task_pinned" if self.is_pinned else "task_unpinned"
        await _safe_respond(interaction, t(msg_key, lang, task_id=self.task_id))
        pin_label = (
            ("📌 ปักหมุดแล้ว" if self.is_pinned else "📌 เลิกปักหมุดแล้ว")
            if lang == "th"
            else ("📌 Pinned" if self.is_pinned else "📌 Unpinned")
        )
        dm_embed = discord.Embed(
            title=pin_label,
            description=f"Task **#{self.task_id}**",
            color=0xFEE75C,
        )
        dm_embed.set_footer(text="To-Do List Bot Gen 2")
        await _send_dm(interaction.user, embed=dm_embed)

    # ── Delete ────────────────────────────────────────────────────────────────

    @ui.button(label="🗑️ Delete", style=discord.ButtonStyle.danger, row=1, custom_id="del")
    async def delete(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = await get_user_lang(interaction.user.id)
        if not self._check_owner(interaction):
            await _safe_respond(interaction, t("permission_denied", lang))
            return
        row = await db.afetchone("SELECT task FROM tasks WHERE task_id=?", (self.task_id,))
        if not row:
            await _safe_respond(interaction, t("task_not_found", lang, task_id=self.task_id))
            return
        confirm = DeleteConfirmView(self.task_id, self.uid, lang)
        await interaction.response.send_message(
            t("task_delete_confirm", lang, task_name=row["task"]),
            view=confirm, ephemeral=True,
        )

    # ── Snooze (+1 Day) ───────────────────────────────────────────────────────

    @ui.button(label="⏰ Snooze +1d", style=discord.ButtonStyle.secondary, row=1, custom_id="snz")
    async def snooze(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = await get_user_lang(interaction.user.id)
        if not self._check_owner(interaction):
            await _safe_respond(interaction, t("permission_denied", lang))
            return
        row = await db.afetchone(
            "SELECT deadline, status FROM tasks WHERE task_id=?", (self.task_id,)
        )
        if not row:
            await _safe_respond(interaction, t("task_not_found", lang, task_id=self.task_id))
            return
        if row["status"] != "Pending":
            await _safe_respond(
                interaction,
                "⚠️ " + ("เลื่อนได้เฉพาะ Task ที่ยังค้างอยู่" if lang == "th" else "Can only snooze Pending tasks"),
            )
            return
        try:
            from datetime import timedelta
            dt = datetime.fromisoformat(row["deadline"])
            if dt.tzinfo is None:
                dt = pytz.utc.localize(dt)
            new_dl = (dt + timedelta(days=1)).isoformat()
            await db.aexecute(
                "UPDATE tasks SET deadline=?, dm_reminded=0, updated_at=CURRENT_TIMESTAMP WHERE task_id=? AND owner_id=?",
                (new_dl, self.task_id, self.uid),
            )
            await db.alog_action(self.uid, "task_snoozed", str(self.task_id), "+1d")
            db.invalidate_stats(self.uid)
            tz_name     = await get_user_timezone(self.uid)
            new_dl_fmt  = format_deadline(new_dl, tz_name)
            snooze_msg = (
                f"⏰ Task **#{self.task_id}** เลื่อนเป็น `{new_dl_fmt}`"
                if lang == "th"
                else f"⏰ Task **#{self.task_id}** snoozed to `{new_dl_fmt}`"
            )
            await _safe_respond(interaction, snooze_msg)
        except Exception as exc:
            log.error("Snooze failed task_id=%d: %s", self.task_id, exc)
            await _safe_respond(interaction, t("err_generic", lang))

    # ── Add Subtask ───────────────────────────────────────────────────────────

    @ui.button(label="➕ Subtask", style=discord.ButtonStyle.secondary, row=4, custom_id="sub")
    async def add_subtask(self, interaction: discord.Interaction, button: ui.Button) -> None:
        lang = await get_user_lang(interaction.user.id)
        if not self._check_owner(interaction):
            await _safe_respond(interaction, t("permission_denied", lang))
            return
        row = await db.afetchone(
            "SELECT parent_task_id FROM tasks WHERE task_id=?", (self.task_id,)
        )
        if row and row["parent_task_id"] is not None:
            await _safe_respond(interaction, t("subtask_no_nested", lang))
            return
            
        uid = str(interaction.user.id)
        # Open priority selector first, then modal
        view = PrioritySelectView(uid, lang, parent_task_id=self.task_id)
        embed = discord.Embed(
            title=t("priority_select_title", lang),
            description=t("priority_select_desc", lang),
            color=0x5865F2,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ─────────────────────────────────────────────────────────────────────────────
# Task Filter Select
# ─────────────────────────────────────────────────────────────────────────────

class TaskFilterSelect(ui.Select):
    """Dropdown to switch the active filter in a TaskListView."""

    def __init__(self, lang: str, current: str) -> None:
        options = [
            discord.SelectOption(
                label=t("tasks_filter_pending", lang), value="Pending",
                emoji="⏳", default=(current == "Pending"),
            ),
            discord.SelectOption(
                label=t("tasks_filter_done", lang), value="Completed",
                emoji="✅", default=(current == "Completed"),
            ),
            discord.SelectOption(
                label=t("tasks_filter_overdue", lang), value="overdue",
                emoji="🚨", default=(current == "overdue"),
            ),
            discord.SelectOption(
                label=t("tasks_filter_today", lang), value="today",
                emoji="📅", default=(current == "today"),
            ),
            discord.SelectOption(
                label="📌 Pinned", value="pinned",
                default=(current == "pinned"),
            ),
            discord.SelectOption(
                label=t("tasks_filter_all", lang), value="all",
                emoji="📋", default=(current == "all"),
            ),
        ]
        super().__init__(
            placeholder=t("list_filter_placeholder", lang),
            options=options, row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TaskListView = self.view  # type: ignore[assignment]
        view.filter_status = self.values[0]
        view.page = 1
        await interaction.response.defer()
        await view.update_message(interaction)


# ─────────────────────────────────────────────────────────────────────────────
# Task List View
# ─────────────────────────────────────────────────────────────────────────────

class TaskListView(ui.View):
    """Paginated task list with filter Select menu and enhanced nav buttons."""

    def __init__(
        self,
        uid: str,
        lang: str,
        tz_name: str,
        filter_status: str = "Pending",
    ) -> None:
        super().__init__(timeout=600)
        self.uid           = uid
        self.lang          = lang
        self.tz_name       = tz_name
        self.filter_status = filter_status
        self.page          = 1
        self._filter_select = TaskFilterSelect(lang, filter_status)
        self.add_item(self._filter_select)

    async def on_timeout(self) -> None:
        _disable_all(self)

    async def _fetch_page(self) -> tuple[list, int, int]:
        now = datetime.now(pytz.utc).isoformat()
        fs  = self.filter_status

        if fs == "overdue":
            base   = "SELECT * FROM tasks WHERE owner_id=? AND parent_task_id IS NULL AND status='Pending' AND deadline<?"
            params: list = [self.uid, now]
        elif fs == "today":
            today_start = datetime.now(pytz.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            today_end   = datetime.now(pytz.utc).replace(hour=23, minute=59, second=59).isoformat()
            base   = "SELECT * FROM tasks WHERE owner_id=? AND parent_task_id IS NULL AND status='Pending' AND deadline BETWEEN ? AND ?"
            params = [self.uid, today_start, today_end]
        elif fs == "pinned":
            base   = "SELECT * FROM tasks WHERE owner_id=? AND parent_task_id IS NULL AND is_pinned=1"
            params = [self.uid]
        elif fs == "all":
            base   = "SELECT * FROM tasks WHERE owner_id=? AND parent_task_id IS NULL"
            params = [self.uid]
        else:
            base   = "SELECT * FROM tasks WHERE owner_id=? AND parent_task_id IS NULL AND status=?"
            params = [self.uid, fs]

        count_row   = await db.afetchone(f"SELECT COUNT(*) AS c FROM ({base})", params)
        total       = count_row["c"] if count_row else 0
        total_pages = max(1, (total + TASKS_PER_PAGE - 1) // TASKS_PER_PAGE)
        self.page   = max(1, min(self.page, total_pages))
        offset      = (self.page - 1) * TASKS_PER_PAGE

        tasks = await db.afetchall(
            f"{base} ORDER BY is_pinned DESC, priority DESC, deadline ASC LIMIT ? OFFSET ?",
            params + [TASKS_PER_PAGE, offset],
        )
        return tasks, self.page, total_pages

    def _update_nav_buttons(self, page: int, total_pages: int) -> None:
        for item in self.children:
            if isinstance(item, ui.Button):
                cid = getattr(item, "custom_id", None)
                if cid == "lv_first":
                    item.disabled = (page <= 1)
                elif cid == "lv_prev":
                    item.disabled = (page <= 1)
                elif cid == "lv_next":
                    item.disabled = (page >= total_pages)
                elif cid == "lv_last":
                    item.disabled = (page >= total_pages)

    async def update_message(self, interaction: discord.Interaction) -> None:
        tasks, page, total_pages = await self._fetch_page()
        fs = self.filter_status
        # Build filter label — map special values to i18n keys
        filter_key_map = {
            "overdue": "tasks_filter_overdue",
            "today":   "tasks_filter_today",
            "pinned":  "tasks_filter_pinned",
            "all":     "tasks_filter_all",
            "Pending":   "tasks_filter_Pending",
            "Completed": "tasks_filter_Completed",
        }
        filter_label = t(filter_key_map.get(fs, f"tasks_filter_{fs}"), self.lang)
        embed = build_task_list_embed(tasks, page, total_pages, self.lang, self.tz_name, filter_label)
        self._update_nav_buttons(page, total_pages)
        await interaction.edit_original_response(embed=embed, view=self)

    @ui.button(emoji="⏮", style=discord.ButtonStyle.secondary, custom_id="lv_first", row=3)
    async def first_page(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer()
        self.page = 1
        await self.update_message(interaction)

    @ui.button(emoji="◀", style=discord.ButtonStyle.secondary, custom_id="lv_prev", row=3)
    async def prev_page(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer()
        self.page -= 1
        await self.update_message(interaction)

    @ui.button(emoji="🔄", style=discord.ButtonStyle.secondary, custom_id="lv_refresh", row=3)
    async def refresh(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer()
        await self.update_message(interaction)

    @ui.button(emoji="▶", style=discord.ButtonStyle.secondary, custom_id="lv_next", row=3)
    async def next_page(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer()
        self.page += 1
        await self.update_message(interaction)

    @ui.button(emoji="⏭", style=discord.ButtonStyle.secondary, custom_id="lv_last", row=3)
    async def last_page(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer()
        _, _, total_pages = await self._fetch_page()
        self.page = total_pages
        await self.update_message(interaction)


# ─────────────────────────────────────────────────────────────────────────────
# Language Select
# ─────────────────────────────────────────────────────────────────────────────

class LanguageView(ui.View):
    """Language selection buttons (TH / EN)."""

    def __init__(self, current_lang: str) -> None:
        super().__init__(timeout=120)
        self.current_lang = current_lang

    async def on_timeout(self) -> None:
        _disable_all(self)

    @ui.button(label="🇹🇭 ไทย", style=discord.ButtonStyle.primary, custom_id="lang_th")
    async def lang_th(self, interaction: discord.Interaction, button: ui.Button) -> None:
        uid = str(interaction.user.id)
        await ensure_user(uid)
        await db.aexecute("UPDATE users SET lang='th' WHERE user_id=?", (uid,))
        db.user_cache.invalidate(uid)
        await db.alog_action(uid, "lang_changed", detail="th")
        self.stop()
        await interaction.response.send_message(t("lang_changed", "th"), ephemeral=True)

    @ui.button(label="🇬🇧 English", style=discord.ButtonStyle.primary, custom_id="lang_en")
    async def lang_en(self, interaction: discord.Interaction, button: ui.Button) -> None:
        uid = str(interaction.user.id)
        await ensure_user(uid)
        await db.aexecute("UPDATE users SET lang='en' WHERE user_id=?", (uid,))
        db.user_cache.invalidate(uid)
        await db.alog_action(uid, "lang_changed", detail="en")
        self.stop()
        await interaction.response.send_message(t("lang_changed", "en"), ephemeral=True)


# ─────────────────────────────────────────────────────────────────────────────
# Startup: Re-register all persistent task views
# ─────────────────────────────────────────────────────────────────────────────

async def register_all_persistent_views(bot: discord.Client) -> None:
    """
    Re-register a TaskActionView for every task in the DB so that buttons on
    old Discord messages continue to work after a bot restart.

    How it works:
      - Each button's custom_id encodes the task_id (e.g. "task_42_done").
      - bot.add_view(view) without message_id tells discord.py to match ANY
        incoming component interaction whose custom_id equals one of the
        view children's custom_ids.
      - Result: every task's buttons stay interactive indefinitely.

    Call this once from setup_hook() — before the bot is marked as ready.
    """
    from core.database import db as _db

    rows = await _db.afetchall(
        """SELECT t.task_id, t.owner_id, t.priority, t.is_pinned,
                  COALESCE(u.lang, 'th') AS lang
           FROM tasks t
           LEFT JOIN users u ON t.owner_id = u.user_id
           ORDER BY t.task_id DESC
           LIMIT 5000""",
    )
    count = 0
    for row in rows:
        try:
            view = TaskActionView(
                task_id=row["task_id"],
                uid=row["owner_id"],
                lang=row["lang"],
                is_pinned=bool(row["is_pinned"]) if row["is_pinned"] is not None else False,
                current_priority=row["priority"] if row["priority"] is not None else 0,
            )
            bot.add_view(view)
            count += 1
        except Exception as exc:
            log.warning("Persistent view registration failed task_id=%s: %s", row["task_id"], exc)
    log.info("✓ Registered %d persistent task views (post-restart button coverage)", count)
