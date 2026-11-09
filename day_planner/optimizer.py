"""
day_planner/optimizer.py — Smart Time-Blocker & Ergonomic Schedule Optimizer.

Combines Eisenhower Matrix Q1/Q2 priority analysis with ergonomic time blocking
(45m focus / 15m ergonomic rest / 60m lunch) to generate an optimized daily timetable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, List, Optional
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

from organization import service as org_service
from organization.models import EisenhowerQuadrant, EisenhowerTask

log = logging.getLogger(__name__)


@dataclass
class TimeBlock:
    """Represents a scheduled block of time in the user's day."""
    start_str: str          # e.g. "09:00"
    end_str: str            # e.g. "09:45"
    block_type: str         # "FOCUS", "BREAK", "LUNCH", "BUFFER"
    task_id: Optional[int] = None
    task_title: Optional[str] = None
    priority: Optional[int] = None
    quadrant: Optional[str] = None
    is_break: bool = False
    duration_mins: int = 0


@dataclass
class DayPlanResult:
    """The complete optimized daily plan for a user."""
    user_id: str
    work_date: str
    start_time: str
    end_time: str
    blocks: list[TimeBlock] = field(default_factory=list)
    total_focus_minutes: int = 0
    total_break_minutes: int = 0
    tasks_count: int = 0
    first_task_id: Optional[int] = None
    first_task_title: Optional[str] = None


def _parse_time_str(time_str: str, default_h: int = 9, default_m: int = 0) -> tuple[int, int]:
    """Parse string like '09:00', '9:30', '18' into (hours, minutes)."""
    if not time_str or not time_str.strip():
        return default_h, default_m

    cleaned = time_str.strip()
    if ":" in cleaned:
        parts = cleaned.split(":")
        try:
            h = max(0, min(23, int(parts[0])))
            m = max(0, min(59, int(parts[1])))
            return h, m
        except (ValueError, IndexError):
            return default_h, default_m
    elif cleaned.isdigit():
        try:
            h = max(0, min(23, int(cleaned)))
            return h, 0
        except ValueError:
            return default_h, default_m

    return default_h, default_m


def _mins_to_str(total_mins: int) -> str:
    """Convert minutes from midnight to HH:MM string."""
    h = (total_mins // 60) % 24
    m = total_mins % 60
    return f"{h:02d}:{m:02d}"


async def optimize_day_schedule(
    user_id: str,
    guild_id: Optional[str] = None,
    project_id: Optional[int] = None,
    start_time: str = "09:00",
    end_time: str = "18:00",
    focus_mins: int = 45,
    break_mins: int = 15,
    tz_name: str = "UTC",
) -> DayPlanResult:
    """
    Computes an optimal chronological schedule for the user's workday.
    
    1. Fetches active tasks categorized via Eisenhower Matrix (Q1/Q2/Q3/Q4).
    2. Sorts tasks prioritizing Q1 (Urgent & Important) and Q2 (Important).
    3. Allocates focus time blocks with ergonomic 15-minute breaks and a 60-minute lunch break.
    """
    # 1. Parse workday window
    start_h, start_m = _parse_time_str(start_time, default_h=9, default_m=0)
    end_h, end_m = _parse_time_str(end_time, default_h=18, default_m=0)

    start_total_mins = start_h * 60 + start_m
    end_total_mins = end_h * 60 + end_m

    if end_total_mins <= start_total_mins:
        start_total_mins = 9 * 60
        end_total_mins = 18 * 60

    # Sanitize block durations
    focus_mins = max(15, min(120, focus_mins))
    break_mins = max(5, min(30, break_mins))

    # Timezone & Date
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    now_local = datetime.now(tz)
    work_date_str = now_local.strftime("%Y-%m-%d")

    # 2. Retrieve tasks via Eisenhower Matrix
    matrix = await org_service.get_eisenhower_matrix(
        user_id=user_id,
        guild_id=guild_id,
        project_id=project_id,
        now=now_local,
    )

    # 3. Prioritize tasks: Q1 first, then Q2, then Q3, then Q4
    # Within each quadrant, overdue or due today first, then priority DESC
    def task_sort_key(t: EisenhowerTask) -> tuple[int, int]:
        is_urgent = 1 if t.is_urgent else 0
        return (-is_urgent, -t.priority)

    candidate_tasks: list[tuple[EisenhowerTask, str]] = []
    for t in sorted(matrix.q1_tasks, key=task_sort_key):
        candidate_tasks.append((t, "Q1 - Do First"))
    for t in sorted(matrix.q2_tasks, key=task_sort_key):
        candidate_tasks.append((t, "Q2 - Schedule"))
    for t in sorted(matrix.q3_tasks, key=task_sort_key):
        candidate_tasks.append((t, "Q3 - Delegate"))
    for t in sorted(matrix.q4_tasks, key=task_sort_key):
        candidate_tasks.append((t, "Q4 - Backlog"))

    # 4. Schedule blocks
    blocks: list[TimeBlock] = []
    curr = start_total_mins
    lunch_start = 12 * 60
    lunch_end = 13 * 60
    lunch_scheduled = False

    task_idx = 0
    num_tasks = len(candidate_tasks)
    total_focus = 0
    total_break = 0

    first_task_id: Optional[int] = None
    first_task_title: Optional[str] = None

    while curr < end_total_mins:
        # Check if lunch break is due
        if not lunch_scheduled and (start_total_mins < lunch_end and end_total_mins > lunch_start):
            if curr >= lunch_start or (curr + focus_mins > lunch_start + 15):
                # Schedule lunch break
                l_start = max(curr, lunch_start)
                l_end = min(l_start + 60, end_total_mins)
                if l_end > l_start:
                    blocks.append(
                        TimeBlock(
                            start_str=_mins_to_str(l_start),
                            end_str=_mins_to_str(l_end),
                            block_type="LUNCH",
                            task_title="🍱 พักรับประทานอาหารกลางวัน / Lunch Break",
                            is_break=True,
                            duration_mins=(l_end - l_start),
                        )
                    )
                    total_break += (l_end - l_start)
                    curr = l_end
                    lunch_scheduled = True
                    continue

        remaining_mins = end_total_mins - curr
        if remaining_mins < 15:
            # Buffer/wrap up
            blocks.append(
                TimeBlock(
                    start_str=_mins_to_str(curr),
                    end_str=_mins_to_str(end_total_mins),
                    block_type="BUFFER",
                    task_title="🏁 สรุปงานประจำวัน & เคลียร์ Inbox / Daily Wrap-up",
                    is_break=False,
                    duration_mins=remaining_mins,
                )
            )
            curr = end_total_mins
            break

        # Focus Block
        f_dur = min(focus_mins, remaining_mins)
        # Avoid running heavily into lunch
        if not lunch_scheduled and curr < lunch_start and curr + f_dur > lunch_start + 15:
            f_dur = lunch_start - curr

        if task_idx < num_tasks:
            task_item, quad_name = candidate_tasks[task_idx]
            task_idx += 1
            if first_task_id is None:
                first_task_id = task_item.task_id
                first_task_title = task_item.task

            blocks.append(
                TimeBlock(
                    start_str=_mins_to_str(curr),
                    end_str=_mins_to_str(curr + f_dur),
                    block_type="FOCUS",
                    task_id=task_item.task_id,
                    task_title=task_item.task,
                    priority=task_item.priority,
                    quadrant=quad_name,
                    is_break=False,
                    duration_mins=f_dur,
                )
            )
        else:
            # No more specific tasks, schedule open focus / review
            blocks.append(
                TimeBlock(
                    start_str=_mins_to_str(curr),
                    end_str=_mins_to_str(curr + f_dur),
                    block_type="FOCUS",
                    task_title="🎯 จัดการงานย่อยและวางแผนล่วงหน้า / Open Focus & Deep Work",
                    is_break=False,
                    duration_mins=f_dur,
                )
            )

        total_focus += f_dur
        curr += f_dur

        # Ergonomic Break Block (if time remains before end of day)
        if curr < end_total_mins:
            b_dur = min(break_mins, end_total_mins - curr)
            # If entering lunch, skip normal short break
            if not lunch_scheduled and curr >= lunch_start:
                continue

            blocks.append(
                TimeBlock(
                    start_str=_mins_to_str(curr),
                    end_str=_mins_to_str(curr + b_dur),
                    block_type="BREAK",
                    task_title="☕ พักสายตา & ยืดเหยียด / 15m Ergonomic Break",
                    is_break=True,
                    duration_mins=b_dur,
                )
            )
            total_break += b_dur
            curr += b_dur

    return DayPlanResult(
        user_id=user_id,
        work_date=work_date_str,
        start_time=_mins_to_str(start_total_mins),
        end_time=_mins_to_str(end_total_mins),
        blocks=blocks,
        total_focus_minutes=total_focus,
        total_break_minutes=total_break,
        tasks_count=min(task_idx, num_tasks),
        first_task_id=first_task_id,
        first_task_title=first_task_title,
    )

