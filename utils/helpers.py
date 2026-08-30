"""
utils/helpers.py — Shared utility functions v4 (PostgreSQL)
Changes over v3:
  - SQL placeholders: ? → $N (PostgreSQL/asyncpg)
  - ensure_user: INSERT OR IGNORE → INSERT ... ON CONFLICT DO NOTHING
  - save_user_settings: 4 separate UPDATEs → 1 dynamic single UPDATE query
  - _load_user_from_db_async: uses $1 placeholder
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

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

def urgency_color(deadline_val: Any, status: str) -> int:
    """Return embed colour based on deadline proximity and task status."""
    if status == "Completed":
        return _C_COMPLETED
    if status == "Cancelled":
        return _C_CANCELLED
    # "Overdue" is a derived status set in build_task_embed — treat same as past deadline
    if status == "Overdue":
        return _C_OVERDUE
    try:
        if isinstance(deadline_val, datetime):
            dt = deadline_val
        elif isinstance(deadline_val, str):
            dt = datetime.fromisoformat(deadline_val)
        else:
            return _C_UPCOMING
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


def urgency_badge(deadline_val: Any, status: str) -> str:
    """Return a short urgency badge string for embed titles."""
    if status in ("Completed", "Cancelled"):
        return ""
    if status == "Overdue":
        return "🔴 OVERDUE"
    try:
        if isinstance(deadline_val, datetime):
            dt = deadline_val
        elif isinstance(deadline_val, str):
            dt = datetime.fromisoformat(deadline_val)
        else:
            return ""
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
    """Build a modern progress bar string with percentage and counts."""
    if total <= 0:
        return f"`{'▱' * width}` **0%** (0/0)"
    pct = min(max(value / total, 0.0), 1.0)
    filled = int(round(pct * width))
    bar = "▰" * filled + "▱" * (width - filled)
    return f"`{bar}` **{pct * 100:.0f}%** ({value}/{total})"


def urgency_bar(deadline_val: Any) -> str:
    """Return a short horizontal bar showing time urgency as colored square indicators.
    Returns an empty string if deadline cannot be parsed.
    """
    try:
        if isinstance(deadline_val, datetime):
            dt = deadline_val
        elif isinstance(deadline_val, str):
            dt = datetime.fromisoformat(deadline_val)
        else:
            return ""
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        secs = (dt - datetime.now(pytz.utc)).total_seconds()
        if secs < 0:
            return "🟥🟥🟥🟥🟥"   # overdue
        if secs < 3_600:            # < 1h
            return "🟥🟥🟥🟥⬜"
        if secs < 10_800:           # < 3h
            return "🟧🟧🟧⬜⬜"
        if secs < 86_400:           # < 24h
            return "🟨🟨🟨⬜⬜"
        if secs < 172_800:          # < 48h
            return "🟦🟦🟦🟦⬜"
        return "🟩🟩🟩🟩🟩"         # plenty of time
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# User helpers — ALL ASYNC to never block the event loop
# ─────────────────────────────────────────────────────────────────────────────

async def _load_user_from_db_async(uid: str):
    """Async: fetch user row from DB and populate cache."""
    from core.database import db
    row = await db.afetchone(
        "SELECT lang, timezone, channel_id, role FROM users WHERE user_id=$1", (uid,)
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


async def ensure_user(user_id, lang: Optional[str] = None,
                      discord_locale: Optional[str] = None) -> None:
    """Async: insert user row if not present (PostgreSQL ON CONFLICT DO NOTHING).

    Initial language priority for new users:
      1. explicit ``lang`` argument (e.g. from /setup)
      2. ``discord_locale`` mapped via DISCORD_LOCALE_MAP
      3. config.bot.default_lang
    Existing users are never updated by this function — use save_user_settings().
    """
    from core.database import db
    from locales.i18n import locale_to_lang
    uid = str(user_id)
    if lang is None and discord_locale is not None:
        lang = locale_to_lang(discord_locale)
    await db.aexecute(
        "INSERT INTO users (user_id, timezone, lang) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
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
    """Async: persist one or more user settings and invalidate cache.
    Builds a single UPDATE query dynamically — avoids multiple round-trips.
    """
    from core.database import db
    uid = str(user_id)
    await ensure_user(uid)

    # Build dynamic SET clause — only update provided fields
    sets: list[str] = []
    values: list = []
    idx = 1

    if timezone is not None:
        sets.append(f"timezone=${idx}"); values.append(timezone); idx += 1
    if channel_id is not None:
        sets.append(f"channel_id=${idx}"); values.append(channel_id); idx += 1
    if lang is not None:
        sets.append(f"lang=${idx}"); values.append(lang); idx += 1
    if notify_enabled is not None:
        sets.append(f"notify_enabled=${idx}"); values.append(notify_enabled); idx += 1
    if daily_digest is not None:
        sets.append(f"daily_digest=${idx}"); values.append(daily_digest); idx += 1

    if sets:
        values.append(uid)
        await db.aexecute(
            f"UPDATE users SET {', '.join(sets)} WHERE user_id=${idx}",
            tuple(values),
        )

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


def format_deadline(dt_val: Any, tz_name: str) -> str:
    """Format stored UTC ISO or datetime → user's local timezone string."""
    try:
        if isinstance(dt_val, datetime):
            dt = dt_val
        elif isinstance(dt_val, str):
            dt = datetime.fromisoformat(dt_val)
        else:
            return str(dt_val or "")
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        local = dt.astimezone(pytz.timezone(tz_name))
        return local.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(dt_val or "")


def time_left_str(deadline_val: Any) -> str:
    """Human-readable time remaining (or overdue) from a stored UTC ISO string or datetime."""
    try:
        if isinstance(deadline_val, datetime):
            dt = deadline_val
        elif isinstance(deadline_val, str):
            dt = datetime.fromisoformat(deadline_val)
        else:
            return "?"
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


def calculate_next_deadline(deadline_val: Any, recurring: str) -> Optional[str]:
    try:
        if isinstance(deadline_val, datetime):
            dt = deadline_val
        elif isinstance(deadline_val, str):
            dt = datetime.fromisoformat(deadline_val)
        else:
            return None
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

_PRIORITY_KEYS = {
    0: "priority_0",
    1: "priority_1",
    2: "priority_2",
    3: "priority_3",
    4: "priority_4",
    5: "priority_5",
    6: "priority_6",
    7: "priority_7",
}
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
    return t(_PRIORITY_KEYS.get(priority, "priority_0"), lang)


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
    is_pinned = bool(row["is_pinned"]) if hasattr(row, "keys") and "is_pinned" in row.keys() else False

    # Determine effective status for colouring
    try:
        if isinstance(deadline, datetime):
            dt = deadline
        else:
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
    ubar     = urgency_bar(deadline) if status not in ("Completed", "Cancelled") else ""

    # ── Title ──────────────────────────────────────────────────────────────────────
    pin_prefix   = "📌 " if is_pinned else ""
    badge_suffix = f"  {badge}" if badge else ""
    task_name    = row["task"]
    title_text   = f"{pin_prefix}#{task_id} — {task_name[:80]}{badge_suffix}"

    embed = discord.Embed(title=title_text, color=color)
    embed.timestamp = datetime.now(pytz.utc)  # live timestamp shown in footer

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

    # ── Row 2: Deadline with urgency bar ───────────────────────────────────────────
    dl_value = f"📅 `{dl_fmt}`\n⏱️ {tl}"
    if ubar:
        dl_value += f"\n{ubar}"
    embed.add_field(
        name=t("task_detail_deadline", lang),
        value=dl_value,
        inline=False,
    )

    # ── Description ──────────────────────────────────────────────────────────────────
    if row["description"]:
        desc_display = row["description"][:500]
        # Use blockquote for better readability instead of codeblock
        desc_lines = "\n".join(f"> {line}" for line in desc_display.splitlines()) or f"> {desc_display}"
        embed.add_field(
            name=t("task_detail_desc", lang),
            value=desc_lines,
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

    # ── Subtask progress (pre-fetched) ──────────────────────────────────────────────
    if subtasks:
        total_sub = len(subtasks)
        done_sub  = sum(1 for s in subtasks if s["status"] == "Completed")
        bar = progress_bar(done_sub, total_sub)
        embed.add_field(
            name=t("task_detail_subtasks", lang),
            value=f"✅ {done_sub}/{total_sub}  {bar}",
            inline=False,
        )

    # ── Category (pre-fetched) ───────────────────────────────────────────────
    if category:
        embed.add_field(
            name=t("task_detail_category", lang),
            value=f"{category['emoji']} {category['name']}",
            inline=True,
        )

    def _fmt_ts(val) -> str:
        if not val:
            return ""
        if isinstance(val, datetime):
            dt = val if val.tzinfo else pytz.utc.localize(val)
            try:
                user_tz = pytz.timezone(tz_name)
                return dt.astimezone(user_tz).strftime("%d/%m/%Y %H:%M")
            except Exception:
                return dt.strftime("%d/%m/%Y %H:%M")
        elif isinstance(val, str):
            try:
                dt = datetime.fromisoformat(val)
                if dt.tzinfo is None:
                    dt = pytz.utc.localize(dt)
                user_tz = pytz.timezone(tz_name)
                return dt.astimezone(user_tz).strftime("%d/%m/%Y %H:%M")
            except Exception:
                return val[:16]
        return ""

    created_raw = row.get("created_at") if hasattr(row, "get") else (row["created_at"] if "created_at" in row else None)
    updated_raw = row.get("updated_at") if hasattr(row, "get") else (row["updated_at"] if "updated_at" in row else None)

    created = _fmt_ts(created_raw)
    updated = _fmt_ts(updated_raw)

    footer_parts = [f"🆔 #{task_id}"]
    if created:
        footer_parts.append(f"🕐 {t('task_detail_created', lang)}: {created} ({tz_name})")
    if updated and updated != created:
        footer_parts.append(f"✏️ {t('task_detail_updated', lang)}: {updated}")
    footer_parts.append(t("footer_text", lang))

    embed.set_footer(text="  •  ".join(footer_parts))
    return embed


def build_task_list_embed(
    tasks, page: int, total_pages: int,
    lang: str, tz_name: str, filter_label: str,
    total_count: int = 0, overdue_count: int = 0,
) -> discord.Embed:
    """Build a premium paginated task list embed with urgency indicators.

    Dynamic embed colour: reflects the most urgent pending task in the list.
    Adds a summary line showing total tasks and overdue count.
    """
    # Compute dynamic colour from worst urgency in current page
    now = datetime.now(pytz.utc)
    worst_color = 0x5865F2  # default blurple
    if tasks:
        for row in tasks:
            if row["status"] not in ("Pending", "Overdue"):
                continue
            c = urgency_color(row["deadline"], row["status"])
            # Priority: red > orange > yellow > blurple > green
            color_priority = {_C_OVERDUE: 5, _C_CRITICAL: 4, _C_WARNING: 3,
                              _C_UPCOMING: 2, _C_FINE: 1}.get(c, 0)
            worst_priority = {_C_OVERDUE: 5, _C_CRITICAL: 4, _C_WARNING: 3,
                              _C_UPCOMING: 2, _C_FINE: 1}.get(worst_color, 0)
            if color_priority > worst_priority:
                worst_color = c

    embed = discord.Embed(
        title=f"📋 {t('tasks_title', lang)}  ›  {filter_label}",
        color=worst_color,
    )

    if not tasks:
        embed.description = (
            f"\n> {t('tasks_empty', lang)}\n"
        )
    else:
        lines: list[str] = []

        # Summary line at top
        if total_count > 0:
            summary = t("tasks_summary", lang, total=total_count, overdue=overdue_count)
            lines.append(f"――― {summary} ―――")

        for row in tasks:
            tid  = row["task_id"]
            name = row["task"]
            name_disp = (name[:48] + "…") if len(name) > 48 else name

            try:
                dl_val = row["deadline"]
                if isinstance(dl_val, datetime):
                    dt = dl_val
                else:
                    dt = datetime.fromisoformat(dl_val)
                if dt.tzinfo is None:
                    dt = pytz.utc.localize(dt)
                is_overdue = dt < now and row["status"] == "Pending"
            except Exception:
                is_overdue = False

            _PRIO_ICONS = ["⬜", "🟦", "🟩", "🟨", "🟧", "🟥", "🔴", "🆘"]
            prio_icon = _PRIO_ICONS[min(row["priority"], 7)]
            if is_overdue:
                status_icon = "🚨"
            elif row["status"] == "Completed":
                status_icon = "✅"
            elif row["status"] == "Cancelled":
                status_icon = "❌"
            else:
                status_icon = "⏳"

            pin_icon = " 📌" if (row.get("is_pinned") if hasattr(row, "get") else False) else ""
            dl_str   = format_deadline(row["deadline"], tz_name)
            tl       = time_left_str(row["deadline"])

            lines.append(
                f"{status_icon}{prio_icon}{pin_icon} **#{tid}** {name_disp}\n"
                f"   ╰ 📅 `{dl_str}`  ·  ⏱️ `{tl}`"
            )

        embed.description = "\n\n".join(lines)

    page_str = f"📄 {page} / {total_pages}"
    embed.set_footer(text=f"{page_str}  ·  {t('footer_text', lang)}")
    return embed


def build_stats_embed(stats: dict[str, int], lang: str, username: str,
                      avatar_url: Optional[str] = None) -> discord.Embed:
    """Build a premium stats embed with progress bar, dynamic header, and breakdown."""
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

    # Dynamic header message based on current state
    if total == 0:
        header = t("stats_header_empty", lang)
    elif overdue > 0:
        header = t("stats_header_overdue", lang, overdue=overdue)
    elif done == total and total > 0:
        header = t("stats_header_all_done", lang)
    else:
        header = t("stats_header_on_track", lang)

    embed = discord.Embed(
        title=f"📊 {t('stats_title', lang)}  ·  {username}",
        description=f"> **{header}**",
        color=color,
    )

    # Optional: set user avatar as thumbnail
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)

    # Completion progress bar
    bar = progress_bar(done, total)
    embed.add_field(
        name=t("stats_completion_rate", lang),
        value=bar,
        inline=False,
    )

    # 3-column breakdown grouped logically:
    # Row 1: Active / Immediate attention
    embed.add_field(name=f"⏳ {t('stats_pending', lang)}",   value=f"**{pending}**",   inline=True)
    embed.add_field(name=f"🚨 {t('stats_overdue', lang)}",   value=f"**{overdue}**",   inline=True)
    embed.add_field(name="📌 Pinned",                        value=f"**{pinned}**",    inline=True)
    # Row 2: Finished / Lifetime totals
    embed.add_field(name=f"✅ {t('stats_completed', lang)}", value=f"**{done}**",      inline=True)
    embed.add_field(name=f"❌ {t('stats_cancelled', lang)}",  value=f"**{cancelled}**", inline=True)
    embed.add_field(name=f"📝 {t('stats_total', lang)}",     value=f"**{total}**",     inline=True)

    # Motivational note
    if total == 0:
        note = t("stats_note_empty", lang)
    elif overdue > 0:
        note = t("stats_note_overdue", lang, overdue=overdue)
    elif done == total and total > 0:
        note = t("stats_note_all_done", lang)
    else:
        pct = int(done / total * 100) if total else 0
        note = t("stats_note_progress", lang, pct=pct)
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
        created_val = row.get("created_at") if hasattr(row, "get") else row["created_at"]
        if isinstance(created_val, datetime):
            if created_val.tzinfo is None:
                created_val = pytz.utc.localize(created_val)
            try:
                user_tz = pytz.timezone(tz_name)
                created_str = created_val.astimezone(user_tz).strftime("%d/%m/%Y %H:%M")
            except Exception:
                created_str = created_val.strftime("%d/%m/%Y %H:%M")
        else:
            created_str = str(created_val or "")

        w.writerow([
            row["task_id"], row["task"], row["status"], row["priority"],
            format_deadline(row["deadline"], tz_name),
            row["recurring"] or "",
            row["category_id"] or "",
            row["tags"] or "",
            (row["description"] or "").replace("\n", " "),
            bool(row["is_pinned"]) if hasattr(row, "keys") and "is_pinned" in row.keys() else False,
            created_str,
        ])
    return io.BytesIO(out.getvalue().encode("utf-8-sig"))  # BOM for Excel
