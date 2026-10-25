"""
handlers/tasks_cog.py — Slash commands for task management v4 (PostgreSQL)
Changes over v3:
  - SQL placeholders: ? → $N (PostgreSQL/asyncpg)
  - CURRENT_TIMESTAMP → NOW()
  - _async_build_task_embed: uses $1, $2 placeholders
"""
from __future__ import annotations

import logging
import json
import re
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
import pytz

from core.database import db
from core.security import rate_limit_check, rate_limiter, validator
from core.config import config
from locales.i18n import t
from utils.helpers import (
    get_user_lang, get_user_timezone, ensure_user,
    build_task_embed, build_task_list_embed, build_stats_embed, build_csv_export,
    format_deadline, time_left_str, build_task_stats_embed,
)
from utils.conflict_resolver import validate_deadline_defensive, DeadlineValidationError
from handlers.task_views import (
    AddTaskModal, TaskActionView, TaskListView, DeleteConfirmView,
    TASKS_PER_PAGE, _send_dm,
    TodayView, OverdueView, SnoozePresetView,
    _build_today_embed_and_view, _build_overdue_embed_and_view,
)
from recurrence.rules import validate_rule
from gamification import service as gamification_service

log = logging.getLogger(__name__)


async def _async_build_task_embed(row, lang: str, tz_name: str) -> discord.Embed:
    """Async wrapper: fetches subtasks + category then builds the embed."""
    task_id = row["task_id"]

    # Fetch subtasks (non-cancelled and non-deleted only)
    subtasks = await db.afetchall(
        "SELECT task_id, task, status FROM tasks WHERE parent_task_id=$1 AND status != 'Cancelled' AND is_deleted = FALSE ORDER BY task_id ASC",
        (task_id,),
    )

    # Fetch category
    category = None
    cat_id = row.get("category_id") if hasattr(row, "get") else row["category_id"]
    if cat_id:
        category = await db.afetchone(
            "SELECT name, emoji FROM categories WHERE category_id=$1",
            (cat_id,),
        )

    return build_task_embed(row, lang, tz_name,
                            subtasks=subtasks or None,
                            category=category)


# ─────────────────────────────────────────────────────────────────────────────
# Autocomplete helpers
# ─────────────────────────────────────────────────────────────────────────────

async def task_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[int]]:
    """Autocomplete pending/in-progress tasks for task_id parameters.
    Returns up to 25 matching choices in format: '#ID — Task name (time_left)'.
    Filter is pushed into SQL via ILIKE so results are not limited by a pre-fetch cap.
    """
    uid = str(interaction.user.id)
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        if current:
            rows = await db.afetchall(
                """SELECT task_id, task, deadline, status
               FROM tasks
               WHERE owner_id=$1
                 AND is_deleted = FALSE
                 AND status IN ('Pending', 'In_Progress')
                 AND parent_task_id IS NULL
                 AND (task ILIKE $2 OR CAST(task_id AS TEXT) ILIKE $2)
               ORDER BY
                 CASE WHEN deadline < $3 THEN 0 ELSE 1 END,
                 deadline ASC NULLS LAST
               LIMIT 25""",
                (uid, f"%{current}%", now_iso),
            )
        else:
            rows = await db.afetchall(
                """SELECT task_id, task, deadline, status
               FROM tasks
               WHERE owner_id=$1
                 AND is_deleted = FALSE
                 AND status IN ('Pending', 'In_Progress')
                 AND parent_task_id IS NULL
               ORDER BY
                 CASE WHEN deadline < $2 THEN 0 ELSE 1 END,
                 deadline ASC NULLS LAST
               LIMIT 25""",
                (uid, now_iso),
            )
    except Exception as exc:
        log.warning("task_autocomplete error: %s", exc)
        return []

    choices = []
    for row in rows:
        tid   = row["task_id"]
        name  = row["task"][:50]
        tl    = time_left_str(row["deadline"]) if row["deadline"] else "—"
        label = f"#{tid} — {name} ({tl})"
        choices.append(app_commands.Choice(name=label[:100], value=tid))
    return choices[:25]


class TasksCog(commands.Cog, name="Tasks"):
    """All task-related slash commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.message_to_task = app_commands.ContextMenu(
            name="Add to To-Do",
            callback=self.add_message_to_todo,
        )

    async def cog_load(self) -> None:
        self.bot.tree.add_command(self.message_to_task)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.message_to_task.name,
            type=self.message_to_task.type,
        )

    async def add_message_to_todo(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ) -> None:
        """Create a personal task from a selected Discord message."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        tz_name = await get_user_timezone(uid)
        await ensure_user(uid, lang)

        text = (message.content or "").strip()
        if not text:
            await interaction.followup.send(
                t("context_task_empty", lang), ephemeral=True
            )
            return
        ok, name_or_err = validator.validate_task_name(text)
        if not ok:
            await interaction.followup.send(t(name_or_err, lang), ephemeral=True)
            return
        if rate_limiter.check_task_creation(uid):
            seconds = rate_limiter.remaining_block_seconds(uid)
            await interaction.followup.send(
                t("task_rate_limited", lang,
                  limit=config.rate_limit.tasks_per_hour, seconds=seconds),
                ephemeral=True,
            )
            return
        try:
            deadline = validate_deadline_defensive("+1d", tz_name)
        except DeadlineValidationError as exc:
            await interaction.followup.send(
                t(exc.i18n_key, lang, **exc.kwargs), ephemeral=True
            )
            return
        try:
            row = await db.afetchone(
                """INSERT INTO tasks (task, deadline, priority, owner_id, source_message_url)
                   VALUES ($1,$2,0,$3,$4) RETURNING task_id""",
                (name_or_err, deadline.isoformat(), uid, message.jump_url),
            )
            if row is None:
                raise RuntimeError("Task insert returned no task_id")
            task_id = row["task_id"]
            db.query_cache.invalidate_tables(["tasks"])
            await db.alog_action(uid, "task_created", str(task_id), name_or_err)
            db.invalidate_stats(uid)
        except Exception as exc:
            log.error("Context-menu task creation failed: %s", exc, exc_info=True)
            await interaction.followup.send(t("err_db", lang), ephemeral=True)
            return

        await interaction.followup.send(
            t("context_task_created", lang, task_id=task_id), ephemeral=True
        )

    # ─────────────────────────────────────────────────────────────────────
    # /add  — 1-step quick add OR modal
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="add", description="➕ เพิ่ม Task ใหม่ / Add a new task")
    @app_commands.describe(
        task="Task name (skip to open full modal)",
        deadline="Deadline: tomorrow 5pm · next monday · friday noon · in 3 days",
        priority="Priority 0–7 (0=Normal, 3=Medium, 5=Important, 7=Critical)",
    )
    @rate_limit_check("command")
    async def add(
        self,
        interaction: discord.Interaction,
        task: Optional[str] = None,
        deadline: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> None:
        uid     = str(interaction.user.id)
        lang    = await get_user_lang(uid)
        tz_name = await get_user_timezone(uid)
        await ensure_user(uid, lang)

        # Validate priority if specified
        if priority is not None and not (0 <= priority <= 7):
            await interaction.response.send_message(
                t("add_invalid_priority_choice", lang), ephemeral=True
            )
            return

        # ── 1-step quick add: task name provided as slash param ────────────────────────
        if task is not None:
            # Validate inputs
            ok, name_or_err = validator.validate_task_name(task)
            if not ok:
                await interaction.response.send_message(t(name_or_err, lang), ephemeral=True)
                return
            task_name = name_or_err

            # Validate deadline if given; default to +1 day end-of-day if omitted
            deadline_str = deadline or "+1d"
            try:
                dt = validate_deadline_defensive(deadline_str, tz_name)
            except DeadlineValidationError as e:
                await interaction.response.send_message(
                    t(e.i18n_key, lang, **e.kwargs), ephemeral=True
                )
                return

            # Rate limit
            if rate_limiter.check_task_creation(uid):
                secs = rate_limiter.remaining_block_seconds(uid)
                await interaction.response.send_message(
                    t("task_rate_limited", lang,
                      limit=config.rate_limit.tasks_per_hour, seconds=secs),
                    ephemeral=True,
                )
                return

            await interaction.response.defer(thinking=False)

            prio = priority if priority is not None else 0
            try:
                row = await db.afetchone(
                    """INSERT INTO tasks (task, deadline, priority, owner_id)
                       VALUES ($1,$2,$3,$4) RETURNING task_id""",
                    (task_name, dt.isoformat(), prio, uid),
                )
                task_id = row["task_id"]
                await db.alog_action(uid, "task_created", str(task_id), task_name)
                db.invalidate_stats(uid)
            except Exception as exc:
                log.error("Quick-add insert failed: %s", exc)
                await interaction.followup.send(t("err_db", lang), ephemeral=True)
                return

            full_row = await db.afetchone("SELECT * FROM tasks WHERE task_id=$1", (task_id,))
            embed = build_task_embed(full_row, lang, tz_name)
            view  = TaskActionView(task_id, uid, lang, current_priority=prio)
            tl    = time_left_str(dt.isoformat())
            await interaction.followup.send(
                t("add_quick_created", lang, task_name=task_name, task_id=task_id, time_left=tl),
                embed=embed, view=view,
            )
            return

        # ── Modal path: no args — open AddTaskModal directly (priority defaults to 0) ───
        modal = AddTaskModal(lang, priority=priority or 0)
        await interaction.response.send_modal(modal)

    # ─────────────────────────────────────────────────────────────────────────
    # /list
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name="list", description="📋 ดูรายการ Task / View your tasks")
    @rate_limit_check("command")
    async def list_tasks(self, interaction: discord.Interaction) -> None:
        uid     = str(interaction.user.id)
        lang    = await get_user_lang(uid)
        tz_name = await get_user_timezone(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer()

        view             = TaskListView(uid, lang, tz_name, "Pending")
        tasks, page, tot = await view._fetch_page()
        filter_label     = t("tasks_filter_Pending", lang)

        # Count total and overdue for summary line
        now_iso = datetime.now(pytz.utc).isoformat()
        total_row = await db.afetchone(
            "SELECT COUNT(*) AS c FROM tasks WHERE owner_id=$1 AND parent_task_id IS NULL AND is_deleted=FALSE", (uid,)
        )
        overdue_row = await db.afetchone(
            "SELECT COUNT(*) AS c FROM tasks WHERE owner_id=$1 AND parent_task_id IS NULL "
            "AND status='Pending' AND deadline<$2 AND is_deleted=FALSE", (uid, now_iso)
        )
        total_count   = total_row["c"]   if total_row   else 0
        overdue_count = overdue_row["c"] if overdue_row else 0

        embed = build_task_list_embed(
            tasks, page, tot, lang, tz_name, filter_label,
            total_count=total_count, overdue_count=overdue_count,
        )
        view._update_nav_buttons(page, tot)
        view._update_quickaction(tasks)
        await interaction.followup.send(embed=embed, view=view)
        # Store message so on_timeout can edit it with disabled buttons
        view._message = await interaction.original_response()

    # ─────────────────────────────────────────────────────────────────────────
    # /today
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name="today", description="📅 ดู Task วันนี้ / Tasks due today")
    @rate_limit_check("command")
    async def today(self, interaction: discord.Interaction) -> None:
        uid     = str(interaction.user.id)
        lang    = await get_user_lang(uid)
        tz_name = await get_user_timezone(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer()
        embed, view = await _build_today_embed_and_view(uid, lang, tz_name)
        await interaction.followup.send(embed=embed, view=view)

    # ─────────────────────────────────────────────────────────────────────────
    # /overdue
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name="overdue", description="🚨 Task เกินกำหนด / Overdue tasks")
    @rate_limit_check("command")
    async def overdue(self, interaction: discord.Interaction) -> None:
        uid     = str(interaction.user.id)
        lang    = await get_user_lang(uid)
        tz_name = await get_user_timezone(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer()
        embed, view = await _build_overdue_embed_and_view(uid, lang, tz_name)
        await interaction.followup.send(embed=embed, view=view)

    # ─────────────────────────────────────────────────────────────────────────
    # /task — detail view by ID
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name="task", description="📌 ดู Task ตาม ID / View task by ID")
    @app_commands.describe(task_id="Task ID number")
    @app_commands.autocomplete(task_id=task_autocomplete)
    @rate_limit_check("command")
    async def task_detail(self, interaction: discord.Interaction, task_id: int) -> None:
        uid     = str(interaction.user.id)
        lang    = await get_user_lang(uid)
        tz_name = await get_user_timezone(uid)
        await interaction.response.defer()

        row = await db.afetchone("SELECT * FROM tasks WHERE task_id=$1", (task_id,))
        if not row:
            await interaction.followup.send(
                t("task_not_found", lang, task_id=task_id), ephemeral=True
            )
            return
        if row["owner_id"] != uid:
            await interaction.followup.send(t("task_not_owned", lang), ephemeral=True)
            return
        if row.get("is_deleted"):
            await interaction.followup.send(
                t("task_already_in_trash", lang, task_id=task_id), ephemeral=True
            )
            return

        # Fetch categories for the Category Select dropdown
        categories = await db.afetchall(
            "SELECT * FROM categories WHERE owner_id=$1 OR owner_id='system' ORDER BY name",
            (uid,),
        )

        embed = await _async_build_task_embed(row, lang, tz_name)
        view  = TaskActionView(
            task_id, uid, lang,
            is_pinned=bool(row["is_pinned"]) if "is_pinned" in row.keys() else False,
            categories=list(categories),
            current_cat_id=row["category_id"],
            current_priority=row["priority"] if "priority" in row.keys() else 0,
        )
        await interaction.followup.send(embed=embed, view=view)

    # ─────────────────────────────────────────────────────────────────────────
    # /done
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name="done", description="✅ ทำเครื่องหมาย Task เสร็จแล้ว / Mark task done")
    @app_commands.describe(task_id="Task ID number", force="Force complete even if checklist items are incomplete")
    @app_commands.autocomplete(task_id=task_autocomplete)
    @rate_limit_check("command")
    async def done(self, interaction: discord.Interaction, task_id: int, force: bool = False) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await interaction.response.defer(ephemeral=True)

        row = await db.afetchone("SELECT task, status, owner_id, is_deleted FROM tasks WHERE task_id=$1", (task_id,))
        if not row:
            await interaction.followup.send(
                t("task_not_found", lang, task_id=task_id), ephemeral=True
            )
            return
        if row["owner_id"] != uid:
            await interaction.followup.send(t("task_not_owned", lang), ephemeral=True)
            return
        if row.get("is_deleted"):
            await interaction.followup.send(
                t("task_already_in_trash", lang, task_id=task_id), ephemeral=True
            )
            return
        if row["status"] == "Completed":
            await interaction.followup.send(t("task_already_done", lang), ephemeral=True)
            return
        if row["status"] == "Cancelled":
            await interaction.followup.send(t("task_already_cancelled", lang), ephemeral=True)
            return

        if not force:
            from routine_workflows import service as routine_service
            from routine_workflows.views import DoDForceConfirmView

            pending_items = await routine_service.get_pending_checklists(task_id)
            if pending_items:
                confirm_view = DoDForceConfirmView(
                    task_id=task_id,
                    task_name=row["task"],
                    user_id=uid,
                    lang=lang,
                    pending_items=pending_items,
                )
                await interaction.followup.send(
                    embed=confirm_view.make_embed(),
                    view=confirm_view,
                    ephemeral=True,
                )
                return

        awarded = await gamification_service.complete_personal_task(task_id, uid)
        if awarded is None:
            await interaction.followup.send(t("task_already_done", lang), ephemeral=True)
            return
        await db.alog_action(uid, "task_completed", str(task_id))

        done_msg = t("task_done_with_name", lang, task_id=task_id, task_name=row["task"])
        embed = discord.Embed(
            title=done_msg,
            color=0x57F287,
        )
        embed.set_footer(text=t("footer_text", lang))
        await interaction.followup.send(embed=embed)
        dm_embed = discord.Embed(
            title=done_msg,
            color=0x57F287,
        )
        dm_embed.set_footer(text=t("footer_text", lang))
        await _send_dm(interaction.user, embed=dm_embed)

    # ─────────────────────────────────────────────────────────────────────────
    # /delete
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name="delete", description="🗑️ ลบ Task / Delete a task")
    @app_commands.describe(task_id="Task ID to delete")
    @app_commands.autocomplete(task_id=task_autocomplete)
    @rate_limit_check("command")
    async def delete(self, interaction: discord.Interaction, task_id: int) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        # Fetch task name BEFORE responding (send_message with view must be first response)
        row = await db.afetchone("SELECT task, owner_id, is_deleted FROM tasks WHERE task_id=$1", (task_id,))
        if not row:
            await interaction.response.send_message(
                t("task_not_found", lang, task_id=task_id), ephemeral=True
            )
            return
        if row["owner_id"] != uid:
            await interaction.response.send_message(t("task_not_owned", lang), ephemeral=True)
            return
        if row.get("is_deleted"):
            await interaction.response.send_message(
                t("task_already_in_trash", lang, task_id=task_id), ephemeral=True
            )
            return

        view = DeleteConfirmView(task_id, uid, lang)
        confirm_embed = discord.Embed(
            title=t("delete_confirm_title", lang),
            description=t("delete_confirm_desc", lang, task_name=row["task"]),
            color=0xED4245,
        )
        confirm_embed.set_footer(text=t("footer_text", lang))
        await interaction.response.send_message(
            embed=confirm_embed, view=view, ephemeral=True,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # /pin  /unpin
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name="pin", description="📌 ปักหมุด Task / Pin a task")
    @app_commands.describe(task_id="Task ID to pin")
    @app_commands.autocomplete(task_id=task_autocomplete)
    @rate_limit_check("command")
    async def pin(self, interaction: discord.Interaction, task_id: int) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        row  = await db.afetchone("SELECT owner_id, is_pinned, is_deleted FROM tasks WHERE task_id=$1", (task_id,))
        if not row or row["owner_id"] != uid:
            await interaction.response.send_message(
                t("task_not_found", lang, task_id=task_id), ephemeral=True
            )
            return
        if row.get("is_deleted"):
            await interaction.response.send_message(
                t("task_already_in_trash", lang, task_id=task_id), ephemeral=True
            )
            return
        await db.aexecute("UPDATE tasks SET is_pinned=1 WHERE task_id=$1 AND owner_id=$2 AND is_deleted=FALSE", (task_id, uid))
        await db.alog_action(uid, "task_pinned", str(task_id))
        db.invalidate_stats(uid)
        await interaction.response.send_message(
            t("task_pinned", lang, task_id=task_id), ephemeral=True
        )

    @app_commands.command(name="unpin", description="📌 เลิกปักหมุด Task / Unpin a task")
    @app_commands.describe(task_id="Task ID to unpin")
    @app_commands.autocomplete(task_id=task_autocomplete)
    @rate_limit_check("command")
    async def unpin(self, interaction: discord.Interaction, task_id: int) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        row  = await db.afetchone(
            "SELECT owner_id, is_pinned, is_deleted FROM tasks WHERE task_id=$1", (task_id,)
        )
        if not row or row["owner_id"] != uid:
            await interaction.response.send_message(
                t("task_not_found", lang, task_id=task_id), ephemeral=True
            )
            return
        if row.get("is_deleted"):
            await interaction.response.send_message(
                t("task_already_in_trash", lang, task_id=task_id), ephemeral=True
            )
            return
        await db.aexecute("UPDATE tasks SET is_pinned=0 WHERE task_id=$1 AND owner_id=$2 AND is_deleted=FALSE", (task_id, uid))
        await db.alog_action(uid, "task_unpinned", str(task_id))
        db.invalidate_stats(uid)
        await interaction.response.send_message(
            t("task_unpinned", lang, task_id=task_id), ephemeral=True
        )

    # ─────────────────────────────────────────────────────────────────────────
    # /recurring
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name="recurring", description="🔄 ตั้งการทำซ้ำ / Set task recurring")
    @app_commands.describe(
        task_id="Task ID",
        interval="Repeat rule",
        every="Interval for every_n_days or every_n_weeks",
        days_of_month="Comma-separated days for monthly_dates (e.g. 1,16)",
    )
    @app_commands.autocomplete(task_id=task_autocomplete)
    @app_commands.choices(interval=[
        app_commands.Choice(name="🔄 Daily / ทุกวัน",       value="daily"),
        app_commands.Choice(name="🔄 Weekly / ทุกสัปดาห์",  value="weekly"),
        app_commands.Choice(name="🔄 Monthly / ทุกเดือน",   value="monthly"),
        app_commands.Choice(name="📅 Weekdays / จันทร์–ศุกร์", value="weekdays"),
        app_commands.Choice(name="📆 Every N days", value="every_n_days"),
        app_commands.Choice(name="📆 Every N weeks", value="every_n_weeks"),
        app_commands.Choice(name="🗓️ Monthly dates (1,16)", value="monthly_dates"),
        app_commands.Choice(name="❌ None / ไม่ทำซ้ำ",       value="none"),
    ])
    @rate_limit_check("command")
    async def recurring(
        self,
        interaction: discord.Interaction,
        task_id: int,
        interval: str,
        every: Optional[int] = None,
        days_of_month: Optional[str] = None,
    ) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        row  = await db.afetchone("SELECT owner_id, deadline FROM tasks WHERE task_id=$1 AND is_deleted=FALSE", (task_id,))
        if not row or row["owner_id"] != uid:
            await interaction.response.send_message(
                t("task_not_found", lang, task_id=task_id), ephemeral=True
            )
            return
        if interval != "none" and row["deadline"] is None:
            await interaction.response.send_message(
                t("task_deadline_required_for_recurring", lang), ephemeral=True
            )
            return

        rule = None
        try:
            if interval == "weekdays":
                if every is not None or days_of_month:
                    raise ValueError("Advanced recurrence options do not apply to weekdays.")
                rule = validate_rule({"type": "weekdays"})
            elif interval in {"every_n_days", "every_n_weeks"}:
                if days_of_month:
                    raise ValueError("Month days do not apply to this interval.")
                if every is None:
                    raise ValueError("An interval is required.")
                rule = validate_rule({"type": interval, "interval": every})
            elif interval == "monthly_dates":
                if every is not None:
                    raise ValueError("An interval does not apply to monthly dates.")
                if not days_of_month:
                    raise ValueError("At least one month day is required.")
                days = [int(value.strip()) for value in days_of_month.split(",")]
                rule = validate_rule({"type": "monthly_dates", "days": days})
            elif every is not None or days_of_month:
                raise ValueError("Advanced recurrence options do not apply to this interval.")
        except ValueError:
            await interaction.response.send_message(
                t("recurrence_invalid", lang), ephemeral=True
            )
            return

        new_val: Optional[str] = interval if interval in {"daily", "weekly", "monthly"} else None
        encoded_rule = json.dumps(rule) if rule is not None else None
        await db.aexecute(
            """UPDATE tasks SET recurring=$1, recurrence_rule=$2::jsonb, updated_at=NOW()
               WHERE task_id=$3 AND owner_id=$4 AND is_deleted=FALSE""",
            (new_val, encoded_rule, task_id, uid),
        )
        await db.alog_action(uid, "task_recurring_set", str(task_id), interval)
        db.invalidate_stats(uid)
        if interval in {"every_n_days", "every_n_weeks"}:
            key = "recurring_every_days" if interval == "every_n_days" else "recurring_every_weeks"
            label = t(key, lang, count=every)
        elif interval == "monthly_dates" and rule is not None:
            label = t("recurring_monthly_dates", lang, dates=", ".join(map(str, rule["days"])))
        else:
            label = t(f"recurring_{interval}", lang) if interval != "none" else t("recurring_none", lang)
        await interaction.response.send_message(
            t("task_recurring_updated", lang, task_id=task_id, interval=label), ephemeral=True
        )


    # ─────────────────────────────────────────────────────────────────────────
    # /stats
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name="stats", description="📊 สถิติของคุณ / Your task statistics")
    @rate_limit_check("command")
    async def stats(self, interaction: discord.Interaction) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)

        stats = await db.user_task_stats(uid)
        avatar_url = interaction.user.display_avatar.url if interaction.user.display_avatar else None
        embed = build_stats_embed(stats, lang, interaction.user.display_name, avatar_url=avatar_url)
        await interaction.response.send_message(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # /export
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="export",
        description="📤 ส่งออก Task เป็น Interactive HTML หรือ CSV / Export tasks as Interactive HTML or CSV",
    )
    @app_commands.describe(format="รูปแบบไฟล์ที่ต้องการส่งออก / Export file format (html, csv)")
    @app_commands.choices(format=[
        app_commands.Choice(name="📄 Interactive HTML (Dashboard ออฟไลน์ ติ๊กถูกได้)", value="html"),
        app_commands.Choice(name="📊 CSV (Spreadsheet / Excel)", value="csv"),
    ])
    @rate_limit_check("export")
    async def export(
        self,
        interaction: discord.Interaction,
        format: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        uid     = str(interaction.user.id)
        lang    = await get_user_lang(uid)
        tz_name = await get_user_timezone(uid)

        tasks = await db.afetchall(
            "SELECT * FROM tasks WHERE owner_id=$1 AND is_deleted=FALSE ORDER BY created_at DESC", (uid,)
        )
        if not tasks:
            await interaction.response.send_message(t("export_empty", lang), ephemeral=True)
            return

        export_format = format.value if format else "html"

        if export_format == "csv":
            csv_bytes = build_csv_export(tasks, tz_name)
            fname = f"tasks_{uid}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
            await db.alog_action(uid, "task_exported", detail=f"{len(tasks)} tasks (csv)")
            await interaction.response.send_message(
                t("export_success", lang, filename=fname),
                file=discord.File(csv_bytes, filename=fname),
                ephemeral=True,
            )
        else:
            from history_reporting import service as history_service
            cats = await db.afetchall(
                "SELECT * FROM categories WHERE owner_id IN ($1, 'system')", (uid,)
            )
            html_bytes = history_service.build_html_export_bytes(
                tasks=tasks,
                categories=cats or [],
                user_id=uid,
                tz_name=tz_name,
                lang=lang,
            )
            fname = f"tasks_report_{uid}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.html"
            await db.alog_action(uid, "task_exported", detail=f"{len(tasks)} tasks (html)")
            await interaction.response.send_message(
                t("export_success_html", lang, filename=fname),
                file=discord.File(html_bytes, filename=fname),
                ephemeral=True,
            )

    # ───────────────────────────────────────────────────────────────────────────
    # /task-stats
    # ───────────────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="task-stats",
        description="📊 Productivity Dashboard — ดูสถิติประสิทธิภาพการทำงานของคุณ",
    )
    @rate_limit_check("command")
    async def task_stats(self, interaction: discord.Interaction) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer(thinking=True)

        data       = await db.get_user_productivity_analytics(uid)
        avatar_url = interaction.user.display_avatar.url if interaction.user.display_avatar else None
        username   = interaction.user.display_name

        embed = build_task_stats_embed(data, lang, username, avatar_url, view_mode="overview")
        view  = TaskStatsView(data, lang, username, avatar_url)
        await interaction.followup.send(embed=embed, view=view)
        await db.alog_action(uid, "task_stats_viewed")

    # ───────────────────────────────────────────────────────────────────────────
    # /digest
    # ───────────────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="digest",
        description="☀️ ดูสรุป Task วันนี้ทันที / View your today's task summary instantly",
    )
    @rate_limit_check("command")
    async def digest(self, interaction: discord.Interaction) -> None:
        """On-demand Daily Digest — shows what the scheduled digest would send."""
        from handlers.reminders_cog import _build_digest_embed, DailyDigestView
        import pytz as _pytz

        uid     = str(interaction.user.id)
        lang    = await get_user_lang(uid)
        tz_name = await get_user_timezone(uid)
        await ensure_user(uid, lang)
        await interaction.response.defer(thinking=True, ephemeral=True)

        _UTC = _pytz.utc
        now  = datetime.now(timezone.utc)
        try:
            local_tz  = _pytz.timezone(tz_name)
            local_now = now.astimezone(local_tz)
        except Exception:
            import pytz
            local_now = now.astimezone(pytz.utc)
            tz_name   = "UTC"

        try:
            embed = await _build_digest_embed(uid, lang, tz_name, local_now, now)
            view  = DailyDigestView(lang)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            await db.alog_action(uid, "digest_viewed_ondemand")
        except Exception as exc:
            log.error("On-demand digest error uid=%s: %s", uid, exc)
            await interaction.followup.send(
                t("err_with_detail", lang, detail=str(exc)),
                ephemeral=True,
            )


# ───────────────────────────────────────────────────────────────────────────
# TaskStatsView — interactive tab switcher for /task-stats
# ───────────────────────────────────────────────────────────────────────────

class TaskStatsView(discord.ui.View):
    """
    Interactive View for /task-stats:
      📊 Overview tab | ⏱️ Speed & Timeliness tab | 🔄 Refresh button
    """

    def __init__(
        self,
        data: dict,
        lang: str,
        username: str,
        avatar_url: Optional[str],
    ) -> None:
        super().__init__(timeout=300)
        self._data       = data
        self._lang       = lang
        self._username   = username
        self._avatar_url = avatar_url
        self._view_mode  = "overview"  # current active tab
        # Localize button labels at init so they start in the user's language
        self.btn_overview.label = t("btn_overview_tab", lang)
        self.btn_speed.label    = t("btn_speed_tab", lang)
        self.btn_refresh.label  = t("btn_stats_refresh", lang)

    @discord.ui.button(label="📊 Overview", style=discord.ButtonStyle.primary,
                       custom_id="stats_overview")
    async def btn_overview(self, interaction: discord.Interaction,
                           button: discord.ui.Button) -> None:
        button.label = t("btn_overview_tab", self._lang)
        self._view_mode = "overview"
        embed = build_task_stats_embed(
            self._data, self._lang, self._username,
            self._avatar_url, view_mode="overview",
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⏱️ Speed & Timeliness",
                       style=discord.ButtonStyle.secondary,
                       custom_id="stats_speed")
    async def btn_speed(self, interaction: discord.Interaction,
                        button: discord.ui.Button) -> None:
        button.label = t("btn_speed_tab", self._lang)
        self._view_mode = "speed"
        embed = build_task_stats_embed(
            self._data, self._lang, self._username,
            self._avatar_url, view_mode="speed",
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.secondary,
                       custom_id="stats_refresh")
    async def btn_refresh(self, interaction: discord.Interaction,
                          button: discord.ui.Button) -> None:
        uid = str(interaction.user.id)
        await interaction.response.defer(thinking=True, ephemeral=True)
        # Invalidate cache so we get fresh data
        db.stats_cache.invalidate(f"analytics:{uid}")
        fresh_data = await db.get_user_productivity_analytics(uid)
        self._data = fresh_data
        embed = build_task_stats_embed(
            fresh_data, self._lang, self._username,
            self._avatar_url, view_mode=self._view_mode,
        )
        # Edit original message with fresh embed + updated view
        await interaction.message.edit(embed=embed, view=self)
        await interaction.followup.send(
            t("stats_refreshed", self._lang), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TasksCog(bot))
