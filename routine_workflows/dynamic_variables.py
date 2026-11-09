"""
Dynamic template variables engine for task & workflow templates.
Resolves dynamic placeholders such as {{today}}, {{tomorrow}}, {{month_name}},
{{year}}, {{week_number}}, {{assignee}}, {{creator}}, {{project_name}}, {{sprint_name}}.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Optional
import pytz


def resolve_template_variables(
    text: Optional[str],
    context: Optional[dict[str, Any]] = None,
    tz_name: str = "UTC",
) -> str:
    """
    Replaces template variables {{variable}} in text with resolved values.

    Supported variables (case-insensitive):
    - {{today}}: Current date (YYYY-MM-DD)
    - {{tomorrow}}: Tomorrow's date (YYYY-MM-DD)
    - {{month_name}}: Full month name (e.g. January, November)
    - {{year}}: Current year (e.g. 2026)
    - {{week_number}}: ISO week number (e.g. 45)
    - {{assignee}}: Assigned member mention or name
    - {{creator}}: Creator/owner mention or name
    - {{project_name}}: Project name
    - {{sprint_name}}: Current active sprint name
    """
    if not text or not isinstance(text, str):
        return "" if text is None else str(text)

    ctx = context or {}

    try:
        user_tz = pytz.timezone(ctx.get("tz_name") or tz_name)
    except Exception:
        user_tz = pytz.utc

    now_dt = ctx.get("now_local")
    if not isinstance(now_dt, datetime):
        now_dt = datetime.now(user_tz)
    elif now_dt.tzinfo is None:
        now_dt = user_tz.localize(now_dt)

    tomorrow_dt = now_dt + timedelta(days=1)
    iso_week = now_dt.isocalendar()[1]

    user_id = ctx.get("user_id") or ctx.get("creator_id") or ctx.get("owner_id")
    creator_val = ctx.get("creator") or (f"<@{user_id}>" if user_id else "")

    assignee_id = ctx.get("assignee_id")
    assignee_val = ctx.get("assignee") or (f"<@{assignee_id}>" if assignee_id else "")

    mapping: dict[str, str] = {
        "today": now_dt.strftime("%Y-%m-%d"),
        "tomorrow": tomorrow_dt.strftime("%Y-%m-%d"),
        "month_name": now_dt.strftime("%B"),
        "year": str(now_dt.year),
        "week_number": str(iso_week),
        "iso_week": str(iso_week),
        "assignee": str(assignee_val),
        "creator": str(creator_val),
        "project_name": str(ctx.get("project_name") or ""),
        "sprint_name": str(ctx.get("sprint_name") or ""),
    }

    pattern = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

    def _replace(match: re.Match) -> str:
        var_name = match.group(1).lower()
        if var_name in mapping:
            return mapping[var_name]
        return match.group(0)

    return pattern.sub(_replace, text)

