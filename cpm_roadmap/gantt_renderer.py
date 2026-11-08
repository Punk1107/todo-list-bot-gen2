"""
cpm_roadmap/gantt_renderer.py — In-Discord Visual Gantt Chart Generator.

Provides 2 rendering modes:
  1. ASCII/Unicode Gantt Block View: Formatted for Discord Embed Codeblock.
  2. High-Res In-Memory PNG Gantt Chart: Rendered with Pure Python Pillow (PIL),
     including task bars, critical path highlights, and dependency connector arrows.
"""
from __future__ import annotations

import io
import math
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

from cpm_roadmap.models import CPMGraphResult, CPMNode, GanttTask


# ─────────────────────────────────────────────────────────────────────────────
# 1. ASCII / Unicode Gantt Block View
# ─────────────────────────────────────────────────────────────────────────────

def render_ascii_gantt(cpm_result: CPMGraphResult, max_days: int = 24) -> str:
    """
    Render a clean ASCII/Unicode Gantt chart formatted for Discord embed codeblock.
    """
    nodes = list(cpm_result.nodes.values())
    if not nodes:
        return "No tasks found in project."

    total_days = max(1.0, cpm_result.total_duration_days)
    scale = max(1.0, total_days / float(max_days))

    lines: List[str] = []
    # Timeline header
    header_days = [f"D{int(i * scale) + 1}" for i in range(min(max_days, int(total_days)) + 1)]
    lines.append(f"{'Task Name':<20} | Timeline (1 block ≈ {scale:.1f}d) | Status")
    lines.append("-" * 65)

    for node in nodes[:15]:  # Limit to 15 tasks for Discord embed height
        start_block = int((node.early_start / 8.0) / scale)
        dur_blocks = max(1, int(node.duration_days / scale))
        slack_blocks = max(0, int((node.slack / 8.0) / scale))

        bar = " " * start_block
        if node.is_critical:
            bar += "█" * dur_blocks  # Critical path
        else:
            bar += "■" * dur_blocks  # Normal task

        if slack_blocks > 0:
            bar += "░" * min(5, slack_blocks)  # Slack time

        crit_badge = "🚨" if node.is_critical else "  "
        task_name = (node.task_name[:16] + "..") if len(node.task_name) > 18 else node.task_name
        status_code = "Done" if node.status == "Completed" else ("Prog" if node.status == "In_Progress" else "Pend")

        lines.append(f"{crit_badge}{task_name:<18} | {bar:<25} | {status_code}")

    if len(nodes) > 15:
        lines.append(f"... +{len(nodes) - 15} more tasks (use PNG mode for full chart)")

    lines.append("-" * 65)
    lines.append("Legend: █ Critical Path  ■ Normal  ░ Slack Time  🚨 At Risk")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 2. High-Res In-Memory PNG Gantt Chart (Pure Pillow)
# ─────────────────────────────────────────────────────────────────────────────

def render_png_gantt(
    cpm_result: CPMGraphResult,
    project_name: str = "Project Gantt Chart",
) -> io.BytesIO:
    """
    Draw a high-resolution Gantt chart with dependency lines and critical path
    highlighting using Pure Python Pillow (PIL). Outputs to in-memory BytesIO buffer.
    """
    nodes = list(cpm_result.nodes.values())
    node_count = max(1, len(nodes))
    total_days = max(1.0, cpm_result.total_duration_days)

    # Canvas dimensions
    width = 1100
    row_height = 42
    header_height = 110
    footer_height = 80
    height = header_height + (node_count * row_height) + footer_height

    # Colors (Discord Dark Theme Palette)
    bg_color = (30, 31, 34)          # #1E1F22
    card_bg = (43, 45, 49)           # #2B2D31
    text_primary = (242, 243, 245)   # #F2F3F5
    text_secondary = (148, 155, 164) # #949BA4
    grid_color = (53, 55, 60)        # #35373C
    critical_color = (237, 66, 69)   # #ED4245 Crimson Red
    progress_color = (88, 101, 242)  # #5865F2 Blurple
    completed_color = (87, 242, 135) # #57F287 Mint Green
    pending_color = (114, 118, 125)  # #72767D Grey
    slack_color = (78, 80, 88)       # #4E5058
    arrow_color = (254, 231, 92)     # #FEE75C Amber

    # Create image canvas
    img = Image.new("RGBA", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # Load default bitmap font
    font = ImageFont.load_default()

    # Draw Header Card
    draw.rectangle([(20, 20), (width - 20, 90)], fill=card_bg)
    draw.text((40, 32), f"📊 GANTT CHART: {project_name.upper()}", fill=text_primary, font=font)
    crit_count = len(cpm_result.critical_path)
    crit_info = f"Critical Path: {crit_count} Tasks · Total Duration: {cpm_result.total_duration_days} Days"
    draw.text((40, 58), crit_info, fill=critical_color if crit_count > 0 else text_secondary, font=font)

    # Chart Layout Grid
    label_width = 240
    chart_start_x = 260
    chart_end_x = width - 40
    chart_width = chart_end_x - chart_start_x

    # Number of day divisions on time axis
    num_ticks = min(15, max(5, int(total_days)))
    day_step = total_days / float(num_ticks)

    # Draw Time Axis Labels
    for i in range(num_ticks + 1):
        day_val = i * day_step
        x = chart_start_x + int((day_val / total_days) * chart_width)
        draw.line([(x, 95), (x, height - footer_height)], fill=grid_color, width=1)
        draw.text((x - 10, 98), f"D{int(day_val) + 1}", fill=text_secondary, font=font)

    # Store center-right and center-left positions of bars for drawing dependency arrows
    bar_endpoints: dict[int, tuple[int, int]] = {}
    bar_startpoints: dict[int, tuple[int, int]] = {}

    # Draw Task Rows
    curr_y = header_height + 15
    for idx, node in enumerate(nodes):
        # Row alternate highlight
        if idx % 2 == 1:
            draw.rectangle([(20, curr_y - 4), (width - 20, curr_y + row_height - 6)], fill=(36, 38, 42))

        # Task Name
        badge = "[CRIT] " if node.is_critical else ""
        name_str = f"{badge}#{node.task_id} {node.task_name}"
        if len(name_str) > 28:
            name_str = name_str[:26] + ".."
        name_color = critical_color if node.is_critical else text_primary
        draw.text((30, curr_y + 8), name_str, fill=name_color, font=font)

        # Bar Coordinates
        start_day = node.early_start / 8.0
        dur_day = node.duration_days
        end_day = start_day + dur_day
        slack_day = node.slack / 8.0

        bar_x1 = chart_start_x + int((start_day / total_days) * chart_width)
        bar_x2 = max(bar_x1 + 8, chart_start_x + int((end_day / total_days) * chart_width))
        bar_y1 = curr_y + 6
        bar_y2 = curr_y + row_height - 14

        # Bar Color Selection
        if node.status == "Completed":
            fill_col = completed_color
        elif node.is_critical:
            fill_col = critical_color
        elif node.status == "In_Progress":
            fill_col = progress_color
        else:
            fill_col = pending_color

        # Draw Slack Bar (if any)
        if slack_day > 0.1 and not node.is_critical:
            slack_x2 = max(bar_x2, chart_start_x + int(((end_day + slack_day) / total_days) * chart_width))
            draw.rectangle([(bar_x2, bar_y1 + 4), (slack_x2, bar_y2 - 4)], fill=slack_color)

        # Draw Task Bar
        draw.rectangle([(bar_x1, bar_y1), (bar_x2, bar_y2)], fill=fill_col)

        # Save coordinates for dependency arrows
        bar_startpoints[node.task_id] = (bar_x1, (bar_y1 + bar_y2) // 2)
        bar_endpoints[node.task_id] = (bar_x2, (bar_y1 + bar_y2) // 2)

        curr_y += row_height

    # Draw Dependency Connector Lines & Arrows
    for node in nodes:
        for pred_id in node.predecessors:
            if pred_id in bar_endpoints and node.task_id in bar_startpoints:
                from_x, from_y = bar_endpoints[pred_id]
                to_x, to_y = bar_startpoints[node.task_id]

                # Draw stepped polyline: (from_x, from_y) -> (mid_x, from_y) -> (mid_x, to_y) -> (to_x, to_y)
                mid_x = from_x + 8
                draw.line([(from_x, from_y), (mid_x, from_y)], fill=arrow_color, width=2)
                draw.line([(mid_x, from_y), (mid_x, to_y)], fill=arrow_color, width=2)
                draw.line([(mid_x, to_y), (to_x, to_y)], fill=arrow_color, width=2)
                # Small arrowhead
                draw.polygon([(to_x, to_y), (to_x - 5, to_y - 3), (to_x - 5, to_y + 3)], fill=arrow_color)

    # Draw Legend Footer
    footer_y = height - footer_height + 20
    draw.rectangle([(20, footer_y - 8), (width - 20, height - 20)], fill=card_bg)

    # Legend markers
    draw.rectangle([(40, footer_y), (55, footer_y + 12)], fill=critical_color)
    draw.text((65, footer_y + 1), "Critical Path (Slack = 0)", fill=text_primary, font=font)

    draw.rectangle([(240, footer_y), (255, footer_y + 12)], fill=progress_color)
    draw.text((265, footer_y + 1), "In Progress", fill=text_primary, font=font)

    draw.rectangle([(380, footer_y), (395, footer_y + 12)], fill=completed_color)
    draw.text((405, footer_y + 1), "Completed", fill=text_primary, font=font)

    draw.rectangle([(510, footer_y), (525, footer_y + 12)], fill=slack_color)
    draw.text((535, footer_y + 1), "Float / Slack Time", fill=text_primary, font=font)

    draw.line([(680, footer_y + 6), (710, footer_y + 6)], fill=arrow_color, width=2)
    draw.text((720, footer_y + 1), "Task Dependency", fill=text_primary, font=font)

    # Save to buffer
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

