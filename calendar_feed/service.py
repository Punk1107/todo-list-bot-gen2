from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from core.database import db

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{40,60}$")


def create_feed_token() -> str:
    """Create a high-entropy URL-safe subscription token."""
    return secrets.token_urlsafe(32)


def hash_feed_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def escape_ical(value: str) -> str:
    return (value.replace("\\", "\\\\")
                 .replace("\r\n", "\n")
                 .replace("\r", "\n")
                 .replace("\n", "\\n")
                 .replace(",", "\\,")
                 .replace(";", "\\;"))


def _fold_ical_line(line: str) -> str:
    """Fold a content line at 75 UTF-8 octets, as required by RFC 5545."""
    chunks: list[str] = []
    current = ""
    octets = 0
    for char in line:
        size = len(char.encode("utf-8"))
        if octets + size > 75:
            chunks.append(current)
            current = " " + char
            octets = 1 + size
        else:
            current += char
            octets += size
    chunks.append(current)
    return "\r\n".join(chunks)


def _utc_stamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _as_utc_datetime(value) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _build_event(row, now: datetime) -> list[str]:
    deadline = _as_utc_datetime(row["deadline"])
    updated = row.get("updated_at") if hasattr(row, "get") else None
    lines = [
        "BEGIN:VEVENT",
        f"UID:task-{row['task_id']}@todo-list-bot",
        f"DTSTAMP:{_utc_stamp(now)}",
        f"DTSTART:{_utc_stamp(deadline)}",
        f"DTEND:{_utc_stamp(deadline + timedelta(minutes=15))}",
        f"SUMMARY:{escape_ical(row['task'])}",
    ]
    if row.get("description"):
        lines.append(f"DESCRIPTION:{escape_ical(row['description'])}")
    if updated:
        lines.append(f"LAST-MODIFIED:{_utc_stamp(_as_utc_datetime(updated))}")
    lines.append("END:VEVENT")
    return lines


def render_icalendar(rows, now: datetime | None = None) -> str:
    """Render task rows as a CRLF-terminated RFC 5545 calendar."""
    current = now or datetime.now(timezone.utc)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//To-Do List Bot//Calendar Feed//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for row in rows:
        lines.extend(_build_event(row, current))
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold_ical_line(line) for line in lines) + "\r\n"


async def build_calendar_feed(token: str) -> str:
    if not _TOKEN_RE.fullmatch(token):
        raise LookupError("Unknown calendar feed")
    token_hash = hash_feed_token(token)
    owner = await db.afetchone(
        "SELECT user_id FROM calendar_feed_tokens WHERE token_hash=$1",
        (token_hash,),
    )
    if owner is None:
        raise LookupError("Unknown calendar feed")
    tasks = await db.afetchall(
        """SELECT task_id, task, description, deadline, updated_at
           FROM tasks
           WHERE owner_id=$1 AND deadline IS NOT NULL
             AND is_deleted = FALSE
             AND status NOT IN ('Completed', 'Cancelled')
           ORDER BY deadline ASC, task_id ASC""",
        (owner["user_id"],),
    )
    return render_icalendar(tasks)
