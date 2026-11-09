"""
day_planner package — Automated Daily Time-Blocker & Smart Schedule Optimizer (Gen 5.0).
"""
from day_planner.optimizer import (
    DayPlanResult,
    TimeBlock,
    optimize_day_schedule,
)
from day_planner.views import DayPlanActionView, build_day_plan_embed

__all__ = [
    "DayPlanResult",
    "TimeBlock",
    "optimize_day_schedule",
    "DayPlanActionView",
    "build_day_plan_embed",
]

