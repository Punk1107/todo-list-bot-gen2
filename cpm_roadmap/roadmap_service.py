"""
cpm_roadmap/roadmap_service.py — Strategic Milestone Roadmap Management & Health Predictor Engine.

Features:
  - Strategic Milestone CRUD operations
  - Task-to-Milestone association
  - Realtime Health Predictor Engine (🟢 On Track / 🟡 At Risk / 🔴 Delayed)
  - Bottleneck task identification and Project Lead risk reporting
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, List, Optional

from core.database import db
from cpm_roadmap.models import HealthStatus, MilestoneHealth, ProjectMilestone

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Milestone Operations
# ─────────────────────────────────────────────────────────────────────────────

async def create_milestone(
    project_id: int,
    title: str,
    target_date: datetime,
) -> ProjectMilestone:
    """Create a new strategic milestone for a project."""
    row = await db.afetchone(
        """
        INSERT INTO project_milestones (project_id, title, target_date, status)
        VALUES ($1, $2, $3, 'active')
        RETURNING milestone_id, project_id, title, target_date, status
        """,
        (project_id, title.strip(), target_date),
    )
    if not row:
        raise RuntimeError("Failed to create milestone in database.")
    return ProjectMilestone.from_row(row)


async def get_milestone(milestone_id: int) -> Optional[ProjectMilestone]:
    """Retrieve milestone by ID with aggregated task counts and story points."""
    row = await db.afetchone(
        """
        SELECT m.milestone_id, m.project_id, m.title, m.target_date, m.status,
               COUNT(t.task_id) AS total_tasks,
               COUNT(t.task_id) FILTER (WHERE t.status = 'Completed') AS completed_tasks,
               COALESCE(SUM(t.story_points), 0) AS total_points,
               COALESCE(SUM(t.story_points) FILTER (WHERE t.status = 'Completed'), 0) AS completed_points
        FROM project_milestones m
        LEFT JOIN tasks t ON t.milestone_id = m.milestone_id AND t.is_deleted = FALSE
        WHERE m.milestone_id = $1
        GROUP BY m.milestone_id, m.project_id, m.title, m.target_date, m.status
        """,
        (milestone_id,),
    )
    if not row:
        return None
    return ProjectMilestone.from_row(row)


async def get_project_milestones(project_id: int) -> List[ProjectMilestone]:
    """List all milestones for a project ordered by target delivery date."""
    rows = await db.afetchall(
        """
        SELECT m.milestone_id, m.project_id, m.title, m.target_date, m.status,
               COUNT(t.task_id) AS total_tasks,
               COUNT(t.task_id) FILTER (WHERE t.status = 'Completed') AS completed_tasks,
               COALESCE(SUM(t.story_points), 0) AS total_points,
               COALESCE(SUM(t.story_points) FILTER (WHERE t.status = 'Completed'), 0) AS completed_points
        FROM project_milestones m
        LEFT JOIN tasks t ON t.milestone_id = m.milestone_id AND t.is_deleted = FALSE
        WHERE m.project_id = $1
        GROUP BY m.milestone_id, m.project_id, m.title, m.target_date, m.status
        ORDER BY m.target_date ASC
        """,
        (project_id,),
    )
    return [ProjectMilestone.from_row(r) for r in (rows or [])]


async def attach_task_to_milestone(task_id: int, milestone_id: int, project_id: int) -> bool:
    """Link a project task to a milestone."""
    res = await db.aexecute(
        """
        UPDATE tasks
        SET milestone_id = $1
        WHERE task_id = $2 AND project_id = $3 AND is_deleted = FALSE
        """,
        (milestone_id, task_id, project_id),
    )
    return "UPDATE 1" in res


async def get_milestone_tasks(milestone_id: int) -> List[dict[str, Any]]:
    """Retrieve all tasks attached to a milestone."""
    rows = await db.afetchall(
        """
        SELECT task_id, task, status, priority, story_points, deadline
        FROM tasks
        WHERE milestone_id = $1 AND is_deleted = FALSE
        ORDER BY priority DESC, created_at ASC
        """,
        (milestone_id,),
    )
    return [dict(r) for r in (rows or [])]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Health Predictor Engine
# ─────────────────────────────────────────────────────────────────────────────

def calculate_milestone_health(
    milestone: ProjectMilestone,
    start_date: datetime,
    now: datetime,
    bottlenecks: Optional[List[dict[str, Any]]] = None,
) -> MilestoneHealth:
    """
    Pure calculation: compute health classification based on progress vs elapsed time.
    """
    # 1. Elapsed Time Ratio
    total_time = (milestone.target_date - start_date).total_seconds()
    if total_time <= 0:
        elapsed_pct = 100.0
    else:
        elapsed = (now - start_date).total_seconds()
        elapsed_pct = max(0.0, min(100.0, round((elapsed / total_time) * 100.0, 1)))

    # 2. Completed Work Ratio
    if milestone.total_points > 0:
        progress_pct = round((milestone.completed_points / milestone.total_points) * 100.0, 1)
    elif milestone.total_tasks > 0:
        progress_pct = round((milestone.completed_tasks / milestone.total_tasks) * 100.0, 1)
    else:
        progress_pct = 0.0

    gap = round(elapsed_pct - progress_pct, 1)
    b_list = bottlenecks or []

    # 3. Health Classification
    # 🟢 On Track: progress is on pace or ahead, or lag <= 10%
    if progress_pct >= 100.0 or gap <= 10.0:
        status = HealthStatus.ON_TRACK
        rec = "งานดำเนินไปตามแผนและสอดคล้องกับกรอบเวลาส่งมอบ รักษาความเร็วในการทำงานนี้ต่อไป"
        b_list = []

    # 🟡 At Risk: progress lags between 10% and 25%
    elif gap <= 25.0:
        status = HealthStatus.AT_RISK
        rec = f"ความคืบหน้าช้ากว่าแผน {gap}% แนะนำให้ปรับลดขอบเขตงาน (Scope Reduction) หรือเพิ่มกำลังคนเพื่อเร่งส่งมอบ"

    # 🔴 Delayed: progress lags > 25%
    else:
        status = HealthStatus.DELAYED
        rec = f"ความคืบหน้าช้ากว่าแผน {gap}% มีความเสี่ยงสูงที่จะส่งมอบไม่ทันตามเป้าหมาย! ต้องแก้ไขงานคอขวดด่วน"

    return MilestoneHealth(
        milestone_id=milestone.milestone_id,
        title=milestone.title,
        target_date=milestone.target_date,
        status=status,
        elapsed_pct=elapsed_pct,
        progress_pct=progress_pct,
        gap_pct=gap,
        recommendation=rec,
        bottleneck_tasks=b_list,
    )


async def predict_milestone_health(milestone_id: int) -> MilestoneHealth:
    """
    Calculate realtime health status for a milestone by querying database
    and passing parameters to calculate_milestone_health.
    """
    milestone = await get_milestone(milestone_id)
    if not milestone:
        raise ValueError(f"Milestone #{milestone_id} not found.")

    proj_row = await db.afetchone(
        "SELECT created_at FROM projects WHERE project_id = $1",
        (milestone.project_id,),
    )
    start_date = proj_row["created_at"] if proj_row and proj_row.get("created_at") else (milestone.target_date - 30 * 86400)
    now = datetime.now(timezone.utc)

    bottlenecks = await _identify_bottlenecks(milestone.project_id, milestone.milestone_id)
    return calculate_milestone_health(milestone, start_date, now, bottlenecks)


async def _identify_bottlenecks(project_id: int, milestone_id: int) -> List[dict[str, Any]]:
    """
    Identify critical bottleneck tasks that block multiple other tasks
    or are overdue within the project/milestone.
    """
    rows = await db.afetchall(
        """
        SELECT t.task_id, t.task, t.status, t.deadline,
               COUNT(d.task_id) AS blocked_dependents_count
        FROM tasks t
        LEFT JOIN project_task_dependencies d ON d.blocked_by_task_id = t.task_id
        WHERE t.project_id = $1 AND t.status != 'Completed' AND t.is_deleted = FALSE
        GROUP BY t.task_id, t.task, t.status, t.deadline
        HAVING COUNT(d.task_id) > 0 OR t.deadline < NOW()
        ORDER BY COUNT(d.task_id) DESC, t.deadline ASC NULLS LAST
        LIMIT 5
        """,
        (project_id,),
    )
    return [dict(r) for r in (rows or [])]
