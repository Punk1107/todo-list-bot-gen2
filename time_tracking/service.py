"""
time_tracking/service.py — Business logic for Time Tracking, Capacity & Estimation Engine.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import io
import logging
from typing import Any, Dict, List, Optional, Tuple

from core.database import db
from time_tracking.models import (
    ActiveTimer,
    CapacityMetric,
    EstimationMetric,
    ProjectBudgetMetric,
    TimeLogEntry,
    TimesheetSummary,
)

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Manual & Stopwatch Time Logging
# ─────────────────────────────────────────────────────────────────────────────

async def log_time(
    task_id: int,
    user_id: str,
    hours: float,
    note: Optional[str] = None,
    is_billable: Optional[bool] = None,
) -> TimeLogEntry:
    """Log spent hours on a task manually or via timer."""
    clean_hours = max(0.01, round(float(hours), 2))
    clean_note = note.strip() if note and note.strip() else None

    # Determine default billable status if not specified
    billable = False if is_billable is None else bool(is_billable)
    if is_billable is None:
        # Check if task belongs to a project with a set budget or member hourly rate
        proj_row = await db.fetchone(
            """
            SELECT p.budget, pm.hourly_rate
            FROM tasks t
            LEFT JOIN projects p ON t.project_id = p.project_id
            LEFT JOIN project_members pm ON p.project_id = pm.project_id AND pm.user_id = $2
            WHERE t.task_id = $1
            """,
            (task_id, user_id),
        )
        if proj_row and ((proj_row["budget"] and proj_row["budget"] > 0) or (proj_row["hourly_rate"] and proj_row["hourly_rate"] > 0)):
            billable = True

    row = await db.fetchone(
        """
        INSERT INTO task_time_logs (task_id, user_id, hours_spent, is_billable, note, logged_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
        RETURNING *
        """,
        (task_id, user_id, clean_hours, billable, clean_note),
    )
    db.query_cache.invalidate_table("task_time_logs")
    db.invalidate_stats(user_id)

    # Fetch task and project names for complete model
    info = await db.fetchone(
        """
        SELECT t.task AS task_title, t.project_id, p.name AS project_name
        FROM tasks t
        LEFT JOIN projects p ON t.project_id = p.project_id
        WHERE t.task_id = $1
        """,
        (task_id,),
    )
    merged = dict(row) if row else {}
    if info:
        merged.update(dict(info))

    return TimeLogEntry.from_row(merged)


async def get_task_time_logs(task_id: int) -> List[TimeLogEntry]:
    """Retrieve all logged time entries for a given task."""
    rows = await db.fetchall(
        """
        SELECT ttl.*, t.task AS task_title, t.project_id, p.name AS project_name
        FROM task_time_logs ttl
        JOIN tasks t ON ttl.task_id = t.task_id
        LEFT JOIN projects p ON t.project_id = p.project_id
        WHERE ttl.task_id = $1
        ORDER BY ttl.logged_at DESC
        """,
        (task_id,),
    )
    return [TimeLogEntry.from_row(r) for r in rows]


async def start_timer(user_id: str, task_id: int, note: Optional[str] = None) -> ActiveTimer:
    """Start an active stopwatch timer for a user on a specific task."""
    clean_note = note.strip() if note and note.strip() else None
    row = await db.fetchone(
        """
        INSERT INTO active_time_timers (user_id, task_id, started_at, note)
        VALUES ($1, $2, NOW(), $3)
        ON CONFLICT (user_id) DO UPDATE SET
            task_id = EXCLUDED.task_id,
            started_at = NOW(),
            note = EXCLUDED.note
        RETURNING *
        """,
        (user_id, task_id, clean_note),
    )
    db.query_cache.invalidate_table("active_time_timers")

    t_row = await db.fetchone("SELECT task FROM tasks WHERE task_id = $1", (task_id,))
    merged = dict(row) if row else {}
    if t_row:
        merged["task_title"] = t_row["task"]

    return ActiveTimer.from_row(merged)


async def get_active_timer(user_id: str) -> Optional[ActiveTimer]:
    """Get currently running stopwatch timer for user if any."""
    row = await db.fetchone(
        """
        SELECT att.*, t.task AS task_title
        FROM active_time_timers att
        JOIN tasks t ON att.task_id = t.task_id
        WHERE att.user_id = $1
        """,
        (user_id,),
    )
    return ActiveTimer.from_row(row) if row else None


async def stop_timer(user_id: str) -> Optional[Tuple[ActiveTimer, TimeLogEntry]]:
    """Stop active stopwatch timer and automatically record logged hours."""
    timer = await get_active_timer(user_id)
    if not timer:
        return None

    elapsed_h = timer.elapsed_hours()
    # Ensure minimum 0.01 hours (approx. 36 seconds)
    logged_h = max(0.01, elapsed_h)

    # Log time entry
    log_entry = await log_time(
        task_id=timer.task_id,
        user_id=user_id,
        hours=logged_h,
        note=timer.note,
    )

    # Delete active timer
    await db.execute("DELETE FROM active_time_timers WHERE user_id = $1", (user_id,))
    db.query_cache.invalidate_table("active_time_timers")

    return timer, log_entry


async def cancel_timer(user_id: str) -> bool:
    """Cancel and discard currently running timer without logging."""
    res = await db.execute("DELETE FROM active_time_timers WHERE user_id = $1", (user_id,))
    db.query_cache.invalidate_table("active_time_timers")
    return bool(res and "DELETE 1" in res)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Timesheet Aggregation & Export
# ─────────────────────────────────────────────────────────────────────────────

async def get_user_timesheet(
    user_id: str,
    period: str = "week",
) -> TimesheetSummary:
    """
    Aggregate user's logged hours over a specified period ('today', 'week', 'month', 'all').
    """
    now = datetime.now(timezone.utc)
    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start_date = now - timedelta(days=30)
    elif period == "all":
        start_date = datetime(2000, 1, 1, tzinfo=timezone.utc)
    else:  # default 'week'
        start_date = now - timedelta(days=7)

    rows = await db.fetchall(
        """
        SELECT ttl.*, t.task AS task_title, t.project_id, p.name AS project_name
        FROM task_time_logs ttl
        JOIN tasks t ON ttl.task_id = t.task_id
        LEFT JOIN projects p ON t.project_id = p.project_id
        WHERE ttl.user_id = $1 AND ttl.logged_at >= $2
        ORDER BY ttl.logged_at DESC
        """,
        (user_id, start_date),
    )

    entries = [TimeLogEntry.from_row(r) for r in rows]
    total_hours = round(sum(e.hours_spent for e in entries), 2)
    billable_hours = round(sum(e.hours_spent for e in entries if e.is_billable), 2)
    non_billable_hours = round(total_hours - billable_hours, 2)

    project_hours: Dict[str, float] = {}
    for e in entries:
        p_name = e.project_name or "Personal / No Project"
        project_hours[p_name] = round(project_hours.get(p_name, 0.0) + e.hours_spent, 2)

    return TimesheetSummary(
        user_id=user_id,
        period=period,
        total_hours=total_hours,
        billable_hours=billable_hours,
        non_billable_hours=non_billable_hours,
        entries=entries,
        project_hours=project_hours,
    )


def export_timesheet_csv(timesheet: TimesheetSummary) -> str:
    """Generate RFC 4180 compliant CSV string for timesheet records."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([
        "Log ID",
        "Task ID",
        "Task Title",
        "Project",
        "Hours",
        "Billable",
        "Logged At (UTC)",
        "Note",
    ])
    for e in timesheet.entries:
        writer.writerow([
            e.log_id,
            e.task_id,
            e.task_title or "",
            e.project_name or "Personal",
            f"{e.hours_spent:.2f}",
            "Yes" if e.is_billable else "No",
            e.logged_at.strftime("%Y-%m-%d %H:%M:%S"),
            e.note or "",
        ])
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Time Estimation vs. Actual Accuracy Analytics
# ─────────────────────────────────────────────────────────────────────────────

async def calculate_estimation_accuracy(
    project_id: Optional[int] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compare estimated_hours vs actual logged hours across tasks.
    Returns metrics, variance percentages, and categorized task breakdowns.
    """
    query = """
        SELECT
            t.task_id,
            t.task AS task_name,
            t.estimated_hours,
            COALESCE(SUM(ttl.hours_spent), 0.0) AS actual_hours
        FROM tasks t
        LEFT JOIN task_time_logs ttl ON t.task_id = ttl.task_id
        WHERE t.estimated_hours IS NOT NULL AND t.estimated_hours > 0 AND t.is_deleted = FALSE
    """
    params: List[Any] = []
    if project_id is not None:
        params.append(project_id)
        query += f" AND t.project_id = ${len(params)}"
    if user_id is not None:
        params.append(user_id)
        query += f" AND t.owner_id = ${len(params)}"

    query += " GROUP BY t.task_id, t.task, t.estimated_hours ORDER BY t.task_id ASC"

    rows = await db.fetchall(query, tuple(params))
    metrics: List[EstimationMetric] = []
    for r in rows:
        m = EstimationMetric.calculate(
            task_id=int(r["task_id"]),
            task_name=str(r["task_name"]),
            estimated_hours=float(r["estimated_hours"]),
            actual_hours=float(r["actual_hours"]),
        )
        metrics.append(m)

    total_est = round(sum(m.estimated_hours for m in metrics), 2)
    total_act = round(sum(m.actual_hours for m in metrics), 2)
    mean_accuracy = (
        round(sum(m.accuracy_pct for m in metrics) / len(metrics), 1)
        if metrics
        else 100.0
    )

    underestimated = [m for m in metrics if m.category == "underestimated"]
    overestimated = [m for m in metrics if m.category == "overestimated"]
    accurate = [m for m in metrics if m.category == "accurate"]

    return {
        "count": len(metrics),
        "total_estimated_hours": total_est,
        "total_actual_hours": total_act,
        "mean_accuracy_pct": mean_accuracy,
        "underestimated_count": len(underestimated),
        "overestimated_count": len(overestimated),
        "accurate_count": len(accurate),
        "metrics": metrics,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Team Workload Capacity & Burnout Shield
# ─────────────────────────────────────────────────────────────────────────────

async def set_user_capacity(user_id: str, weekly_hours: float) -> float:
    """Set or update user's weekly working capacity in hours (e.g. 35.0, 40.0)."""
    clean_hours = max(1.0, min(168.0, round(float(weekly_hours), 1)))
    await db.execute(
        """
        INSERT INTO user_workload_capacities (user_id, weekly_capacity_hours, updated_at)
        VALUES ($1, $2, NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            weekly_capacity_hours = EXCLUDED.weekly_capacity_hours,
            updated_at = NOW()
        """,
        (user_id, clean_hours),
    )
    db.query_cache.invalidate_table("user_workload_capacities")
    return clean_hours


async def get_user_capacity(user_id: str) -> float:
    """Retrieve user's weekly capacity hours (defaults to 40.0 hours)."""
    row = await db.fetchone(
        "SELECT weekly_capacity_hours FROM user_workload_capacities WHERE user_id = $1",
        (user_id,),
    )
    return float(row["weekly_capacity_hours"]) if row else 40.0


async def calculate_member_workload_capacity(
    guild_id: str,
    user_id: str,
) -> CapacityMetric:
    """
    Calculate member's allocated estimated workload percentage for active tasks.
    """
    capacity = await get_user_capacity(user_id)

    # Sum estimated_hours for active (Pending / In_Progress) tasks assigned to user
    row = await db.fetchone(
        """
        SELECT
            COUNT(DISTINCT t.task_id) AS task_count,
            COALESCE(SUM(t.estimated_hours), 0.0) AS total_est
        FROM tasks t
        LEFT JOIN task_assignments ta ON t.task_id = ta.task_id
        LEFT JOIN projects p ON t.project_id = p.project_id
        WHERE (ta.user_id = $1 OR t.owner_id = $1)
          AND t.status IN ('Pending', 'In_Progress')
          AND t.is_deleted = FALSE
          AND (p.guild_id = $2 OR (t.project_id IS NULL AND t.owner_id = $1))
        """,
        (user_id, guild_id),
    )

    assigned_hours = float(row["total_est"]) if row else 0.0
    task_count = int(row["task_count"]) if row else 0

    return CapacityMetric.compute(
        user_id=user_id,
        weekly_capacity_hours=capacity,
        assigned_estimated_hours=assigned_hours,
        active_task_count=task_count,
    )


async def check_burnout_shield(
    guild_id: str,
    user_id: str,
    additional_hours: float = 0.0,
) -> Optional[Dict[str, Any]]:
    """
    Check if assigning extra workload pushes user over 100% capacity.
    Returns warning dict if overloaded, or None if safe.
    """
    metric = await calculate_member_workload_capacity(guild_id, user_id)
    new_total = metric.assigned_estimated_hours + max(0.0, additional_hours)
    new_pct = round((new_total / metric.weekly_capacity_hours) * 100.0, 1)

    if new_pct > 100.0:
        return {
            "user_id": user_id,
            "weekly_capacity": metric.weekly_capacity_hours,
            "current_hours": metric.assigned_estimated_hours,
            "new_hours": new_total,
            "workload_pct": new_pct,
            "is_overloaded": True,
        }
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 5. Billable / Non-Billable Cost Calculation & Budget Tracking
# ─────────────────────────────────────────────────────────────────────────────

async def set_project_budget(
    project_id: int,
    budget: float,
    currency: str = "THB",
) -> None:
    """Set total budget and currency for a project."""
    clean_budget = max(0.0, round(float(budget), 2))
    clean_currency = currency.strip().upper()[:10] if currency and currency.strip() else "THB"

    await db.execute(
        "UPDATE projects SET budget = $1, currency = $2, updated_at = NOW() WHERE project_id = $3",
        (clean_budget, clean_currency, project_id),
    )
    db.query_cache.invalidate_table("projects")


async def set_member_rate(
    project_id: int,
    user_id: str,
    hourly_rate: float,
) -> None:
    """Set member's hourly billing rate for a project."""
    clean_rate = max(0.0, round(float(hourly_rate), 2))
    await db.execute(
        """
        UPDATE project_members
        SET hourly_rate = $1
        WHERE project_id = $2 AND user_id = $3
        """,
        (clean_rate, project_id, user_id),
    )
    db.query_cache.invalidate_table("project_members")


async def calculate_project_budget_spent(project_id: int) -> Optional[ProjectBudgetMetric]:
    """
    Calculate spent budget based on billable hours logged by members multiplied by their hourly rates.
    """
    proj = await db.fetchone(
        "SELECT project_id, name, budget, currency FROM projects WHERE project_id = $1",
        (project_id,),
    )
    if not proj:
        return None

    budget = float(proj["budget"]) if proj["budget"] is not None else 0.0
    currency = proj["currency"] or "THB"

    # Fetch all time logs for tasks in this project
    rows = await db.fetchall(
        """
        SELECT
            ttl.user_id,
            ttl.hours_spent,
            ttl.is_billable,
            COALESCE(pm.hourly_rate, 0.0) AS hourly_rate
        FROM task_time_logs ttl
        JOIN tasks t ON ttl.task_id = t.task_id
        LEFT JOIN project_members pm ON t.project_id = pm.project_id AND ttl.user_id = pm.user_id
        WHERE t.project_id = $1
        """,
        (project_id,),
    )

    total_billable_hours = 0.0
    total_non_billable_hours = 0.0
    spent_amount = 0.0
    member_costs: Dict[str, float] = {}

    for r in rows:
        h = float(r["hours_spent"])
        is_billable = bool(r["is_billable"])
        rate = float(r["hourly_rate"])
        uid = str(r["user_id"])

        if is_billable:
            total_billable_hours += h
            cost = h * rate
            spent_amount += cost
            member_costs[uid] = round(member_costs.get(uid, 0.0) + cost, 2)
        else:
            total_non_billable_hours += h

    spent_amount = round(spent_amount, 2)
    total_billable_hours = round(total_billable_hours, 2)
    total_non_billable_hours = round(total_non_billable_hours, 2)
    spent_pct = round((spent_amount / budget) * 100.0, 1) if budget > 0 else 0.0

    return ProjectBudgetMetric(
        project_id=project_id,
        project_name=proj["name"],
        budget=budget,
        currency=currency,
        spent_amount=spent_amount,
        spent_pct=spent_pct,
        total_billable_hours=total_billable_hours,
        total_non_billable_hours=total_non_billable_hours,
        is_near_limit=(spent_pct >= 80.0 and spent_pct < 100.0),
        is_over_budget=(spent_pct >= 100.0),
        member_costs=member_costs,
    )

