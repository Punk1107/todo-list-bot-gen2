"""
Unicode Sparklines & Braille Pattern Visualizations.
Provides lightweight, zero-latency text-based data visualizations for Discord embeds:
- Unicode Block Elements:  ▂▃▄▅▆▇█
- Braille Patterns: ⣀⣤⣶⣿ and ⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏
"""
from __future__ import annotations

from typing import Sequence

BLOCK_ELEMENTS: tuple[str, ...] = (" ", "▂", "▃", "▄", "▅", "▆", "▇", "█")
BRAILLE_LEVELS: tuple[str, ...] = ("⣀", "⣤", "⣶", "⣿")
BRAILLE_WAVE_PINS: tuple[str, ...] = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


def render_block_sparkline(values: Sequence[float | int]) -> str:
    """
    Renders a sequence of numerical values into a Unicode block sparkline ( ▂▃▄▅▆▇█).
    Example:
        [1, 2, 4, 8, 16, 8, 4] -> "  ▂▄█▄▂"
    """
    if not values:
        return ""

    floats = [float(v) for v in values]
    min_v = min(floats)
    max_v = max(floats)

    # If all values are identical or all 0
    if max_v == min_v:
        if max_v == 0.0:
            return BLOCK_ELEMENTS[0] * len(values)
        return BLOCK_ELEMENTS[3] * len(values)  # Middle bar '▄'

    span = max_v - min_v
    num_levels = len(BLOCK_ELEMENTS)
    result = []
    for val in floats:
        # Scale between 0 and num_levels - 1
        idx = int(((val - min_v) / span) * (num_levels - 1))
        idx = max(0, min(num_levels - 1, idx))
        result.append(BLOCK_ELEMENTS[idx])

    return "".join(result)


def render_braille_sparkline(values: Sequence[float | int]) -> str:
    """
    Renders numerical values using 4-level vertical Braille height characters (⣀⣤⣶⣿).
    """
    if not values:
        return ""

    floats = [float(v) for v in values]
    min_v = min(floats)
    max_v = max(floats)

    if max_v == min_v:
        if max_v == 0.0:
            return "⠀" * len(values)
        return BRAILLE_LEVELS[1] * len(values)

    span = max_v - min_v
    num_levels = len(BRAILLE_LEVELS)
    result = []
    for val in floats:
        idx = int(((val - min_v) / span) * (num_levels - 1))
        idx = max(0, min(num_levels - 1, idx))
        result.append(BRAILLE_LEVELS[idx])

    return "".join(result)


def render_braille_wave(count: int = 10, intensity: float = 1.0) -> str:
    """
    Generates a continuous Braille focus wave pattern (⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏)
    representing focus flow and activity continuity.
    """
    if count <= 0:
        return ""
    pins_len = len(BRAILLE_WAVE_PINS)
    return "".join(BRAILLE_WAVE_PINS[int(i * intensity) % pins_len] for i in range(count))


def render_progress_bar(
    pct: float,
    width: int = 10,
    fill_char: str = "█",
    empty_char: str = "░",
) -> str:
    """Renders a clean text progress bar with percentage."""
    clamped = max(0.0, min(100.0, float(pct)))
    filled_len = int(round((clamped / 100.0) * width))
    empty_len = width - filled_len
    bar = fill_char * filled_len + empty_char * empty_len
    return f"[{bar}] {clamped:.1f}%"

