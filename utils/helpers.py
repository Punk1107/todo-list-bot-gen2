"""
utils/helpers.py — Shared utility functions v3 (System Upgrade)
Changes:
  - ALL user helpers are now async (eliminates blocking DB calls on event loop)
  - Redesigned premium embed builders with richer visual hierarchy
  - Enhanced urgency system with better color gradients
  - Improved progress bar renderer (fills with block characters)
  - Richer task list embed with proper sections and spacing
  - Subtask/category fetching in build_task_embed now async-safe
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
from datetime import datetime, timedelta
from typing import Optional

import discord
import pytz

from core.config import config
from locales.i18n import t

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Colour palette — one place to change everything
# ─────────────────────────────────────────────────────────────────────────────

_C_OVERDUE   = 0xED4245   # Discord red
_C_CRITICAL  = 0xE67E22   # orange    (< 3 h)
_C_WARNING   = 0xFEE75C   # yellow    (< 24 h) — Discord yellow
_C_UPCOMING  = 0x5865F2   # Discord blurple (< 72 h)
_C_FINE      = 0x57F287   # Discord green   (>= 72 h)
_C_COMPLETED = 0x95A5A6   # grey
_C_CANCELLED = 0x7F8C8D   # dark grey
_C_PINNED    = 0xFEE75C   # gold / yellow


# ─────────────────────────────────────────────────────────────────────────────
# Urgency helpers
# ─────────────────────────────────────────────────────────────────────────────

def urgency_color(deadline_str: str, status: str) -> int:
    """Return embed colour based on deadline proximity and task status."""
    if status == "Completed":
        return _C_COMPLETED
    if status == "Cancelled":
        return _C_CANCELLED
    try:
        dt = datetime.fromisoformat(deadline_str)
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        secs = (dt - datetime.now(pytz.utc)).total_seconds()
        if secs < 0:
            return _C_OVERDUE
        if secs < 10_800:     # 3 h
            return _C_CRITICAL
        if secs < 86_400:     # 24 h
            return _C_WARNING
        if secs < 259_200:    # 72 h
            return _C_UPCOMING
        return _C_FINE
    except Exception:
        return _C_UPCOMING


def urgency_badge(deadline_str: str, status: str) -> str:
    """Return a short urgency badge string for embed titles."""
    if status in ("Completed", "Cancelled"):
        return ""
    try:
        dt = datetime.fromisoformat(deadline_str)
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        secs = (dt - datetime.now(pytz.utc)).total_seconds()
        if secs < 0:
            return "🔴 OVERDUE"
        if secs < 10_800:
            return "🟠 CRITICAL"
        if secs < 86_400:
            return "🟡 DUE TODAY"
        if secs < 259_200:
            return "🔵 UPCOMING"
        return "🟢 ON TRACK"
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Progress bar
# ─────────────────────────────────────────────────────────────────────────────

def progress_bar(value: int, total: int, width: int = 12) -> str:
    """Render a Unicode block progress bar with percentage.
    E.g.  progress_bar(3, 5) → ████████░░░░ **60%**
    """
    if total == 0:
        return f"`{'░' * width}` **—**"
    pct = value / total
    filled = round(pct * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"`{bar}` **{pct * 100:.0f}%** ({value}/{total})"


# ─────────────────────────────────────────────────────────────────────────────
# User helpers — ALL ASYNC to never block the event loop
# ─────────────────────────────────────────────────────────────────────────────

async def _load_user_from_db_async(uid: str):
    """Async: fetch user row from DB and populate cache."""
    from core.database import db
    row = await db.afetchone(
        "SELECT lang, timezone, channel_id, role FROM users WHERE user_id=?", (uid,)
    )
    if row:
        db.user_cache.set(uid, row["lang"], row["timezone"], row["channel_id"], row["role"])
    return row


async def get_user_lang(user_id) -> str:
    """Async: return user's language preference (cache-first)."""
    from core.database import db
    uid = str(user_id)
    cached = db.user_cache.get(uid)
    if cached:
        return cached.lang
    row = await _load_user_from_db_async(uid)
    return row["lang"] if row else config.bot.default_lang


async def get_user_timezone(user_id) -> str:
    """Async: return user's timezone string (cache-first)."""
    from core.database import db
    uid = str(user_id)
    cached = db.user_cache.get(uid)
    if cached:
        return cached.timezone
    row = await _load_user_from_db_async(uid)
    return row["timezone"] if row else config.bot.default_timezone


async def get_user_channel(user_id) -> Optional[int]:
    """Async: return user's notification channel ID (cache-first)."""
    from core.database import db
    uid = str(user_id)
    cached = db.user_cache.get(uid)
    if cached:
        return cached.channel_id
    row = await _load_user_from_db_async(uid)
    return row["channel_id"] if row else None


async def get_user_role(user_id) -> str:
    """Async: return user's role (cache-first)."""
    from core.database import db
    uid = str(user_id)
    cached = db.user_cache.get(uid)
    if cached:
        return cached.role
    row = await _load_user_from_db_async(uid)
    return row["role"] if row else "user"


async def ensure_user(user_id, lang: Optional[str] = None) -> None:
    """Async: insert user row if not present (INSERT OR IGNORE)."""
    from core.database import db
    uid = str(user_id)
    await db.aexecute(
        "INSERT OR IGNORE INTO users (user_id, timezone, lang) VALUES (?,?,?)",
        (uid, config.bot.default_timezone, lang or config.bot.default_lang),
    )


async def save_user_settings(
    user_id,
    *,
    timezone: Optional[str] = None,
    channel_id: Optional[int] = None,
    lang: Optional[str] = None,
    notify_enabled: Optional[int] = None,
    daily_digest: Optional[int] = None,
) -> None:
    """Async: persist one or more user settings and invalidate cache."""
    from core.database import db
    uid = str(user_id)
    await ensure_user(uid)
    if timezone:
        await db.aexecute("UPDATE users SET timezone=? WHERE user_id=?", (timezone, uid))
    if channel_id is not None:
        await db.aexecute("UPDATE users SET channel_id=? WHERE user_id=?", (channel_id, uid))
    if lang:
        await db.aexecute("UPDATE users SET lang=? WHERE user_id=?", (lang, uid))
    if notify_enabled is not None:
        await db.aexecute("UPDATE users SET notify_enabled=? WHERE user_id=?", (notify_enabled, uid))
    if daily_digest is not None:
        await db.aexecute("UPDATE users SET daily_digest=? WHERE user_id=?", (daily_digest, uid))
    db.user_cache.invalidate(uid)


# ─────────────────────────────────────────────────────────────────────────────
# Date/time helpers
# ─────────────────────────────────────────────────────────────────────────────

_DATE_FORMATS = [
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y %H:%M",
    "%Y-%m-%d %H:%M",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
]


def parse_deadline(text: str, tz_name: str) -> Optional[datetime]:
    """Parse user text → UTC-aware datetime. Returns None on failure."""
    try:
        tz = pytz.timezone(tz_name)
    except pytz.exceptions.UnknownTimeZoneError:
        tz = pytz.utc

    for fmt in _DATE_FORMATS:
        try:
            naive = datetime.strptime(text.strip(), fmt)
            if "%H" not in fmt:
                naive = naive.replace(hour=23, minute=59)
            return tz.localize(naive).astimezone(pytz.utc)
        except ValueError:
            continue
    return None


def format_deadline(dt_str: str, tz_name: str) -> str:
    """Format stored UTC ISO → user's local timezone string."""
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        local = dt.astimezone(pytz.timezone(tz_name))
        return local.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return dt_str


def time_left_str(deadline_str: str) -> str:
    """Human-readable time remaining (or overdue) from a stored UTC ISO string."""
    try:
        dt = datetime.fromisoformat(deadline_str)
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        delta = dt - datetime.now(pytz.utc)
        if delta.total_seconds() < 0:
            elapsed = -delta
            d, rem = divmod(int(elapsed.total_seconds()), 86400)
            h, rem = divmod(rem, 3600)
            m = rem // 60
            if d:
                return f"-{d}d {h}h"
            if h:
                return f"-{h}h {m}m"
            return f"-{m}m"
        d, rem = divmod(int(delta.total_seconds()), 86400)
        h, rem = divmod(rem, 3600)
        m = rem // 60
        parts = []
        if d:
            parts.append(f"{d}d")
        if h:
            parts.append(f"{h}h")
        if m and not d:
            parts.append(f"{m}m")
        return " ".join(parts) or "< 1m"
    except Exception:
        return "?"


def calculate_next_deadline(deadline_str: str, recurring: str) -> Optional[str]:
    try:
        dt = datetime.fromisoformat(deadline_str)
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        if recurring == "daily":
            nxt = dt + timedelta(days=1)
        elif recurring == "weekly":
            nxt = dt + timedelta(weeks=1)
        elif recurring == "monthly":
            m = dt.month + 1
            y = dt.year
            if m > 12:
                m, y = 1, y + 1
            try:
                nxt = dt.replace(month=m, year=y)
            except ValueError:
                nxt = dt + timedelta(days=30)
        else:
            return None
        return nxt.isoformat()
    except Exception as exc:
        log.error("calculate_next_deadline: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Label helpers
# ─────────────────────────────────────────────────────────────────────────────

_PRIORITY_KEYS = {0: "priority_low", 1: "priority_medium", 2: "priority_high"}
_STATUS_KEYS = {
    "Pending":   "status_pending",
    "Completed": "status_completed",
    "Cancelled": "status_cancelled",
    "Overdue":   "status_overdue",
}
_RECURRING_KEYS = {
    "daily":   "recurring_daily",
    "weekly":  "recurring_weekly",
    "monthly": "recurring_monthly",
}


def _prio_label(priority: int, lang: str) -> str:
    return t(_PRIORITY_KEYS.get(priority, "priority_low"), lang)


def _status_label(status: str, lang: str) -> str:
    return t(_STATUS_KEYS.get(status, "status_pending"), lang)


def _recurring_label(recurring: Optional[str], lang: str) -> str:
    if not recurring:
        return t("recurring_none", lang)
    return t(_RECURRING_KEYS.get(recurring, "recurring_none"), lang)


# ─────────────────────────────────────────────────────────────────────────────
# Embed builders
# ─────────────────────────────────────────────────────────────────────────────

def build_task_embed(row, lang: str, tz_name: str,
                     subtasks=None, category=None) -> discord.Embed:
    """
    Build a premium, visually hierarchical embed for a single task.
    Accepts pre-fetched subtasks/category to avoid blocking DB calls.
    """
    task_id   = row["task_id"]
    status    = row["status"]
    deadline  = row["deadline"]
    priority  = row["priority"]
    is_pinned = bool(row["is_pinned"]) if "is_pinned" in row.keys() else False

    # Determine effective status for colouring
    try:
        dt = datetime.fromisoformat(deadline)
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        if dt < datetime.now(pytz.utc) and status == "Pending":
            status = "Overdue"
    except Exception:
        pass

    color    = urgency_color(deadline, status)
    badge    = urgency_badge(deadline, status)
    tl       = time_left_str(deadline)
    dl_fmt   = format_deadline(deadline, tz_name)

    # ── Title ────────────────────────────────────────────────────────────────
    pin_prefix   = "📌 " if is_pinned else ""
    badge_suffix = f"  {badge}" if badge else ""
    task_name    = row["task"]
    title_text   = f"{pin_prefix}#{task_id} — {task_name[:80]}{badge_suffix}"

    embed = discord.Embed(title=title_text, color=color)

    # ── Row 1: Status | Priority ─────────────────────────────────────────────
    embed.add_field(
        name=t("task_detail_status", lang),
        value=_status_label(status, lang),
        inline=True,
    )
    embed.add_field(
        name=t("task_detail_priority", lang),
        value=_prio_label(priority, lang),
        inline=True,
    )
    # Blank to force 2-column layout on row 1
    embed.add_field(name="\u200B", value="\u200B", inline=True)

    # ── Row 2: Deadline ──────────────────────────────────────────────────────
    embed.add_field(
        name=t("task_detail_deadline", lang),
        value=f"📅 `{dl_fmt}`\n⏱️ {tl}",
        inline=False,
    )

    # ── Description ─────────────────────────────────────────────────────────
    if row["description"]:
        desc_display = row["description"][:500]
        embed.add_field(
            name=t("task_detail_desc", lang),
            value=f"```{desc_display}```",
            inline=False,
        )

    # ── Tags ─────────────────────────────────────────────────────────────────
    if row["tags"]:
        tag_display = "  ".join(
            f"`{tag.strip()}`"
            for tag in row["tags"].split(",")
            if tag.strip()
        )
        embed.add_field(name=t("task_detail_tags", lang), value=tag_display, inline=True)

    # ── Recurring ────────────────────────────────────────────────────────────
    if row["recurring"]:
        embed.add_field(
            name=t("task_detail_recurring", lang),
            value=_recurring_label(row["recurring"], lang),
            inline=True,
        )

    # ── Subtask progress (pre-fetched) ───────────────────────────────────────
    if subtasks:
        total_sub = len(subtasks)
        done_sub  = sum(1 for s in subtasks if s["status"] == "Completed")
        bar = progress_bar(done_sub, total_sub)
        embed.add_field(
            name=t("task_detail_subtasks", lang),
            value=bar,
            inline=False,
        )

    # ── Category (pre-fetched) ───────────────────────────────────────────────
    if category:
        embed.add_field(
            name=t("task_detail_category", lang),
            value=f"{category['emoji']} {category['name']}",
            inline=True,
        )

    created = (row["created_at"] or "")[:16]
    embed.set_footer(text=f"🆔 #{task_id}  •  {t('footer_text', lang)}  •  🕐 {created}")
    return embed


def build_task_list_embed(
    tasks, page: int, total_pages: int,
    lang: str, tz_name: str, filter_label: str,
) -> discord.Embed:
    """Build a premium paginated task list embed with urgency indicators."""
    embed = discord.Embed(
        title=f"📋 {t('tasks_title', lang)}  ›  {filter_label}",
        color=0x5865F2,
    )

    if not tasks:
        embed.description = (
            f"\n> {t('tasks_empty', lang)}\n"
        )
    else:
        now = datetime.now(pytz.utc)
        lines: list[str] = []

        for row in tasks:
            tid  = row["task_id"]
            name = row["task"]
            name_disp = (name[:48] + "…") if len(name) > 48 else name

            try:
                dt = datetime.fromisoformat(row["deadline"])
                if dt.tzinfo is None:
                    dt = pytz.utc.localize(dt)
                is_overdue = dt < now and row["status"] == "Pending"
            except Exception:
                is_overdue = False

            prio_icon   = ["🟢", "🟡", "🔴"][row["priority"]]
            if is_overdue:
                status_icon = "🚨"
            elif row["status"] == "Completed":
                status_icon = "✅"
            elif row["status"] == "Cancelled":
                status_icon = "❌"
            else:
                status_icon = "⏳"

            pin_icon = " 📌" if row.get("is_pinned") else ""
            dl_str   = format_deadline(row["deadline"], tz_name)
            tl       = time_left_str(row["deadline"])

            lines.append(
                f"{status_icon}{prio_icon}{pin_icon} **#{tid}** {name_disp}\n"
                f"   ╰ 📅 `{dl_str}`  ·  ⏱️ `{tl}`"
            )

        embed.description = "\n".join(lines)

    page_str = f"📄 {page} / {total_pages}"
    embed.set_footer(text=f"{page_str}  ·  {t('footer_text', lang)}")
    return embed


def build_stats_embed(stats: dict[str, int], lang: str, username: str) -> discord.Embed:
    """Build a premium stats embed with progress bar and breakdown."""
    total     = stats.get("total", 0)
    done      = stats.get("completed", 0)
    pending   = stats.get("pending", 0)
    overdue   = stats.get("overdue", 0)
    pinned    = stats.get("pinned", 0)
    cancelled = stats.get("cancelled", 0)

    if total == 0:
        color = _C_COMPLETED
    elif overdue > 0:
        color = _C_CRITICAL
    elif done == total:
        color = _C_FINE
    else:
        color = _C_UPCOMING

    embed = discord.Embed(
        title=f"📊 {t('stats_title', lang)}  ·  {username}",
        color=color,
    )

    # Completion progress bar
    bar = progress_bar(done, total)
    embed.add_field(
        name=t("stats_completion_rate", lang),
        value=bar,
        inline=False,
    )

    # 3-column breakdown
    embed.add_field(name=f"📝 {t('stats_total', lang)}",     value=f"**{total}**",     inline=True)
    embed.add_field(name=f"✅ {t('stats_completed', lang)}", value=f"**{done}**",      inline=True)
    embed.add_field(name=f"⏳ {t('stats_pending', lang)}",   value=f"**{pending}**",   inline=True)
    embed.add_field(name=f"🚨 {t('stats_overdue', lang)}",   value=f"**{overdue}**",   inline=True)
    embed.add_field(name="📌 Pinned",                        value=f"**{pinned}**",    inline=True)
    embed.add_field(name="❌ Cancelled",                      value=f"**{cancelled}**", inline=True)

    # Motivational note
    if total == 0:
        note = "ยังไม่มี Task เลย! ใช้ `/add` เพื่อเริ่มต้น 🚀" if lang == "th" else "No tasks yet! Use `/add` to get started 🚀"
    elif overdue > 0:
        note = f"⚠️ มี {overdue} Task เกินกำหนด ใช้ `/overdue` ตรวจสอบ" if lang == "th" else f"⚠️ {overdue} task(s) overdue — use `/overdue` to review"
    elif done == total and total > 0:
        note = "🏆 เสร็จทุก Task แล้ว! ยอดเยี่ยมมาก!" if lang == "th" else "🏆 All tasks completed! Outstanding work!"
    else:
        pct = int(done / total * 100) if total else 0
        note = f"ทำเสร็จไปแล้ว {pct}% เยี่ยมมาก!" if lang == "th" else f"You're {pct}% done — keep it up!"
    embed.add_field(name="\u200B", value=f"> {note}", inline=False)

    embed.set_footer(text=t("footer_text", lang))
    return embed


# ─────────────────────────────────────────────────────────────────────────────
# CSV export
# ─────────────────────────────────────────────────────────────────────────────

def build_csv_export(tasks, tz_name: str) -> io.BytesIO:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([
        "ID", "Task", "Status", "Priority", "Deadline", "Recurring",
        "Category", "Tags", "Description", "Pinned", "Created",
    ])
    for row in tasks:
        w.writerow([
            row["task_id"], row["task"], row["status"], row["priority"],
            format_deadline(row["deadline"], tz_name),
            row["recurring"] or "",
            row["category_id"] or "",
            row["tags"] or "",
            (row["description"] or "").replace("\n", " "),
            bool(row["is_pinned"]) if "is_pinned" in row.keys() else False,
            row["created_at"] or "",
        ])
    return io.BytesIO(out.getvalue().encode("utf-8-sig"))  # BOM for Excel
