"""
utils/conflict_resolver.py — Conflict Resolution & Defensive Programming utilities

Implements:
  - Duplicate task name detection (case-insensitive, Pending status)
  - Auto-rename with sequential suffix generation
  - Enhanced defensive deadline validation (past check, year range, subtask hierarchy)
  - Smart Snooze: guarantees overdue tasks are always moved to the future
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytz

log = logging.getLogger(__name__)

# How far ahead a deadline can be set (years)
_MAX_YEARS_AHEAD = 10
# How many seconds of grace to allow for near-simultaneous submissions
_DEADLINE_GRACE_SECONDS = 60


# ─────────────────────────────────────────────────────────────────────────────
# Duplicate Task Detection
# ─────────────────────────────────────────────────────────────────────────────

async def check_duplicate_task(
    uid: str,
    task_name: str,
    parent_task_id: Optional[int] = None,
    exclude_task_id: Optional[int] = None,
) -> Optional[dict]:
    """
    Check if a Pending task with the same name (case-insensitive, trimmed)
    already exists for this user.

    - If parent_task_id is given, only checks sibling subtasks under the same parent.
    - If exclude_task_id is given, the task with that ID is ignored (useful for edits).
    - Returns the conflicting task row dict if found, otherwise None.
    """
    from core.database import db  # lazy import to avoid circular imports

    name_lower = task_name.strip().lower()

    if parent_task_id is not None:
        # Subtask scope: only check siblings under the same parent
        sql = """
            SELECT task_id, task, deadline, status
            FROM tasks
            WHERE owner_id=$1
              AND status='Pending'
              AND parent_task_id=$2
              AND LOWER(TRIM(task))=$3
        """
        params: tuple = (uid, parent_task_id, name_lower)
    else:
        # Top-level task scope
        sql = """
            SELECT task_id, task, deadline, status
            FROM tasks
            WHERE owner_id=$1
              AND status='Pending'
              AND parent_task_id IS NULL
              AND LOWER(TRIM(task))=$2
        """
        params = (uid, name_lower)

    row = await db.afetchone(sql, params)

    if row is None:
        return None

    # Exclude the task currently being edited
    if exclude_task_id is not None and row["task_id"] == exclude_task_id:
        return None

    return dict(row)


async def suggest_unique_task_name(
    uid: str,
    base_name: str,
    parent_task_id: Optional[int] = None,
) -> str:
    """
    Find the next available unique name by appending a counter suffix.
    e.g. "My Task" -> "My Task (2)" -> "My Task (3)" ...
    Only considers Pending tasks.
    """
    from core.database import db

    if parent_task_id is not None:
        sql = """
            SELECT task FROM tasks
            WHERE owner_id=$1 AND status='Pending' AND parent_task_id=$2
              AND LOWER(TRIM(task)) LIKE LOWER($3)
        """
        params = (uid, parent_task_id, f"{base_name.strip()} (%)")
    else:
        sql = """
            SELECT task FROM tasks
            WHERE owner_id=$1 AND status='Pending' AND parent_task_id IS NULL
              AND LOWER(TRIM(task)) LIKE LOWER($2)
        """
        params = (uid, f"{base_name.strip()} (%)")

    existing_rows = await db.afetchall(sql, params)

    # Collect existing suffix numbers
    used_numbers: set[int] = set()
    suffix_re = re.compile(r"^(.+?)\s*\((\d+)\)$", re.IGNORECASE)
    for r in (existing_rows or []):
        m = suffix_re.match(r["task"].strip())
        if m:
            try:
                used_numbers.add(int(m.group(2)))
            except ValueError:
                pass

    # Find the smallest unused number >= 2
    counter = 2
    while counter in used_numbers:
        counter += 1

    return f"{base_name.strip()} ({counter})"


# ─────────────────────────────────────────────────────────────────────────────
# Defensive Deadline Validation
# ─────────────────────────────────────────────────────────────────────────────

class DeadlineValidationError(ValueError):
    """Raised when a deadline fails defensive validation. Contains i18n key + kwargs."""

    def __init__(self, i18n_key: str, **kwargs) -> None:
        super().__init__(i18n_key)
        self.i18n_key = i18n_key
        self.kwargs = kwargs


def validate_deadline_defensive(
    deadline_str: str,
    tz_name: str,
    parent_deadline_iso: Optional[str] = None,
    grace_seconds: int = _DEADLINE_GRACE_SECONDS,
) -> datetime:
    """
    Parse and defensively validate a deadline string.

    Checks performed (in order):
      1. Parse the deadline string via helpers.parse_deadline
      2. Sanity-check the year (must be between year 2000 and _MAX_YEARS_AHEAD from now)
      3. Reject past deadlines (with a configurable grace buffer)
      4. If parent_deadline_iso is provided, reject deadlines that exceed the parent's

    Returns the UTC-aware datetime on success.
    Raises DeadlineValidationError with an i18n key + context kwargs on failure.
    """
    from utils.helpers import parse_deadline

    # Step 1: Parse
    dt = parse_deadline(deadline_str, tz_name)
    if dt is None:
        raise DeadlineValidationError("task_invalid_deadline")

    # Step 2: Year range check
    now_utc = datetime.now(timezone.utc)
    max_future = now_utc.replace(year=now_utc.year + _MAX_YEARS_AHEAD)
    if dt > max_future:
        raise DeadlineValidationError("task_invalid_year")
    if dt.year < 2000:
        raise DeadlineValidationError("task_invalid_year")

    # Step 3: Past deadline check (with grace buffer)
    cutoff = now_utc - timedelta(seconds=grace_seconds)
    if dt < cutoff:
        # Build human-friendly current time in user's local timezone for the error message
        try:
            local_tz = pytz.timezone(tz_name)
        except pytz.exceptions.UnknownTimeZoneError:
            local_tz = pytz.utc
        current_local = now_utc.astimezone(local_tz).strftime("%d/%m/%Y %H:%M")
        input_local = dt.astimezone(local_tz).strftime("%d/%m/%Y %H:%M")
        raise DeadlineValidationError(
            "task_past_deadline_detailed",
            current_time=current_local,
            input_time=input_local,
        )

    # Step 4: Subtask hierarchy check — subtask deadline must not exceed parent's
    if parent_deadline_iso is not None:
        try:
            if isinstance(parent_deadline_iso, str):
                parent_dt = datetime.fromisoformat(parent_deadline_iso)
            else:
                parent_dt = parent_deadline_iso  # type: ignore[assignment]
            if parent_dt.tzinfo is None:
                parent_dt = pytz.utc.localize(parent_dt)
            if dt > parent_dt:
                # Format both for display in user's timezone
                try:
                    local_tz = pytz.timezone(tz_name)
                except pytz.exceptions.UnknownTimeZoneError:
                    local_tz = pytz.utc
                parent_dl_str = parent_dt.astimezone(local_tz).strftime("%d/%m/%Y %H:%M")
                subtask_dl_str = dt.astimezone(local_tz).strftime("%d/%m/%Y %H:%M")
                raise DeadlineValidationError(
                    "subtask_deadline_exceeds_parent",
                    subtask_dl=subtask_dl_str,
                    parent_dl=parent_dl_str,
                )
        except DeadlineValidationError:
            raise
        except Exception as exc:
            log.warning("Failed to parse parent deadline for subtask check: %s", exc)

    return dt


# ─────────────────────────────────────────────────────────────────────────────
# Defensive Snooze
# ─────────────────────────────────────────────────────────────────────────────

def calculate_defensive_snooze(
    current_deadline_iso: "str | datetime",
    now_utc: Optional[datetime] = None,
    days: int = 1,
) -> str:
    """
    Calculate the snoozed deadline, ensuring it is always in the future.

    For a task that is already overdue:
        new_deadline = max(original_deadline + days, now + days)
    For a task that is NOT overdue:
        new_deadline = original_deadline + days

    Returns the new deadline as an ISO format string.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = pytz.utc.localize(now_utc)

    # Parse the current deadline
    if isinstance(current_deadline_iso, datetime):
        dt = current_deadline_iso
    else:
        dt = datetime.fromisoformat(current_deadline_iso)
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)

    # Snooze from the deadline
    snoozed_from_deadline = dt + timedelta(days=days)

    # If task is overdue, also consider snoozing from now
    if dt < now_utc:
        snoozed_from_now = now_utc + timedelta(days=days)
        new_deadline = max(snoozed_from_deadline, snoozed_from_now)
    else:
        new_deadline = snoozed_from_deadline

    return new_deadline.isoformat()
