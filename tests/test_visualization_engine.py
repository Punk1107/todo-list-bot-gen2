"""
Unit tests for Gen 5.0 Pillar 6: Pure In-Bot Visual Graphic & Data Visualization.
Covers:
  - Feature 24: Self-Hosted In-Memory Image Generator (365-Day Heatmap & Burndown Chart)
  - Feature 25: Cumulative Flow Diagrams (CFD) & Agile Velocity Charts
  - Feature 26: Unicode Sparklines & Braille Pattern Visualizations
  - Service query calculations and data series formatting
"""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from visualization import (
    render_block_sparkline,
    render_braille_sparkline,
    render_braille_wave,
    render_progress_bar,
    render_streak_heatmap,
    render_burndown_chart,
    render_cfd_chart,
    render_velocity_chart,
)
from visualization import service as viz_service

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Feature 26: Unicode Sparklines & Braille Patterns Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_render_block_sparkline():
    # Empty
    assert render_block_sparkline([]) == ""

    # All zeros
    assert render_block_sparkline([0, 0, 0]) == "   "

    # All identical non-zero
    assert render_block_sparkline([5, 5, 5]) == "▄▄▄"

    # Ascending sequence
    spark = render_block_sparkline([0, 1, 2, 3, 4, 5, 6, 7])
    assert len(spark) == 8
    assert spark[0] == " "
    assert spark[-1] == "█"


def test_render_braille_sparkline():
    assert render_braille_sparkline([]) == ""
    assert render_braille_sparkline([0, 0, 0]) == "⠀⠀⠀"
    assert render_braille_sparkline([10, 10, 10]) == "⣤⣤⣤"

    spark = render_braille_sparkline([0, 1, 2, 3])
    assert len(spark) == 4
    assert spark[0] == "⣀"
    assert spark[-1] == "⣿"


def test_render_braille_wave():
    assert render_braille_wave(0) == ""
    wave = render_braille_wave(10)
    assert len(wave) == 10
    assert wave == "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def test_render_progress_bar():
    assert render_progress_bar(0.0) == "[░░░░░░░░░░] 0.0%"
    assert render_progress_bar(50.0) == "[█████░░░░░] 50.0%"
    assert render_progress_bar(100.0) == "[██████████] 100.0%"
    assert render_progress_bar(120.0) == "[██████████] 100.0%"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Feature 24: Heatmap & Burndown In-Memory PNG Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_render_streak_heatmap():
    today = date(2026, 11, 9)
    sample_counts = {
        (today - timedelta(days=1)).isoformat(): 3,
        (today - timedelta(days=5)).isoformat(): 7,
        (today - timedelta(days=30)).isoformat(): 2,
    }

    buf = render_streak_heatmap(
        completion_counts=sample_counts,
        title="365-Day Test Heatmap",
        username="Tester",
        streak_days=14,
        longest_streak=25,
        end_date=today,
    )

    assert isinstance(buf, io.BytesIO)
    data = buf.getvalue()
    assert len(data) > 1000
    assert data[:8] == PNG_SIGNATURE


def test_render_burndown_chart():
    ideal = [100.0, 80.0, 60.0, 40.0, 20.0, 0.0]
    actual = [100.0, 85.0, 55.0, 30.0]
    days = ["D1", "D2", "D3", "D4", "D5", "D6"]

    buf = render_burndown_chart(
        sprint_name="Sprint 10",
        total_points=100.0,
        ideal_burn=ideal,
        actual_burn=actual,
        day_labels=days,
    )

    assert isinstance(buf, io.BytesIO)
    data = buf.getvalue()
    assert len(data) > 1000
    assert data[:8] == PNG_SIGNATURE


# ─────────────────────────────────────────────────────────────────────────────
# 3. Feature 25: CFD & Velocity Chart Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_render_cfd_chart():
    dates = ["Nov 01", "Nov 02", "Nov 03", "Nov 04"]
    completed = [2, 4, 7, 10]
    in_prog = [3, 4, 3, 2]
    pending = [8, 6, 4, 2]

    buf = render_cfd_chart(
        title="Sprint 42",
        dates=dates,
        pending_series=pending,
        in_progress_series=in_prog,
        completed_series=completed,
    )

    assert isinstance(buf, io.BytesIO)
    data = buf.getvalue()
    assert len(data) > 1000
    assert data[:8] == PNG_SIGNATURE


def test_render_velocity_chart():
    sprints = ["Sprint 1", "Sprint 2", "Sprint 3", "Sprint 4"]
    planned = [20.0, 25.0, 30.0, 30.0]
    completed = [18.0, 22.0, 28.0, 32.0]

    buf = render_velocity_chart(
        project_name="Core Engine",
        sprint_names=sprints,
        planned_points=planned,
        completed_points=completed,
    )

    assert isinstance(buf, io.BytesIO)
    data = buf.getvalue()
    assert len(data) > 1000
    assert data[:8] == PNG_SIGNATURE


# ─────────────────────────────────────────────────────────────────────────────
# 4. Service Layer Query & Series Computation Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_user_365_day_completions():
    fake_rows = [
        {"cdate": "2026-11-08", "cnt": 4},
        {"cdate": "2026-11-09", "cnt": 6},
    ]
    with patch("core.database.db.fetchall", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = fake_rows
        res = await viz_service.get_user_365_day_completions("U123")
        assert res == {"2026-11-08": 4, "2026-11-09": 6}


@pytest.mark.asyncio
async def test_get_user_7day_activity():
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    fake_rows = [
        {"cdate": yesterday.isoformat(), "cnt": 5},
        {"cdate": today.isoformat(), "cnt": 3},
    ]
    with patch("core.database.db.fetchall", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = fake_rows
        activity = await viz_service.get_user_7day_activity("U123")
        assert len(activity) == 7
        assert activity[-1] == 3
        assert activity[-2] == 5


@pytest.mark.asyncio
async def test_get_sprint_burndown_data():
    now_utc = datetime.now(timezone.utc)
    fake_sprint = {
        "sprint_id": 5,
        "name": "Sprint 5",
        "total_points": 50.0,
        "completed_points": 20.0,
        "start_date": now_utc - timedelta(days=4),
        "end_date": now_utc + timedelta(days=5),
        "status": "Active",
    }
    fake_tasks = [
        {"task_id": 1, "status": "Completed", "story_points": 20.0},
        {"task_id": 2, "status": "In_Progress", "story_points": 30.0},
    ]
    with patch("core.database.db.fetchone", new_callable=AsyncMock) as mock_one, \
         patch("core.database.db.fetchall", new_callable=AsyncMock) as mock_all:
        mock_one.return_value = fake_sprint
        mock_all.return_value = fake_tasks

        data = await viz_service.get_sprint_burndown_data(5)
        assert data is not None
        assert data["sprint_name"] == "Sprint 5"
        assert data["total_points"] == 50.0
        assert len(data["ideal_burn"]) == len(data["day_labels"])
        assert data["ideal_burn"][0] == 50.0
        assert data["ideal_burn"][-1] == 0.0


@pytest.mark.asyncio
async def test_get_project_velocity_history():
    fake_proj = {"name": "Phoenix Project"}
    fake_sprints = [
        {"sprint_id": 1, "name": "Sprint 1", "total_points": 20.0, "completed_points": 18.0},
        {"sprint_id": 2, "name": "Sprint 2", "total_points": 25.0, "completed_points": 25.0},
    ]
    with patch("core.database.db.fetchone", new_callable=AsyncMock) as mock_one, \
         patch("core.database.db.fetchall", new_callable=AsyncMock) as mock_all:
        mock_one.return_value = fake_proj
        mock_all.return_value = fake_sprints

        vel = await viz_service.get_project_velocity_history(10)
        assert vel["project_name"] == "Phoenix Project"
        assert vel["sprint_names"] == ["Sprint 1", "Sprint 2"]
        assert vel["planned_points"] == [20.0, 25.0]
        assert vel["completed_points"] == [18.0, 25.0]

