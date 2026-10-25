"""
organization/service.py — Business logic for Eisenhower Matrix & Custom Saved Filters
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from core.database import db
from organization.models import (
    EisenhowerMatrixData,
    EisenhowerQuadrant,
    EisenhowerTask,
    SavedFilter,
    SavedFilterCriteria,
)

log = logging.getLogger(__name__)

# Urgency threshold: 48 hours (in seconds)
_URGENT_THRESHOLD_SECS = 48 * 3600

# Maximum saved filters per user to avoid database bloat
_MAX_FILTERS_PER_USER = 25


# ─────────────────────────────────────────────────────────────────────────────
# 1. Eisenhower Matrix Logic
# ─────────────────────────────────────────────────────────────────────────────

def classify_task_quadrant(
    task_row: Mapping[str, Any],
    now: Optional[datetime] = None,
) -> tuple[EisenhowerQuadrant, bool, bool, str]:
    """
    Classify a task into one of the 4 Eisenhower Quadrants based on Priority and Deadline.
    Returns:
        (quadrant, is_urgent, is_important, relative_time_string)
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # 1. Importance: P4-P7 is Important, P0-P3 is Not Important
    prio = int(task_row.get("priority") or 0)
    is_important = prio >= 4

    # 2. Urgency: Deadline <= 48 hours or Overdue
    deadline_val = task_row.get("deadline")
    is_urgent = False
    rel_time = ""

    if deadline_val:
        try:
            if isinstance(deadline_val, datetime):
                dt = deadline_val
            elif isinstance(deadline_val, str):
                dt = datetime.fromisoformat(deadline_val)
            else:
                dt = None

            if dt:
                # Ensure UTC awareness
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                diff = (dt - now).total_seconds()
                if diff < 0:
                    is_urgent = True
                    hrs = int(abs(diff) // 3600)
                    if hrs < 24:
                        rel_time = f"🚨 Overdue {hrs}h"
                    else:
                        rel_time = f"🚨 Overdue {hrs // 24}d"
                elif diff <= _URGENT_THRESHOLD_SECS:
                    is_urgent = True
                    hrs = max(1, int(diff // 3600))
                    rel_time = f"⏳ In {hrs}h"
                else:
                    is_urgent = False
                    days = int(diff // 86400)
                    rel_time = f"📅 In {days}d"
        except Exception:
            is_urgent = False
            rel_time = ""

    # 3. Quadrant mapping
    if is_important and is_urgent:
        quadrant = EisenhowerQuadrant.Q1_DO_FIRST
    elif is_important and not is_urgent:
        quadrant = EisenhowerQuadrant.Q2_SCHEDULE
    elif not is_important and is_urgent:
        quadrant = EisenhowerQuadrant.Q3_DELEGATE
    else:
        quadrant = EisenhowerQuadrant.Q4_ELIMINATE

    return quadrant, is_urgent, is_important, rel_time


async def get_eisenhower_matrix(
    user_id: str,
    guild_id: Optional[str] = None,
    project_id: Optional[int] = None,
    is_guild_admin: bool = False,
    now: Optional[datetime] = None,
) -> EisenhowerMatrixData:
    """
    Fetch all active tasks for user/project/guild and organize into the 4 Eisenhower quadrants.
    Filters out Completed, Cancelled, and Soft-deleted tasks.
    Enforces privacy controls for confidential tasks.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if project_id is not None:
        # Project-scoped matrix
        rows = await db.afetchall(
            """SELECT * FROM tasks
               WHERE project_id = $1
                 AND is_deleted = FALSE
                 AND status NOT IN ('Completed', 'Cancelled')
               ORDER BY priority DESC, deadline ASC NULLS LAST""",
            (project_id,),
        )
        # Filter private tasks if caller is not owner, lead, or admin
        if not is_guild_admin:
            from collaboration import service as collab_service
            role = await collab_service.get_member_role(project_id, user_id)
            proj = await collab_service.get_project(project_id, guild_id or "") if guild_id else None
            is_lead = (role == "lead") or (proj and proj.owner_id == user_id)
            if not is_lead:
                rows = [r for r in (rows or []) if not r.get("is_private") or str(r.get("owner_id")) == user_id]
    elif guild_id:
        # Guild-scoped matrix: personal tasks of user + project tasks user is assigned to or owns
        rows = await db.afetchall(
            """SELECT t.* FROM tasks t
               WHERE t.is_deleted = FALSE
                 AND t.status NOT IN ('Completed', 'Cancelled')
                 AND (
                     (t.owner_id = $1 AND (t.guild_id = $2 OR t.guild_id IS NULL))
                     OR (t.guild_id = $2 AND EXISTS (
                         SELECT 1 FROM task_assignments ta WHERE ta.task_id = t.task_id AND ta.user_id = $1
                     ))
                     OR (t.guild_id = $2 AND t.project_id IS NOT NULL AND EXISTS (
                         SELECT 1 FROM project_members pm
                         WHERE pm.project_id = t.project_id AND pm.user_id = $1 AND pm.role = 'lead'
                     ))
                 )
               ORDER BY t.priority DESC, t.deadline ASC NULLS LAST""",
            (user_id, guild_id),
        )
    else:
        # Personal DM matrix
        rows = await db.afetchall(
            """SELECT * FROM tasks
               WHERE owner_id = $1
                 AND project_id IS NULL
                 AND is_deleted = FALSE
                 AND status NOT IN ('Completed', 'Cancelled')
               ORDER BY priority DESC, deadline ASC NULLS LAST""",
            (user_id,),
        )

    matrix = EisenhowerMatrixData()

    for r in (rows or []):
        quadrant, is_urgent, is_important, rel_time = classify_task_quadrant(r, now=now)
        task_item = EisenhowerTask(
            task_id        = int(r["task_id"]),
            task           = str(r["task"]),
            priority       = int(r.get("priority") or 0),
            status         = str(r.get("status") or "Pending"),
            deadline       = r.get("deadline"),
            tags           = r.get("tags"),
            description    = r.get("description"),
            owner_id       = str(r.get("owner_id") or ""),
            guild_id       = str(r.get("guild_id")) if r.get("guild_id") else None,
            project_id     = int(r.get("project_id")) if r.get("project_id") is not None else None,
            is_private     = bool(r.get("is_private") or False),
            quadrant       = quadrant,
            is_urgent      = is_urgent,
            is_important   = is_important,
            relative_time  = rel_time,
        )

        if quadrant == EisenhowerQuadrant.Q1_DO_FIRST:
            matrix.q1_tasks.append(task_item)
        elif quadrant == EisenhowerQuadrant.Q2_SCHEDULE:
            matrix.q2_tasks.append(task_item)
        elif quadrant == EisenhowerQuadrant.Q3_DELEGATE:
            matrix.q3_tasks.append(task_item)
        else:
            matrix.q4_tasks.append(task_item)

    return matrix


# ─────────────────────────────────────────────────────────────────────────────
# 2. Saved Filters / Smart Lists Logic
# ─────────────────────────────────────────────────────────────────────────────

async def create_saved_filter(
    owner_id: str,
    name: str,
    criteria: SavedFilterCriteria,
    guild_id: Optional[str] = None,
) -> SavedFilter:
    """Create or update a custom saved filter."""
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Filter name cannot be empty.")
    if len(clean_name) > 50:
        raise ValueError("Filter name cannot exceed 50 characters.")

    # Validate criteria priorities
    if criteria.min_priority is not None and not (0 <= criteria.min_priority <= 7):
        raise ValueError("min_priority must be between 0 and 7.")
    if criteria.max_priority is not None and not (0 <= criteria.max_priority <= 7):
        raise ValueError("max_priority must be between 0 and 7.")
    if criteria.min_priority is not None and criteria.max_priority is not None:
        if criteria.min_priority > criteria.max_priority:
            raise ValueError("min_priority cannot be greater than max_priority.")

    # Check if updating existing or creating new
    existing = await get_saved_filter_by_name(owner_id, clean_name, guild_id)
    if not existing:
        existing_count = await db.afetchone(
            "SELECT COUNT(*) AS cnt FROM saved_filters WHERE owner_id=$1",
            (owner_id,),
        )
        if existing_count and int(existing_count["cnt"] or 0) >= _MAX_FILTERS_PER_USER:
            raise ValueError(f"Maximum limit of {_MAX_FILTERS_PER_USER} saved filters reached.")

    crit_json = json.dumps(criteria.to_dict())

    row = await db.afetchone(
        """INSERT INTO saved_filters (owner_id, guild_id, name, criteria, created_at, updated_at)
           VALUES ($1, $2, $3, $4::jsonb, NOW(), NOW())
           ON CONFLICT (owner_id, name) DO UPDATE
           SET criteria = EXCLUDED.criteria,
               guild_id = EXCLUDED.guild_id,
               updated_at = NOW()
           RETURNING *""",
        (owner_id, guild_id, clean_name, crit_json),
    )
    db.query_cache.invalidate_table("saved_filters")
    return SavedFilter.from_record(row)


async def get_saved_filter(filter_id: int, owner_id: str) -> Optional[SavedFilter]:
    """Retrieve a single saved filter by ID and verify owner."""
    row = await db.afetchone(
        "SELECT * FROM saved_filters WHERE filter_id=$1 AND owner_id=$2",
        (filter_id, owner_id),
    )
    return SavedFilter.from_record(row) if row else None


async def get_saved_filter_by_name(
    owner_id: str, name: str, guild_id: Optional[str] = None
) -> Optional[SavedFilter]:
    """Retrieve a saved filter by exact name for the given owner."""
    clean_name = name.strip()
    row = await db.afetchone(
        "SELECT * FROM saved_filters WHERE owner_id=$1 AND LOWER(name)=LOWER($2)",
        (owner_id, clean_name),
    )
    return SavedFilter.from_record(row) if row else None


async def list_saved_filters(
    owner_id: str, guild_id: Optional[str] = None
) -> list[SavedFilter]:
    """Return all saved filters for the user."""
    rows = await db.afetchall(
        """SELECT * FROM saved_filters
           WHERE owner_id=$1
             AND (guild_id=$2 OR guild_id IS NULL OR $2 IS NULL)
           ORDER BY updated_at DESC, name ASC""",
        (owner_id, guild_id),
    )
    return [SavedFilter.from_record(r) for r in (rows or [])]


async def delete_saved_filter(filter_id: int, owner_id: str) -> bool:
    """Delete a saved filter by ID."""
    row = await db.afetchone(
        "DELETE FROM saved_filters WHERE filter_id=$1 AND owner_id=$2 RETURNING filter_id",
        (filter_id, owner_id),
    )
    if row:
        db.query_cache.invalidate_table("saved_filters")
        return True
    return False


async def delete_saved_filter_by_name(owner_id: str, name: str) -> bool:
    """Delete a saved filter by name."""
    clean_name = name.strip()
    row = await db.afetchone(
        "DELETE FROM saved_filters WHERE owner_id=$1 AND LOWER(name)=LOWER($2) RETURNING filter_id",
        (owner_id, clean_name),
    )
    if row:
        db.query_cache.invalidate_table("saved_filters")
        return True
    return False


async def execute_saved_filter(
    saved_filter: SavedFilter,
    user_id: str,
    guild_id: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """
    Execute a saved filter criteria against the tasks table and return matching rows.
    Guarantees soft-deleted tasks (is_deleted = TRUE) are excluded.
    """
    crit = saved_filter.criteria
    params: list[Any] = []
    idx = 1

    where_clauses = ["t.is_deleted = FALSE"]

    # Scope
    if crit.project_id is not None:
        where_clauses.append(f"t.project_id = ${idx}")
        params.append(crit.project_id)
        idx += 1
    elif guild_id:
        where_clauses.append(f"(t.owner_id = ${idx} OR t.guild_id = ${idx+1})")
        params.extend([user_id, guild_id])
        idx += 2
    else:
        where_clauses.append(f"t.owner_id = ${idx} AND t.guild_id IS NULL")
        params.append(user_id)
        idx += 1

    # Status
    if crit.status:
        st = crit.status.strip()
        if st.lower() == "active":
            where_clauses.append("t.status NOT IN ('Completed', 'Cancelled')")
        else:
            where_clauses.append(f"t.status = ${idx}")
            params.append(st)
            idx += 1

    # Priority
    if crit.min_priority is not None:
        where_clauses.append(f"t.priority >= ${idx}")
        params.append(int(crit.min_priority))
        idx += 1

    if crit.max_priority is not None:
        where_clauses.append(f"t.priority <= ${idx}")
        params.append(int(crit.max_priority))
        idx += 1

    # Tags (matches any specified tag)
    if crit.tags:
        tag_conditions = []
        for tag in crit.tags:
            tag_clean = tag.strip().lower()
            if tag_clean:
                tag_conditions.append(f"LOWER(COALESCE(t.tags, '')) LIKE ${idx}")
                params.append(f"%{tag_clean}%")
                idx += 1
        if tag_conditions:
            where_clauses.append(f"({' OR '.join(tag_conditions)})")

    # Deadline conditions
    if crit.has_deadline is True:
        where_clauses.append("t.deadline IS NOT NULL")
    elif crit.has_deadline is False:
        where_clauses.append("t.deadline IS NULL")

    if crit.due_within_days is not None and crit.due_within_days >= 0:
        where_clauses.append(
            f"(t.deadline IS NOT NULL AND CASE WHEN t.deadline ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}' THEN t.deadline::timestamptz <= (NOW() + INTERVAL '{int(crit.due_within_days)} days') ELSE FALSE END)"
        )

    # Sort
    sort_sql = "t.priority DESC, t.deadline ASC NULLS LAST"
    if crit.sort_by == "deadline_asc":
        sort_sql = "t.deadline ASC NULLS LAST, t.priority DESC"
    elif crit.sort_by == "created_desc":
        sort_sql = "t.created_at DESC"
    elif crit.sort_by == "priority_desc":
        sort_sql = "t.priority DESC, t.deadline ASC NULLS LAST"

    where_sql = " AND ".join(where_clauses)
    query = f"""SELECT t.* FROM tasks t
               WHERE {where_sql}
               ORDER BY {sort_sql}
               LIMIT ${idx}"""
    params.append(min(limit, 100))

    rows = await db.afetchall(query, tuple(params))
    return [dict(r) for r in (rows or [])]
