"""
Sprint Burndown Chart, Cumulative Flow Diagram (CFD), and Agile Velocity Chart.
Pure Python Pillow (PIL) in-memory PNG renderers.
"""
from __future__ import annotations

import io
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont


# ─────────────────────────────────────────────────────────────────────────────
# 1. Sprint Burndown Chart
# ─────────────────────────────────────────────────────────────────────────────

def render_burndown_chart(
    sprint_name: str,
    total_points: float,
    ideal_burn: Sequence[float],
    actual_burn: Sequence[float],
    day_labels: Sequence[str],
) -> io.BytesIO:
    """
    Renders a high-resolution Sprint Burndown Chart into an in-memory PNG buffer.

    Args:
        sprint_name: Name of the sprint.
        total_points: Initial committed story points / scope.
        ideal_burn: Ideal points trajectory down to 0.
        actual_burn: Actual remaining points recorded per day.
        day_labels: Day labels for X axis (e.g. ['Day 1', 'Day 2', ...]).
    """
    width = 850
    height = 460

    # Palette
    bg_color = (30, 31, 34)          # #1E1F22
    card_bg = (43, 45, 49)           # #2B2D31
    text_primary = (242, 243, 245)   # #F2F3F5
    text_secondary = (148, 155, 164) # #949BA4
    grid_color = (53, 55, 60)        # #35373C
    ideal_color = (148, 155, 164)    # #949BA4 (Grey dashed/dotted)
    actual_color = (87, 242, 135)    # #57F287 (Mint Green)
    node_color = (255, 255, 255)

    img = Image.new("RGBA", (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    # Header Card
    draw.rectangle([(16, 12), (width - 16, 70)], fill=card_bg)
    draw.text((30, 20), f"📉 SPRINT BURNDOWN CHART — {sprint_name.upper()}", fill=text_primary, font=font)

    current_actual = actual_burn[-1] if actual_burn else total_points
    burnt_points = max(0.0, total_points - current_actual)
    header_info = (
        f"Total Scope: {total_points:.1f} pts · "
        f"Burnt: {burnt_points:.1f} pts · "
        f"Remaining: {current_actual:.1f} pts"
    )
    draw.text((30, 42), header_info, fill=text_secondary, font=font)

    # Plot Bounds
    plot_left = 65
    plot_right = width - 40
    plot_top = 100
    plot_bottom = height - 60
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    # Y-axis scaling
    max_y = max(1.0, float(total_points) * 1.1)

    # Draw horizontal grid lines & Y labels (5 steps)
    for i in range(5):
        val = (max_y / 4.0) * i
        y_pos = int(plot_bottom - (val / max_y) * plot_height)
        draw.line([(plot_left, y_pos), (plot_right, y_pos)], fill=grid_color, width=1)
        draw.text((plot_left - 45, y_pos - 6), f"{val:4.1f}", fill=text_secondary, font=font)

    num_days = max(2, len(day_labels))
    x_step = plot_width / float(num_days - 1)

    # Draw X-axis labels
    for idx, d_lbl in enumerate(day_labels):
        x_pos = int(plot_left + (idx * x_step))
        draw.line([(x_pos, plot_bottom), (x_pos, plot_bottom + 4)], fill=grid_color, width=1)
        # Show label every 1 or 2 days depending on length
        if num_days <= 14 or idx % 2 == 0 or idx == num_days - 1:
            draw.text((x_pos - 12, plot_bottom + 8), str(d_lbl), fill=text_secondary, font=font)

    # 1. Draw Ideal Burn Line (Dashed)
    ideal_coords = []
    for idx, pt in enumerate(ideal_burn):
        x = int(plot_left + (idx * x_step))
        y = int(plot_bottom - (max(0.0, pt) / max_y) * plot_height)
        ideal_coords.append((x, y))

    for i in range(len(ideal_coords) - 1):
        x1, y1 = ideal_coords[i]
        x2, y2 = ideal_coords[i + 1]
        draw.line([(x1, y1), (x2, y2)], fill=ideal_color, width=2)

    # 2. Draw Actual Burn Line
    actual_coords = []
    for idx, pt in enumerate(actual_burn):
        x = int(plot_left + (idx * x_step))
        y = int(plot_bottom - (max(0.0, pt) / max_y) * plot_height)
        actual_coords.append((x, y))

    if len(actual_coords) >= 2:
        for i in range(len(actual_coords) - 1):
            draw.line([actual_coords[i], actual_coords[i + 1]], fill=actual_color, width=3)

    # Draw nodes on actual points
    for x, y in actual_coords:
        draw.ellipse([(x - 4, y - 4), (x + 4, y + 4)], fill=actual_color, outline=node_color, width=1)

    # Legend
    legend_y = height - 25
    draw.line([(width - 280, legend_y + 4), (width - 250, legend_y + 4)], fill=ideal_color, width=2)
    draw.text((width - 240, legend_y), "Ideal Burn", fill=text_secondary, font=font)

    draw.line([(width - 150, legend_y + 4), (width - 120, legend_y + 4)], fill=actual_color, width=3)
    draw.ellipse([(width - 137, legend_y + 1), (width - 133, legend_y + 5)], fill=actual_color, outline=node_color)
    draw.text((width - 110, legend_y), "Actual Burn", fill=text_primary, font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────────────────
# 2. Cumulative Flow Diagram (CFD Stacked Area Chart)
# ─────────────────────────────────────────────────────────────────────────────

def render_cfd_chart(
    title: str,
    dates: Sequence[str],
    pending_series: Sequence[int],
    in_progress_series: Sequence[int],
    completed_series: Sequence[int],
) -> io.BytesIO:
    """
    Renders a Cumulative Flow Diagram (CFD) stacked area chart.
    Layers:
      - Bottom: Completed (Mint Green)
      - Middle: In Progress (Blurple)
      - Top: Pending (Amber / Yellow)
    """
    width = 850
    height = 460

    bg_color = (30, 31, 34)          # #1E1F22
    card_bg = (43, 45, 49)           # #2B2D31
    text_primary = (242, 243, 245)   # #F2F3F5
    text_secondary = (148, 155, 164) # #949BA4
    grid_color = (53, 55, 60)        # #35373C

    color_completed = (87, 242, 135, 230)    # Mint Green
    color_in_prog = (88, 101, 242, 230)      # Blurple
    color_pending = (254, 231, 92, 230)      # Amber

    img = Image.new("RGBA", (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    # Header Card
    draw.rectangle([(16, 12), (width - 16, 70)], fill=card_bg)
    draw.text((30, 20), f"🌊 CUMULATIVE FLOW DIAGRAM (CFD) — {title.upper()}", fill=text_primary, font=font)
    total_curr = (completed_series[-1] if completed_series else 0) + \
                 (in_progress_series[-1] if in_progress_series else 0) + \
                 (pending_series[-1] if pending_series else 0)
    header_info = f"Total Tasks Tracked: {total_curr} · Work in Progress (WIP) Bottleneck Analytics"
    draw.text((30, 42), header_info, fill=text_secondary, font=font)

    # Plot bounds
    plot_left = 65
    plot_right = width - 40
    plot_top = 100
    plot_bottom = height - 60
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    # Calculate cumulative totals
    n = len(dates)
    cum_completed = list(completed_series)
    cum_in_prog = [c + p for c, p in zip(cum_completed, in_progress_series)]
    cum_pending = [ip + pend for ip, pend in zip(cum_in_prog, pending_series)]

    max_val = max(1, max(cum_pending) if cum_pending else 10)
    max_y = float(max_val) * 1.15

    # Grid & Y labels
    for i in range(5):
        val = int((max_y / 4.0) * i)
        y_pos = int(plot_bottom - (val / max_y) * plot_height)
        draw.line([(plot_left, y_pos), (plot_right, y_pos)], fill=grid_color, width=1)
        draw.text((plot_left - 35, y_pos - 6), f"{val:3d}", fill=text_secondary, font=font)

    x_step = plot_width / float(max(1, n - 1))

    # X-axis labels
    for idx, d_lbl in enumerate(dates):
        x_pos = int(plot_left + (idx * x_step))
        draw.line([(x_pos, plot_bottom), (x_pos, plot_bottom + 4)], fill=grid_color, width=1)
        if n <= 10 or idx % 2 == 0 or idx == n - 1:
            draw.text((x_pos - 12, plot_bottom + 8), str(d_lbl), fill=text_secondary, font=font)

    # Helper to calculate points polygon
    def get_points(series: Sequence[int]) -> list[tuple[int, int]]:
        return [
            (int(plot_left + idx * x_step), int(plot_bottom - (v / max_y) * plot_height))
            for idx, v in enumerate(series)
        ]

    pts_completed = get_points(cum_completed)
    pts_in_prog = get_points(cum_in_prog)
    pts_pending = get_points(cum_pending)

    # 1. Draw Pending layer (Top)
    poly_pending = [(plot_left, plot_bottom)] + pts_pending + [(plot_right, plot_bottom)]
    draw.polygon(poly_pending, fill=color_pending)

    # 2. Draw In Progress layer (Middle)
    poly_in_prog = [(plot_left, plot_bottom)] + pts_in_prog + [(plot_right, plot_bottom)]
    draw.polygon(poly_in_prog, fill=color_in_prog)

    # 3. Draw Completed layer (Bottom)
    poly_completed = [(plot_left, plot_bottom)] + pts_completed + [(plot_right, plot_bottom)]
    draw.polygon(poly_completed, fill=color_completed)

    # Legend
    legend_y = height - 25
    # Completed
    draw.rectangle([(width - 330, legend_y + 1), (width - 320, legend_y + 11)], fill=color_completed)
    draw.text((width - 312, legend_y), "Completed", fill=text_primary, font=font)
    # In Progress
    draw.rectangle([(width - 220, legend_y + 1), (width - 210, legend_y + 11)], fill=color_in_prog)
    draw.text((width - 202, legend_y), "In Progress", fill=text_primary, font=font)
    # Pending
    draw.rectangle([(width - 110, legend_y + 1), (width - 100, legend_y + 11)], fill=color_pending)
    draw.text((width - 92, legend_y), "Pending", fill=text_primary, font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────────────────────
# 3. Agile Velocity Comparison Chart
# ─────────────────────────────────────────────────────────────────────────────

def render_velocity_chart(
    project_name: str,
    sprint_names: Sequence[str],
    planned_points: Sequence[float],
    completed_points: Sequence[float],
) -> io.BytesIO:
    """
    Renders an Agile Velocity Comparison Chart (Planned vs Completed Story Points).
    Grouped bar chart per sprint with team average velocity line.
    """
    width = 850
    height = 460

    bg_color = (30, 31, 34)          # #1E1F22
    card_bg = (43, 45, 49)           # #2B2D31
    text_primary = (242, 243, 245)   # #F2F3F5
    text_secondary = (148, 155, 164) # #949BA4
    grid_color = (53, 55, 60)        # #35373C
    color_planned = (88, 101, 242)   # Blurple
    color_completed = (87, 242, 135) # Mint Green
    avg_color = (237, 66, 69)        # Red line for avg velocity

    img = Image.new("RGBA", (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    # Header Card
    draw.rectangle([(16, 12), (width - 16, 70)], fill=card_bg)
    draw.text((30, 20), f"⚡ AGILE VELOCITY COMPARISON — {project_name.upper()}", fill=text_primary, font=font)

    avg_vel = (sum(completed_points) / len(completed_points)) if completed_points else 0.0
    header_info = (
        f"Sprints Analyzed: {len(sprint_names)} · "
        f"Average Velocity: {avg_vel:.1f} pts/sprint · "
        f"Delivery Consistency"
    )
    draw.text((30, 42), header_info, fill=text_secondary, font=font)

    plot_left = 65
    plot_right = width - 40
    plot_top = 100
    plot_bottom = height - 60
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    all_vals = list(planned_points) + list(completed_points) + [avg_vel]
    max_val = max(1.0, max(all_vals) if all_vals else 10.0)
    max_y = max_val * 1.2

    # Grid & Y labels
    for i in range(5):
        val = (max_y / 4.0) * i
        y_pos = int(plot_bottom - (val / max_y) * plot_height)
        draw.line([(plot_left, y_pos), (plot_right, y_pos)], fill=grid_color, width=1)
        draw.text((plot_left - 45, y_pos - 6), f"{val:4.1f}", fill=text_secondary, font=font)

    num_sprints = max(1, len(sprint_names))
    slot_width = plot_width / float(num_sprints)
    bar_width = min(36.0, slot_width * 0.35)

    # Draw grouped bars for each sprint
    for idx, name in enumerate(sprint_names):
        center_x = plot_left + (idx * slot_width) + (slot_width / 2.0)
        p_pt = planned_points[idx] if idx < len(planned_points) else 0.0
        c_pt = completed_points[idx] if idx < len(completed_points) else 0.0

        p_height = (p_pt / max_y) * plot_height
        c_height = (c_pt / max_y) * plot_height

        # Planned bar (Left)
        p_x1 = int(center_x - bar_width - 2)
        p_y1 = int(plot_bottom - p_height)
        p_x2 = int(center_x - 2)
        draw.rectangle([(p_x1, p_y1), (p_x2, plot_bottom)], fill=color_planned)
        if p_pt > 0:
            draw.text((p_x1 + 2, max(plot_top + 2, p_y1 - 12)), f"{p_pt:.0f}", fill=text_secondary, font=font)

        # Completed bar (Right)
        c_x1 = int(center_x + 2)
        c_y1 = int(plot_bottom - c_height)
        c_x2 = int(center_x + bar_width + 2)
        draw.rectangle([(c_x1, c_y1), (c_x2, plot_bottom)], fill=color_completed)
        if c_pt > 0:
            draw.text((c_x1 + 2, max(plot_top + 2, c_y1 - 12)), f"{c_pt:.0f}", fill=color_completed, font=font)

        # X label (Sprint Name)
        lbl = name[:12]
        draw.text((int(center_x - len(lbl) * 3), plot_bottom + 8), lbl, fill=text_primary, font=font)

    # Average Velocity horizontal line
    avg_y = int(plot_bottom - (avg_vel / max_y) * plot_height)
    draw.line([(plot_left, avg_y), (plot_right, avg_y)], fill=avg_color, width=2)
    draw.text((plot_right - 110, avg_y - 14), f"Avg: {avg_vel:.1f} pts", fill=avg_color, font=font)

    # Legend
    legend_y = height - 25
    draw.rectangle([(width - 330, legend_y + 1), (width - 320, legend_y + 11)], fill=color_planned)
    draw.text((width - 312, legend_y), "Planned Points", fill=text_primary, font=font)

    draw.rectangle([(width - 190, legend_y + 1), (width - 180, legend_y + 11)], fill=color_completed)
    draw.text((width - 172, legend_y), "Completed Points", fill=text_primary, font=font)

    draw.line([(width - 60, legend_y + 6), (width - 45, legend_y + 6)], fill=avg_color, width=2)
    draw.text((width - 40, legend_y), "Avg", fill=avg_color, font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

