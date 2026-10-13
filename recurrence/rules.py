"""Validation and next-occurrence calculation for recurring tasks."""
from __future__ import annotations

import json
import calendar
from datetime import datetime, timedelta
from typing import Any, Optional

import pytz

from utils.helpers import calculate_next_deadline


def validate_rule(rule: object) -> dict[str, Any]:
    """Normalize a user-supplied recurrence rule or raise ValueError."""
    if not isinstance(rule, dict):
        raise ValueError("A recurrence rule must be an object.")

    kind = rule.get("type")
    if kind == "weekdays":
        return {"type": "weekdays"}

    if kind in {"every_n_days", "every_n_weeks"}:
        interval = rule.get("interval")
        upper_bound = 365 if kind == "every_n_days" else 52
        if isinstance(interval, bool) or not isinstance(interval, int) or not 1 <= interval <= upper_bound:
            raise ValueError(f"{kind} interval must be between 1 and {upper_bound}.")
        return {"type": kind, "interval": interval}

    if kind == "monthly_dates":
        days = rule.get("days")
        if not isinstance(days, list) or not days:
            raise ValueError("At least one day of the month is required.")
        if any(isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= 31 for day in days):
            raise ValueError("Month days must be integers from 1 to 31.")
        return {"type": kind, "days": sorted(set(days))}

    raise ValueError("Unknown recurrence rule.")


def decode_rule(value: object) -> Optional[dict[str, Any]]:
    """Decode JSONB values returned as either mappings or JSON strings."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("Stored recurrence rule is not valid JSON.") from exc
    return validate_rule(value)


def next_deadline(
    deadline_val: Any,
    legacy: Optional[str] = None,
    rule: object = None,
) -> Optional[str]:
    """Calculate the next deadline, preserving compatibility with legacy rules."""
    if rule is None:
        return calculate_next_deadline(deadline_val, legacy or "")

    normalized = validate_rule(rule)
    if isinstance(deadline_val, datetime):
        current = deadline_val
    elif isinstance(deadline_val, str):
        current = datetime.fromisoformat(deadline_val)
    else:
        return None
    if current.tzinfo is None:
        current = pytz.utc.localize(current)

    kind = normalized["type"]
    if kind == "weekdays":
        candidate = current + timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
    elif kind == "every_n_days":
        candidate = current + timedelta(days=normalized["interval"])
    elif kind == "every_n_weeks":
        candidate = current + timedelta(weeks=normalized["interval"])
    else:
        candidate = _next_month_date(current, normalized["days"])
    return candidate.isoformat()


def _next_month_date(current: datetime, days: list[int]) -> datetime:
    year, month = current.year, current.month
    for _ in range(24):
        last_day = calendar.monthrange(year, month)[1]
        for day in days:
            candidate = current.replace(
                year=year,
                month=month,
                day=min(day, last_day),
            )
            if candidate > current:
                return candidate
        month += 1
        if month > 12:
            month, year = 1, year + 1
    raise ValueError("Unable to calculate the next monthly recurrence.")
