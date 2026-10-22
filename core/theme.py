"""
core/theme.py — Embed Theme Personalization Engine
Provides curated, aesthetic color themes for Discord embeds across the bot.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ThemeDefinition:
    key: str
    name: str
    emoji: str
    color_hex: str
    color_int: int
    description: str


THEMES: dict[str, ThemeDefinition] = {
    "default": ThemeDefinition(
        key="default",
        name="Discord Blurple",
        emoji="💙",
        color_hex="#5865F2",
        color_int=0x5865F2,
        description="Classic Discord blurple, balanced and clear",
    ),
    "cyberpunk": ThemeDefinition(
        key="cyberpunk",
        name="Cyberpunk Neon",
        emoji="💖",
        color_hex="#FF007F",
        color_int=0xFF007F,
        description="Vibrant neon pink, high-tech and energetic",
    ),
    "emerald": ThemeDefinition(
        key="emerald",
        name="Emerald Forest",
        emoji="🌲",
        color_hex="#2ECC71",
        color_int=0x2ECC71,
        description="Lush emerald green, calming and fresh",
    ),
    "sunset": ThemeDefinition(
        key="sunset",
        name="Sunset Orange",
        emoji="🌅",
        color_hex="#E67E22",
        color_int=0xE67E22,
        description="Warm sunset amber, active and motivating",
    ),
    "pastel_pink": ThemeDefinition(
        key="pastel_pink",
        name="Pastel Sakura",
        emoji="🌸",
        color_hex="#FD79A8",
        color_int=0xFD79A8,
        description="Soft cherry blossom pink, gentle and pleasant",
    ),
    "midnight": ThemeDefinition(
        key="midnight",
        name="Midnight Purple",
        emoji="🔮",
        color_hex="#6C5CE7",
        color_int=0x6C5CE7,
        description="Mystic indigo purple, focused and deep",
    ),
    "crimson": ThemeDefinition(
        key="crimson",
        name="Crimson Flame",
        emoji="🩸",
        color_hex="#E74C3C",
        color_int=0xE74C3C,
        description="Intense crimson red, bold and urgent",
    ),
    "ocean": ThemeDefinition(
        key="ocean",
        name="Deep Ocean",
        emoji="🌊",
        color_hex="#0984E3",
        color_int=0x0984E3,
        description="Serene deep ocean blue, steady and productive",
    ),
    "gold": ThemeDefinition(
        key="gold",
        name="Royal Gold",
        emoji="👑",
        color_hex="#F1C40F",
        color_int=0xF1C40F,
        description="Radiant royal gold, premium and rewarding",
    ),
    "obsidian": ThemeDefinition(
        key="obsidian",
        name="Dark Obsidian",
        emoji="🖤",
        color_hex="#2D3436",
        color_int=0x2D3436,
        description="Sleek dark obsidian, ultra-minimal and sharp",
    ),
}

DEFAULT_THEME = THEMES["default"]


def get_theme(key: Optional[str]) -> ThemeDefinition:
    """Return ThemeDefinition for key; falls back to default if key is unknown or None."""
    if not key:
        return DEFAULT_THEME
    return THEMES.get(key.lower(), DEFAULT_THEME)


def get_theme_color(key: Optional[str]) -> int:
    """Return integer RGB color code for Discord embed from theme key."""
    return get_theme(key).color_int


def list_themes() -> list[ThemeDefinition]:
    """Return list of all registered themes in display order."""
    return list(THEMES.values())


async def set_user_theme(user_id: str | int, theme_key: str) -> bool:
    """
    Persist user theme preference to database and update cache.
    Returns True if valid theme was saved, False if theme is invalid.
    """
    clean_key = str(theme_key).strip().lower()
    if clean_key not in THEMES:
        return False

    from utils.helpers import save_user_settings
    await save_user_settings(str(user_id), theme=clean_key)
    return True
