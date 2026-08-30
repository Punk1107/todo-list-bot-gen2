"""
handlers/tasks_cog.py — Slash commands for task management v4 (PostgreSQL)
Changes over v3:
  - SQL placeholders: ? → $N (PostgreSQL/asyncpg)
  - CURRENT_TIMESTAMP → NOW()
  - _async_build_task_embed: uses $1, $2 placeholders
"""
from __future__ import annotations

import logging
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
    format_deadline, time_left_str,
)
from handlers.task_views import (
    AddTaskModal, TaskActionView, TaskListView, DeleteConfirmView,
    PrioritySelectView,
    TASKS_PER_PAGE, _send_dm,
)

log = logging.getLogger(__name__)


async def _async_build_task_embed(row, lang: str, tz_name: str) -> discord.Embed:
    """Async wrapper: fetches subtasks + category then builds the embed."""
    task_id = row["task_id"]

    # Fetch subtasks (non-cancelled only)
    subtasks = await db.afetchall(
        "SELECT status FROM tasks WHERE parent_task_id=$1 AND status != 'Cancelled'",
        (task_id,),
    )

    # Fetch category
    category = None
    if row["category_id"]:
        category = await db.afetchone(
            "SELECT name, emoji FROM categories WHERE category_id=$1",
            (row["category_id"],),
        )

    return build_task_embed(row, lang, tz_name,
                            subtasks=subtasks or None,
                            category=category)


class TasksCog(commands.Cog, name="Tasks"):
    """All task-related slash commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ─────────────────────────────────────────────────────────────────────────
    # /add
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name="add", description="➕ เพิ่ม Task ใหม่ / Add a new task")
    @rate_limit_check("command")
    async def add(self, interaction: discord.Interaction) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)

        # Step 1: priority dropdown — opens AddTaskModal after selection
        view  = PrioritySelectView(uid, lang)
        embed = PrioritySelectView.build_embed(lang)
        # Send a public message (so everyone sees 'User used /add')
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
        # Store message in view so it can edit out the dropdown on timeout (optional, see on_timeout)
        view.message = await interaction.original_response()

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

        view             = TaskListView(uid, lang, tz_name, "Pending")
        tasks, page, tot = await view._fetch_page()
        filter_label     = t("tasks_filter_Pending", lang)

        # Count total and overdue for summary line
        now_iso = datetime.now(pytz.utc).isoformat()
        total_row = await db.afetchone(
            "SELECT COUNT(*) AS c FROM tasks WHERE owner_id=$1 AND parent_task_id IS NULL", (uid,)
        )
        overdue_row = await db.afetchone(
            "SELECT COUNT(*) AS c FROM tasks WHERE owner_id=$1 AND parent_task_id IS NULL "
            "AND status='Pending' AND deadline<$2", (uid, now_iso)
        )
        total_count   = total_row["c"]   if total_row   else 0
        overdue_count = overdue_row["c"] if overdue_row else 0

        embed = build_task_list_embed(
            tasks, page, tot, lang, tz_name, filter_label,
            total_count=total_count, overdue_count=overdue_count,
        )
        view._update_nav_buttons(page, tot)
        await interaction.response.send_message(embed=embed, view=view)
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

        # Compute today's boundaries in the user's local timezone, then convert to UTC
        now_utc   = datetime.now(pytz.utc)
        local_tz  = pytz.timezone(tz_name)
        local_now = now_utc.astimezone(local_tz)
        start = local_now.replace(hour=0,  minute=0,  second=0,  microsecond=0).astimezone(pytz.utc).isoformat()
        end   = local_now.replace(hour=23, minute=59, second=59, microsecond=0).astimezone(pytz.utc).isoformat()

        tasks = await db.afetchall(
            """SELECT * FROM tasks
               WHERE owner_id=$1 AND status='Pending'
                 AND deadline BETWEEN $2 AND $3
               ORDER BY deadline ASC""",
            (uid, start, end),
        )

        overdue_row = await db.afetchone(
            "SELECT COUNT(*) AS c FROM tasks WHERE owner_id=$1 AND status='Pending' AND deadline<$2",
            (uid, now_utc.isoformat()),
        )
        overdue_c = overdue_row["c"] if overdue_row else 0

        # Dynamic color based on urgency
        if overdue_c > 0:
            today_color = 0xED4245
        elif any(r["priority"] >= 4 for r in tasks):
            today_color = 0xE67E22
        else:
            today_color = 0x5865F2

        local_date = local_now.strftime("%d/%m/%Y")
        embed = discord.Embed(
            title=f"📅 {t('tasks_filter_today', lang)} — {local_date}",
            color=today_color,
        )
        if not tasks:
            embed.description = "> " + t("tasks_empty", lang)
        else:
            lines = [f"**{t('today_summary', lang, count=len(tasks), overdue=overdue_c)}**\n"]
            for r in tasks:
                try:
                    dt = datetime.fromisoformat(r["deadline"])
                    if dt.tzinfo is None:
                        dt = pytz.utc.localize(dt)
                    is_overdue = dt < now_utc
                except Exception:
                    is_overdue = False
                icon = "🚨" if is_overdue else "⏳"
                tl = time_left_str(r["deadline"])
                dl_fmt = format_deadline(r["deadline"], tz_name)
                lines.append(
                    f"{icon} `#{r['task_id']}` **{r['task'][:50]}**\n"
                    f"   ╰ 📅 `{dl_fmt}`  ·  ⏱️ `{tl}`"
                )
            embed.description = "\n".join(lines)
            embed.set_footer(text=f"{len(tasks)} task(s) today  |  {t('footer_text', lang)}")
        await interaction.followup.send(embed=embed)

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

        now   = datetime.now(pytz.utc).isoformat()
        tasks = await db.afetchall(
            """SELECT * FROM tasks
               WHERE owner_id=$1 AND status='Pending' AND deadline<$2
               ORDER BY deadline ASC""",
            (uid, now),
        )

        embed = discord.Embed(title=f"🚨 {t('tasks_filter_overdue', lang)}", color=0xED4245)
        if not tasks:
            embed.description = "> ✅ " + t("overdue_none", lang)
        else:
            summary_line = t("overdue_summary", lang, total=len(tasks))
            note_line = t("overdue_note", lang)
            lines = [f"**{summary_line}**\n> *{note_line}*\n"]
            for r in tasks:
                lines.append(
                    f"🚨 `#{r['task_id']}` **{r['task'][:50]}**\n"
                    f"   ╰─ 📅 `{format_deadline(r['deadline'], tz_name)}`  (⏱️ `{time_left_str(r['deadline'])}`)"
                )
            embed.description = "\n".join(lines)
            embed.set_footer(text=f"⚠️ {len(tasks)} overdue  |  {t('footer_text', lang)}")
        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # /task — detail view by ID
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name="task", description="📌 ดู Task ตาม ID / View task by ID")
    @app_commands.describe(task_id="Task ID number")
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
    @app_commands.describe(task_id="Task ID number")
    @rate_limit_check("command")
    async def done(self, interaction: discord.Interaction, task_id: int) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await interaction.response.defer(ephemeral=True)

        row = await db.afetchone("SELECT task, status, owner_id FROM tasks WHERE task_id=$1", (task_id,))
        if not row:
            await interaction.followup.send(
                t("task_not_found", lang, task_id=task_id), ephemeral=True
            )
            return
        if row["owner_id"] != uid:
            await interaction.followup.send(t("task_not_owned", lang), ephemeral=True)
            return
        if row["status"] == "Completed":
            await interaction.followup.send(t("task_already_done", lang), ephemeral=True)
            return
        if row["status"] == "Cancelled":
            await interaction.followup.send(t("task_already_cancelled", lang), ephemeral=True)
            return

        await db.aexecute(
            "UPDATE tasks SET status='Completed', updated_at=NOW() WHERE task_id=$1 AND owner_id=$2",
            (task_id, uid),
        )
        await db.alog_action(uid, "task_completed", str(task_id))
        db.invalidate_stats(uid)

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
    @rate_limit_check("command")
    async def delete(self, interaction: discord.Interaction, task_id: int) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        # Fetch task name BEFORE responding (send_message with view must be first response)
        row = await db.afetchone("SELECT task, owner_id FROM tasks WHERE task_id=$1", (task_id,))
        if not row:
            await interaction.response.send_message(
                t("task_not_found", lang, task_id=task_id), ephemeral=True
            )
            return
        if row["owner_id"] != uid:
            await interaction.response.send_message(t("task_not_owned", lang), ephemeral=True)
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
    @rate_limit_check("command")
    async def pin(self, interaction: discord.Interaction, task_id: int) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        row  = await db.afetchone("SELECT owner_id, is_pinned FROM tasks WHERE task_id=$1", (task_id,))
        if not row or row["owner_id"] != uid:
            await interaction.response.send_message(
                t("task_not_found", lang, task_id=task_id), ephemeral=True
            )
            return
        await db.aexecute("UPDATE tasks SET is_pinned=1 WHERE task_id=$1", (task_id,))
        await db.alog_action(uid, "task_pinned", str(task_id))
        await interaction.response.send_message(
            t("task_pinned", lang, task_id=task_id), ephemeral=True
        )

    @app_commands.command(name="unpin", description="📌 เลิกปักหมุด Task / Unpin a task")
    @app_commands.describe(task_id="Task ID to unpin")
    @rate_limit_check("command")
    async def unpin(self, interaction: discord.Interaction, task_id: int) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        row  = await db.afetchone("SELECT owner_id FROM tasks WHERE task_id=$1", (task_id,))
        if not row or row["owner_id"] != uid:
            await interaction.response.send_message(
                t("task_not_found", lang, task_id=task_id), ephemeral=True
            )
            return
        await db.aexecute("UPDATE tasks SET is_pinned=0 WHERE task_id=$1", (task_id,))
        await db.alog_action(uid, "task_unpinned", str(task_id))
        await interaction.response.send_message(
            t("task_unpinned", lang, task_id=task_id), ephemeral=True
        )

    # ─────────────────────────────────────────────────────────────────────────
    # /recurring
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name="recurring", description="🔄 ตั้งการทำซ้ำ / Set task recurring")
    @app_commands.describe(task_id="Task ID", interval="daily / weekly / monthly / none")
    @app_commands.choices(interval=[
        app_commands.Choice(name="🔄 Daily / ทุกวัน",       value="daily"),
        app_commands.Choice(name="🔄 Weekly / ทุกสัปดาห์",  value="weekly"),
        app_commands.Choice(name="🔄 Monthly / ทุกเดือน",   value="monthly"),
        app_commands.Choice(name="❌ None / ไม่ทำซ้ำ",       value="none"),
    ])
    @rate_limit_check("command")
    async def recurring(
        self, interaction: discord.Interaction, task_id: int, interval: str
    ) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        row  = await db.afetchone("SELECT owner_id FROM tasks WHERE task_id=$1", (task_id,))
        if not row or row["owner_id"] != uid:
            await interaction.response.send_message(
                t("task_not_found", lang, task_id=task_id), ephemeral=True
            )
            return

        new_val: Optional[str] = None if interval == "none" else interval
        await db.aexecute(
            "UPDATE tasks SET recurring=$1, updated_at=NOW() WHERE task_id=$2",
            (new_val, task_id),
        )
        await db.alog_action(uid, "task_recurring_set", str(task_id), interval)
        label = t(f"recurring_{interval}", lang) if interval != "none" else t("recurring_none", lang)
        await interaction.response.send_message(
            f"🔄 Task **#{task_id}** → {label}", ephemeral=True
        )

    # ─────────────────────────────────────────────────────────────────────────
    # /search  (BUG FIX: COALESCE prevents NULL from matching)
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.command(name="search", description="🔍 ค้นหา Task / Search tasks")
    @app_commands.describe(query="Search keyword / คำค้นหา")
    @rate_limit_check("search")
    async def search(self, interaction: discord.Interaction, query: str) -> None:
        uid     = str(interaction.user.id)
        lang    = await get_user_lang(uid)
        tz_name = await get_user_timezone(uid)

        q = validator.sanitize(query, 100)
        if validator.is_suspicious(q):
            await interaction.response.send_message(t("err_suspicious", lang), ephemeral=True)
            return
        await interaction.response.defer()

        # FIX: COALESCE ensures NULL columns don't prevent matches
        tasks = await db.afetchall(
            """SELECT * FROM tasks
               WHERE owner_id=$1
                 AND (task LIKE $2
                      OR COALESCE(tags, '') LIKE $2
                      OR COALESCE(description, '') LIKE $2)
               ORDER BY is_pinned DESC, priority DESC, deadline ASC LIMIT 20""",
            (uid, f"%{q}%"),
        )

        title_text = f"🔍 {t('search_title', lang, query=q)}"
        if tasks:
            title_text += f" — {len(tasks)} {t('cat_task_count', lang, count=len(tasks))}"
        embed = discord.Embed(title=title_text, color=0x5865F2)
        if not tasks:
            embed.description = "> " + t("search_empty", lang, query=q)
        else:
            now   = datetime.now(pytz.utc)
            lines = [f"> *{t('search_results_count', lang, query=q, count=len(tasks))}*\n"]
            escaped_q = re.escape(q)
            for row in tasks:
                try:
                    dt = datetime.fromisoformat(row["deadline"])
                    if dt.tzinfo is None:
                        dt = pytz.utc.localize(dt)
                    is_overdue = dt < now and row["status"] == "Pending"
                    is_done    = row["status"] == "Completed"
                except Exception:
                    is_overdue = False
                    is_done    = False

                if is_overdue:
                    icon = "🚨"
                elif is_done:
                    icon = "✅"
                else:
                    icon = "⏳"

                pin  = " 📌" if row.get("is_pinned") else ""
                name = row["task"][:60]
                highlighted_name = re.sub(
                    f"({escaped_q})", r"__**\1**__", name, flags=re.IGNORECASE
                )
                dl_fmt = format_deadline(row["deadline"], tz_name)
                tl     = time_left_str(row["deadline"])
                lines.append(
                    f"{icon} `#{row['task_id']}`{pin} {highlighted_name}\n"
                    f"   ╰ 📅 `{dl_fmt}`  ·  ⏱️ `{tl}`"
                )
            embed.description = "\n".join(lines)
        embed.set_footer(text=t("footer_text", lang))
        await interaction.followup.send(embed=embed)

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

    @app_commands.command(name="export", description="📤 ส่งออก Task เป็น CSV / Export tasks as CSV")
    @rate_limit_check("export")
    async def export(self, interaction: discord.Interaction) -> None:
        uid     = str(interaction.user.id)
        lang    = await get_user_lang(uid)
        tz_name = await get_user_timezone(uid)

        tasks = await db.afetchall(
            "SELECT * FROM tasks WHERE owner_id=$1 ORDER BY created_at DESC", (uid,)
        )
        if not tasks:
            await interaction.response.send_message(t("export_empty", lang), ephemeral=True)
            return

        csv_bytes = build_csv_export(tasks, tz_name)
        fname = f"tasks_{uid}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
        await db.alog_action(uid, "task_exported", detail=f"{len(tasks)} tasks")
        await interaction.response.send_message(
            t("export_success", lang, filename=fname),
            file=discord.File(csv_bytes, filename=fname),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TasksCog(bot))
