"""
Streak 365-Day Contribution Heatmap Renderer.
Generates a GitHub-style 52-week contribution grid using Pure Python Pillow (PIL).
Outputs directly to in-memory io.BytesIO PNG buffer.
"""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta, timezone
from typing import Mapping, Optional

from PIL import Image, ImageDraw, ImageFont


def _get_intensity_color(count: int) -> tuple[int, int, int]:
    """Returns RGB color for task completion count."""
    if count <= 0:
        return (46, 50, 56)       # #2E3238 (Dark empty cell)
    elif count <= 2:
        return (14, 68, 41)       # #0E4429 (L1 Dark Green)
    elif count <= 4:
        return (0, 109, 50)       # #006D32 (L2 Medium Green)
    elif count <= 6:
        return (38, 166, 65)      # #26A641 (L3 Light Green)
    return (57, 211, 83)          # #39D353 (L4 Vibrant Green)


def render_streak_heatmap(
    completion_counts: Mapping[str, int],
    title: str = "365-Day Contribution Heatmap",
    username: str = "User",
    streak_days: int = 0,
    longest_streak: int = 0,
    end_date: Optional[date] = None,
) -> io.BytesIO:
    """
    Renders 52 weeks (364 days) contribution heatmap into an in-memory BytesIO PNG.

    Args:
        completion_counts: Mapping of 'YYYY-MM-DD' strings to completion counts.
        title: Chart title.
        username: Target user display name.
        streak_days: Current active streak in days.
        longest_streak: Longest recorded streak in days.
        end_date: Anchor date (default: today UTC).
    """
    if end_date is None:
        end_date = datetime.now(timezone.utc).date()

    # Total 52 weeks = 364 days
    # Align end_date so that the grid completes the current week through Sunday
    days_since_sunday = (end_date.weekday() + 1) % 7
    grid_end = end_date + timedelta(days=(6 - end_date.weekday()))
    grid_start = grid_end - timedelta(weeks=52) + timedelta(days=1)

    box_size = 14
    box_gap = 3
    step = box_size + box_gap

    left_margin = 46
    top_margin = 85
    footer_margin = 45

    grid_width = 52 * step
    grid_height = 7 * step

    canvas_width = left_margin + grid_width + 30
    canvas_height = top_margin + grid_height + footer_margin

    # Discord Dark Palette
    bg_color = (30, 31, 34)          # #1E1F22
    card_bg = (43, 45, 49)           # #2B2D31
    text_primary = (242, 243, 245)   # #F2F3F5
    text_secondary = (148, 155, 164) # #949BA4

    img = Image.new("RGBA", (canvas_width, canvas_height), bg_color)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    # 1. Header Card
    draw.rectangle([(16, 12), (canvas_width - 16, 68)], fill=card_bg)
    draw.text((30, 22), f"🔥 {title.upper()} — {username}", fill=text_primary, font=font)

    total_tasks = sum(completion_counts.values()) if completion_counts else 0
    stats_str = (
        f"Total Completed: {total_tasks:,} tasks · "
        f"Current Streak: {streak_days} days · "
        f"Longest Streak: {longest_streak} days"
    )
    draw.text((30, 44), stats_str, fill=text_secondary, font=font)

    # 2. Day Labels (Mon, Wed, Fri)
    day_labels = {0: "Mon", 2: "Wed", 4: "Fri"}
    for day_idx, label in day_labels.items():
        y = top_margin + (day_idx * step) + 2
        draw.text((12, y), label, fill=text_secondary, font=font)

    # 3. Draw 52-week x 7-day Grid & Month Labels
    curr = grid_start
    last_month = None

    for week in range(52):
        col_x = left_margin + (week * step)

        # Draw month label if month changes
        if curr.month != last_month and curr.day <= 7:
            month_name = curr.strftime("%b")
            draw.text((col_x, top_margin - 16), month_name, fill=text_secondary, font=font)
            last_month = curr.month

        for row in range(7):
            row_y = top_margin + (row * step)
            date_str = curr.isoformat()
            count = completion_counts.get(date_str, 0)
            cell_color = _get_intensity_color(count)

            # Draw cell box with 1px rounded feel
            draw.rectangle(
                [(col_x, row_y), (col_x + box_size - 1, row_y + box_size - 1)],
                fill=cell_color,
            )
            curr += timedelta(days=1)

    # 4. Legend at bottom right
    legend_y = canvas_height - 30
    legend_x = canvas_width - 210
    draw.text((legend_x - 36, legend_y + 1), "Less", fill=text_secondary, font=font)

    sample_counts = [0, 2, 4, 6, 8]
    for idx, sc in enumerate(sample_counts):
        lx = legend_x + (idx * (box_size + box_gap))
        draw.rectangle([(lx, legend_y), (lx + box_size - 1, legend_y + box_size - 1)], fill=_get_intensity_color(sc))

    draw.text((legend_x + len(sample_counts) * (box_size + box_gap) + 8, legend_y + 1), "More", fill=text_secondary, font=font)

    # Export to BytesIO
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

