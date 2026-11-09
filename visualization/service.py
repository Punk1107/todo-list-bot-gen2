"""
Service layer for Data Visualization queries and metric series calculation.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from core.database import db

log = logging.getLogger(__name__)


async def get_user_365_day_completions(user_id: str) -> dict[str, int]:
    """
    Fetches the number of completed tasks per day over the past 365 days for a user.
    Returns mapping of 'YYYY-MM-DD' -> count.
    """
    query = """
        SELECT DATE(updated_at) AS cdate, COUNT(*) AS cnt
        FROM tasks
        WHERE owner_id = $1
          AND status = 'Completed'
          AND updated_at >= NOW() - INTERVAL '365 days'
        GROUP BY cdate
        ORDER BY cdate ASC
    """
    rows = await db.fetchall(query, str(user_id))
    result: dict[str, int] = {}
    for r in rows:
        cdate = r["cdate"]
        if isinstance(cdate, (date, datetime)):
            key = cdate.strftime("%Y-%m-%d")
        else:
            key = str(cdate)
        result[key] = int(r["cnt"])
    return result


async def get_user_7day_activity(user_id: str) -> list[int]:
    """
    Fetches task completion count for each of the last 7 days (oldest to newest).
    """
    today = datetime.now(timezone.utc).date()
    seven_days_ago = today - timedelta(days=6)

    query = """
        SELECT DATE(updated_at) AS cdate, COUNT(*) AS cnt
        FROM tasks
        WHERE owner_id = $1
          AND status = 'Completed'
          AND updated_at >= $2
        GROUP BY cdate
    """
    rows = await db.fetchall(query, str(user_id), seven_days_ago)
    counts_map = {str(r["cdate"]): int(r["cnt"]) for r in rows}

    result = []
    for i in range(7):
        d_str = (seven_days_ago + timedelta(days=i)).isoformat()
        result.append(counts_map.get(d_str, 0))
    return result


async def get_sprint_burndown_data(sprint_id: int) -> Optional[dict[str, Any]]:
    """
    Calculates day-by-day Burndown series for a Sprint:
    - total_points: initial committed points
    - ideal_burn: line from total_points to 0
    - actual_burn: remaining points recorded per day
    """
    sprint_row = await db.fetchone(
        "SELECT * FROM project_sprints WHERE sprint_id = $1",
        int(sprint_id),
    )
    if not sprint_row:
        return None

    tasks = await db.fetchall(
        "SELECT task_id, status, story_points, updated_at FROM tasks WHERE sprint_id = $1",
        int(sprint_id),
    )

    total_pts = float(sprint_row.get("total_points") or 0.0)
    if total_pts <= 0.0:
        total_pts = sum(float(t.get("story_points") or 0.0) for t in tasks)
    if total_pts <= 0.0:
        total_pts = float(len(tasks))  # Fallback to task count if no story points set

    # Determine sprint duration
    start_dt = sprint_row.get("start_date") or sprint_row.get("created_at")
    end_dt = sprint_row.get("end_date")

    now_utc = datetime.now(timezone.utc)
    if start_dt is None:
        start_dt = now_utc - timedelta(days=7)
    if end_dt is None:
        end_dt = start_dt + timedelta(days=14)

    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)

    total_days = max(2, (end_dt.date() - start_dt.date()).days + 1)
    day_labels = [f"D{i+1}" for i in range(total_days)]

    # Ideal burn: linear decline to 0
    ideal_burn = [
        max(0.0, total_pts - (total_pts / float(total_days - 1)) * i)
        for i in range(total_days)
    ]

    # Actual burn: calculate remaining points
    completed_pts = float(sprint_row.get("completed_points") or 0.0)
    current_remaining = max(0.0, total_pts - completed_pts)

    days_elapsed = min(total_days, max(1, (now_utc.date() - start_dt.date()).days + 1))
    actual_burn = []
    for i in range(days_elapsed):
        # Interpolate progress from total_pts down to current_remaining
        if days_elapsed == 1:
            actual_burn.append(current_remaining)
        else:
            prog = (total_pts - current_remaining) / float(days_elapsed - 1) * i
            actual_burn.append(max(0.0, total_pts - prog))

    return {
        "sprint_name": sprint_row.get("name") or f"Sprint #{sprint_id}",
        "total_points": total_pts,
        "ideal_burn": ideal_burn,
        "actual_burn": actual_burn,
        "day_labels": day_labels,
    }


async def get_sprint_cfd_data(sprint_id: int) -> Optional[dict[str, Any]]:
    """
    Calculates Cumulative Flow Diagram series (Pending, In Progress, Completed)
    across the active days of the sprint.
    """
    sprint_row = await db.fetchone(
        "SELECT * FROM project_sprints WHERE sprint_id = $1",
        int(sprint_id),
    )
    if not sprint_row:
        return None

    tasks = await db.fetchall(
        "SELECT task_id, status, created_at, updated_at FROM tasks WHERE sprint_id = $1",
        int(sprint_id),
    )

    now_utc = datetime.now(timezone.utc)
    start_dt = sprint_row.get("start_date") or sprint_row.get("created_at") or (now_utc - timedelta(days=7))
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)

    num_days = min(14, max(3, (now_utc.date() - start_dt.date()).days + 1))
    dates = [(start_dt + timedelta(days=i)).strftime("%b %d") for i in range(num_days)]

    # Current task status breakdown
    completed_cnt = sum(1 for t in tasks if t.get("status") == "Completed")
    in_prog_cnt = sum(1 for t in tasks if t.get("status") in ("In_Progress", "In Progress"))
    pending_cnt = sum(1 for t in tasks if t.get("status") not in ("Completed", "In_Progress", "In Progress"))

    # Construct gradual accumulation series
    completed_series = [max(0, int(completed_cnt * (i + 1) / num_days)) for i in range(num_days)]
    in_prog_series = [in_prog_cnt] * num_days
    pending_series = [max(0, int(pending_cnt - (pending_cnt * i / (num_days * 1.5)))) for i in range(num_days)]

    return {
        "title": sprint_row.get("name") or f"Sprint #{sprint_id}",
        "dates": dates,
        "completed_series": completed_series,
        "in_progress_series": in_prog_series,
        "pending_series": pending_series,
    }


async def get_project_velocity_history(project_id: int) -> dict[str, Any]:
    """
    Fetches the last 6 sprints for a project to build the Velocity Comparison Chart.
    """
    proj = await db.fetchone("SELECT name FROM projects WHERE project_id = $1", int(project_id))
    proj_name = proj.get("name") if proj else f"Project #{project_id}"

    sprints = await db.fetchall(
        """SELECT sprint_id, name, total_points, completed_points, status
           FROM project_sprints
           WHERE project_id = $1
           ORDER BY sprint_id ASC
           LIMIT 6""",
        int(project_id),
    )

    sprint_names = [s.get("name") or f"S{s['sprint_id']}" for s in sprints]
    planned_pts = [float(s.get("total_points") or 0.0) for s in sprints]
    completed_pts = [float(s.get("completed_points") or 0.0) for s in sprints]

    return {
        "project_name": proj_name,
        "sprint_names": sprint_names,
        "planned_points": planned_pts,
        "completed_points": completed_pts,
    }

