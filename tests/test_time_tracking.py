"""
tests/test_time_tracking.py — Comprehensive Unit Tests for Pillar 4:
Time Tracking, Capacity & Estimation Engine (Gen 5.0).
"""
from __future__ import annotations

from datetime import datetime, timezone

from time_tracking.models import (
    ActiveTimer,
    CapacityMetric,
    EstimationMetric,
    ProjectBudgetMetric,
    TimeLogEntry,
    TimesheetSummary,
)
from time_tracking.service import export_timesheet_csv


def test_active_timer_elapsed_calculations():
    """Verify ActiveTimer computes elapsed seconds and fractional hours accurately."""
    start_time = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc)
    current_time = datetime(2026, 11, 9, 11, 30, 0, tzinfo=timezone.utc)  # 1.5 hours later

    timer = ActiveTimer(
        user_id="user_123",
        task_id=101,
        started_at=start_time,
        note="Refactoring billing logic",
        task_title="Stripe Integration",
    )

    elapsed_s = timer.elapsed_seconds(now=current_time)
    assert elapsed_s == 5400.0  # 90 mins * 60 s

    elapsed_h = timer.elapsed_hours(now=current_time)
    assert elapsed_h == 1.5


def test_estimation_metric_classification():
    """Verify estimation variance and accuracy % formulas and categorization."""
    # 1. Accurate (within +-15%)
    # Est 10h, Act 11h -> +10% variance, 90% accuracy
    m_acc = EstimationMetric.calculate(
        task_id=1,
        task_name="Task A",
        estimated_hours=10.0,
        actual_hours=11.0,
    )
    assert m_acc.variance_pct == 10.0
    assert m_acc.accuracy_pct == 90.0
    assert m_acc.category == "accurate"

    # 2. Underestimated (Took longer than expected: > +15%)
    # Est 10h, Act 16h -> +60% variance, 40% accuracy
    m_under = EstimationMetric.calculate(
        task_id=2,
        task_name="Task B",
        estimated_hours=10.0,
        actual_hours=16.0,
    )
    assert m_under.variance_pct == 60.0
    assert m_under.accuracy_pct == 40.0
    assert m_under.category == "underestimated"

    # 3. Overestimated (Finished quicker than expected: < -15%)
    # Est 10h, Act 5h -> -50% variance, 50% accuracy
    m_over = EstimationMetric.calculate(
        task_id=3,
        task_name="Task C",
        estimated_hours=10.0,
        actual_hours=5.0,
    )
    assert m_over.variance_pct == -50.0
    assert m_over.accuracy_pct == 50.0
    assert m_over.category == "overestimated"

    # 4. Zero / Guard check
    m_zero = EstimationMetric.calculate(
        task_id=4,
        task_name="Task D",
        estimated_hours=0.0,
        actual_hours=0.0,
    )
    assert m_zero.accuracy_pct == 100.0
    assert m_zero.category == "accurate"


def test_capacity_metric_and_burnout_shield():
    """Verify workload capacity percentage and Burnout Shield warning condition."""
    # Safe workload (30h allocated out of 40h capacity = 75%)
    safe = CapacityMetric.compute(
        user_id="user_safe",
        weekly_capacity_hours=40.0,
        assigned_estimated_hours=30.0,
        active_task_count=3,
    )
    assert safe.workload_pct == 75.0
    assert safe.is_overloaded is False

    # Overloaded / Burnout Risk (46h allocated out of 40h capacity = 115%)
    overloaded = CapacityMetric.compute(
        user_id="user_burnout",
        weekly_capacity_hours=40.0,
        assigned_estimated_hours=46.0,
        active_task_count=6,
    )
    assert overloaded.workload_pct == 115.0
    assert overloaded.is_overloaded is True


def test_project_budget_threshold_alerts():
    """Verify budget consumption calculation and 80%/100% threshold triggers."""
    # Under limit (50%)
    b_under = ProjectBudgetMetric(
        project_id=1,
        project_name="Web Redesign",
        budget=10000.0,
        currency="THB",
        spent_amount=5000.0,
        spent_pct=50.0,
        total_billable_hours=10.0,
        total_non_billable_hours=5.0,
        is_near_limit=False,
        is_over_budget=False,
    )
    assert not b_under.is_near_limit
    assert not b_under.is_over_budget

    # Near limit (85%)
    b_near = ProjectBudgetMetric(
        project_id=2,
        project_name="Mobile App",
        budget=10000.0,
        currency="THB",
        spent_amount=8500.0,
        spent_pct=85.0,
        total_billable_hours=17.0,
        total_non_billable_hours=2.0,
        is_near_limit=True,
        is_over_budget=False,
    )
    assert b_near.is_near_limit is True
    assert b_near.is_over_budget is False

    # Over budget (110%)
    b_over = ProjectBudgetMetric(
        project_id=3,
        project_name="Backend API",
        budget=10000.0,
        currency="THB",
        spent_amount=11000.0,
        spent_pct=110.0,
        total_billable_hours=22.0,
        total_non_billable_hours=1.0,
        is_near_limit=False,
        is_over_budget=True,
    )
    assert b_over.is_over_budget is True


def test_export_timesheet_csv_format():
    """Verify CSV timesheet generator produces compliant header and data rows."""
    now = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
    entries = [
        TimeLogEntry(
            log_id=1,
            task_id=101,
            user_id="user_alice",
            hours_spent=2.5,
            is_billable=True,
            logged_at=now,
            note="Database optimization",
            task_title="PostgreSQL tuning",
            project_id=5,
            project_name="Core Services",
        ),
        TimeLogEntry(
            log_id=2,
            task_id=102,
            user_id="user_alice",
            hours_spent=1.0,
            is_billable=False,
            logged_at=now,
            note="Team sync meeting",
            task_title="Weekly standup",
            project_id=None,
            project_name=None,
        ),
    ]

    summary = TimesheetSummary(
        user_id="user_alice",
        period="week",
        total_hours=3.5,
        billable_hours=2.5,
        non_billable_hours=1.0,
        entries=entries,
        project_hours={"Core Services": 2.5, "Personal / No Project": 1.0},
    )

    csv_output = export_timesheet_csv(summary)
    lines = csv_output.strip().split("\n")
    assert len(lines) == 3  # Header + 2 rows

    assert "Log ID,Task ID,Task Title,Project,Hours,Billable,Logged At (UTC),Note" in lines[0]
    assert "1,101,PostgreSQL tuning,Core Services,2.50,Yes,2026-11-09 12:00:00,Database optimization" in lines[1]
    assert "2,102,Weekly standup,Personal,1.00,No,2026-11-09 12:00:00,Team sync meeting" in lines[2]
