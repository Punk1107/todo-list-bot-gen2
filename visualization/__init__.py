"""
visualization package — Pure In-Bot Visual Graphic & Data Visualization Engine.
Features:
- Streak 365-Day Contribution Heatmap (Pillow in-memory PNG)
- Sprint Burndown Chart (Pillow in-memory PNG)
- Cumulative Flow Diagram (CFD Stacked Area Chart)
- Agile Velocity Comparison Chart (Planned vs Completed Bar Chart)
- Unicode Block Element Sparklines & Braille Focus Waves
"""
from __future__ import annotations

from visualization.sparklines import (
    render_block_sparkline,
    render_braille_sparkline,
    render_braille_wave,
    render_progress_bar,
)
from visualization.heatmap_renderer import render_streak_heatmap
from visualization.sprint_charts import (
    render_burndown_chart,
    render_cfd_chart,
    render_velocity_chart,
)

__all__ = [
    "render_block_sparkline",
    "render_braille_sparkline",
    "render_braille_wave",
    "render_progress_bar",
    "render_streak_heatmap",
    "render_burndown_chart",
    "render_cfd_chart",
    "render_velocity_chart",
]
