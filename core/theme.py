"""
core/theme.py — Embed Theme Personalization Engine
Provides curated, aesthetic color themes for Discord embeds across the bot.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Optional


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
    Deactivates any active custom theme so the built-in preset takes effect.
    Returns True if valid theme was saved, False if theme is invalid.
    """
    clean_key = str(theme_key).strip().lower()
    if clean_key not in THEMES:
        return False

    from core.database import db
    from utils.helpers import save_user_settings
    uid = str(user_id)
    try:
        await db.aexecute(
            "UPDATE user_themes SET is_active=FALSE, updated_at=NOW() WHERE user_id=$1 AND is_active=TRUE",
            (uid,),
        )
        db.query_cache.invalidate_table("user_themes")
    except Exception:
        pass
    await save_user_settings(uid, theme=clean_key)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Gen 5.0 Feature 43: Custom Hex Palettes, Emoji Sets & Progress Bar Styles
# ─────────────────────────────────────────────────────────────────────────────

_HEX_RE = re.compile(r"^#?[0-9A-Fa-f]{6}$")

VALID_PROGRESS_STYLES = ("neon", "retro", "minimal", "blocks")

DEFAULT_EMOJI_SET: dict[str, str] = {
    "pending": "⏳",
    "in_progress": "🔄",
    "done": "✅",
    "overdue": "🚨",
}

EMOJI_PRESETS: dict[str, dict[str, str]] = {
    "classic": dict(DEFAULT_EMOJI_SET),
    "neon": {"pending": "🔮", "in_progress": "⚡", "done": "💎", "overdue": "💥"},
    "retro": {"pending": "🕹️", "in_progress": "⚙️", "done": "🏆", "overdue": "👾"},
    "minimal": {"pending": "○", "in_progress": "◐", "done": "●", "overdue": "!"},
}


@dataclass(frozen=True)
class EffectivePalette:
    """Resolved palette applied to Discord embeds for a user or guild."""
    name: str
    primary_color: str = "#5865F2"
    success_color: str = "#57F287"
    warning_color: str = "#FEE75C"
    danger_color: str = "#ED4245"
    progress_style: str = "neon"
    emoji_set: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_EMOJI_SET))
    source: str = "default"

    @property
    def primary_int(self) -> int:
        return hex_to_int(self.primary_color, 0x5865F2)

    def color_for(self, status: str = "primary") -> int:
        """Return integer RGB color matching status key."""
        mapping = {
            "primary": self.primary_color,
            "pending": self.primary_color,
            "success": self.success_color,
            "done": self.success_color,
            "completed": self.success_color,
            "warning": self.warning_color,
            "in_progress": self.warning_color,
            "danger": self.danger_color,
            "overdue": self.danger_color,
        }
        return hex_to_int(mapping.get(status.lower(), self.primary_color), 0x5865F2)

    def emoji_for(self, key: str, fallback: str = "") -> str:
        return self.emoji_set.get(key, DEFAULT_EMOJI_SET.get(key, fallback))


def normalize_hex_color(value: str, fallback: Optional[str] = None) -> str:
    """Validate and normalize a 6-digit hex color as uppercase `#RRGGBB`."""
    cleaned = (value or "").strip()
    if not _HEX_RE.match(cleaned):
        if fallback is not None:
            return fallback
        raise ValueError(f"Invalid hex color '{value}'. Expected #RRGGBB.")
    if not cleaned.startswith("#"):
        cleaned = f"#{cleaned}"
    return cleaned.upper()


def hex_to_int(hex_str: str, fallback: int = 0x5865F2) -> int:
    """Convert `#RRGGBB` string into integer color for `discord.Embed`."""
    try:
        cleaned = normalize_hex_color(hex_str)
        return int(cleaned[1:], 16)
    except Exception:
        return fallback


def render_progress_bar(pct: float, style: str = "neon", width: int = 10) -> str:
    """Render a progress bar string using the chosen theme style."""
    clamped = max(0.0, min(100.0, float(pct)))
    filled = round((clamped / 100.0) * width)
    empty = max(0, width - filled)

    style_key = style if style in VALID_PROGRESS_STYLES else "neon"
    if style_key == "retro":
        return f"[{'#' * filled}{'-' * empty}]"
    if style_key == "minimal":
        return f"{'●' * filled}{'○' * empty}"
    if style_key == "blocks":
        return f"{'🟩' * filled}{'⬜' * empty}"
    return f"{'▰' * filled}{'▱' * empty}"


def _parse_emoji_set(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        merged = dict(DEFAULT_EMOJI_SET)
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, str) and v.strip():
                merged[k] = v.strip()[:16]
        return merged
    if isinstance(raw, str):
        try:
            return _parse_emoji_set(json.loads(raw))
        except Exception:
            pass
    return dict(DEFAULT_EMOJI_SET)


def _row_to_palette(row: dict[str, Any], source: str) -> EffectivePalette:
    return EffectivePalette(
        name=str(row.get("name") or "Custom"),
        primary_color=normalize_hex_color(str(row.get("primary_color") or "#5865F2"), "#5865F2"),
        success_color=normalize_hex_color(str(row.get("success_color") or "#57F287"), "#57F287"),
        warning_color=normalize_hex_color(str(row.get("warning_color") or "#FEE75C"), "#FEE75C"),
        danger_color=normalize_hex_color(str(row.get("danger_color") or "#ED4245"), "#ED4245"),
        progress_style=str(row.get("progress_style") or "neon"),
        emoji_set=_parse_emoji_set(row.get("emoji_set")),
        source=source,
    )


async def save_user_custom_theme(
    user_id: str,
    name: str,
    *,
    primary_color: str = "#5865F2",
    success_color: str = "#57F287",
    warning_color: str = "#FEE75C",
    danger_color: str = "#ED4245",
    progress_style: str = "neon",
    emoji_set: Optional[dict[str, str]] = None,
    activate: bool = True,
) -> EffectivePalette:
    """Create or update a custom palette for `user_id` and optionally activate it."""
    from core.database import db
    from utils.helpers import ensure_user

    clean_name = name.strip()[:40]
    if not clean_name:
        raise ValueError("Theme name cannot be empty.")
    style = progress_style.strip().lower()
    if style not in VALID_PROGRESS_STYLES:
        raise ValueError(f"Unsupported progress style '{progress_style}'.")

    p_hex = normalize_hex_color(primary_color)
    s_hex = normalize_hex_color(success_color)
    w_hex = normalize_hex_color(warning_color)
    d_hex = normalize_hex_color(danger_color)
    emojis = _parse_emoji_set(emoji_set)

    uid = str(user_id)
    await ensure_user(uid)

    if activate:
        await db.aexecute(
            "UPDATE user_themes SET is_active=FALSE, updated_at=NOW() WHERE user_id=$1",
            (uid,),
        )

    row = await db.afetchone(
        """INSERT INTO user_themes
               (user_id, name, primary_color, success_color, warning_color,
                danger_color, progress_style, emoji_set, is_active, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,NOW())
           ON CONFLICT (user_id, name) DO UPDATE SET
               primary_color=EXCLUDED.primary_color,
               success_color=EXCLUDED.success_color,
               warning_color=EXCLUDED.warning_color,
               danger_color=EXCLUDED.danger_color,
               progress_style=EXCLUDED.progress_style,
               emoji_set=EXCLUDED.emoji_set,
               is_active=EXCLUDED.is_active,
               updated_at=NOW()
           RETURNING *""",
        (uid, clean_name, p_hex, s_hex, w_hex, d_hex, style, json.dumps(emojis), activate),
    )
    db.query_cache.invalidate_table("user_themes")
    return _row_to_palette(dict(row), "user_custom") if row else EffectivePalette(
        name=clean_name,
        primary_color=p_hex,
        success_color=s_hex,
        warning_color=w_hex,
        danger_color=d_hex,
        progress_style=style,
        emoji_set=emojis,
        source="user_custom",
    )


async def list_user_custom_themes(user_id: str) -> list[dict[str, Any]]:
    """Return all saved custom themes for `user_id`."""
    from core.database import db
    rows = await db.afetchall(
        "SELECT * FROM user_themes WHERE user_id=$1 ORDER BY is_active DESC, updated_at DESC",
        (str(user_id),),
    )
    return [dict(r) for r in (rows or [])]


async def activate_user_custom_theme(user_id: str, name: str) -> Optional[EffectivePalette]:
    """Activate an existing custom theme by name for `user_id`."""
    from core.database import db
    uid = str(user_id)
    target = await db.afetchone(
        "SELECT * FROM user_themes WHERE user_id=$1 AND LOWER(name)=LOWER($2)",
        (uid, name.strip()),
    )
    if not target:
        return None
    await db.aexecute(
        "UPDATE user_themes SET is_active=FALSE, updated_at=NOW() WHERE user_id=$1",
        (uid,),
    )
    row = await db.afetchone(
        "UPDATE user_themes SET is_active=TRUE, updated_at=NOW() WHERE theme_id=$1 RETURNING *",
        (target["theme_id"],),
    )
    db.query_cache.invalidate_table("user_themes")
    return _row_to_palette(dict(row or target), "user_custom")


async def delete_user_custom_theme(user_id: str, name: str) -> bool:
    """Delete a saved custom theme by name for `user_id`."""
    from core.database import db
    row = await db.afetchone(
        "DELETE FROM user_themes WHERE user_id=$1 AND LOWER(name)=LOWER($2) RETURNING theme_id",
        (str(user_id), name.strip()),
    )
    if row:
        db.query_cache.invalidate_table("user_themes")
        return True
    return False


async def save_guild_theme(
    guild_id: str,
    updated_by: str,
    *,
    name: str = "Server Theme",
    primary_color: str = "#5865F2",
    success_color: str = "#57F287",
    warning_color: str = "#FEE75C",
    danger_color: str = "#ED4245",
    progress_style: str = "neon",
    emoji_set: Optional[dict[str, str]] = None,
) -> EffectivePalette:
    """Create or update server-wide default custom palette in `guild_themes`."""
    from core.database import db

    clean_name = (name or "Server Theme").strip()[:40]
    style = progress_style.strip().lower()
    if style not in VALID_PROGRESS_STYLES:
        raise ValueError(f"Unsupported progress style '{progress_style}'.")

    p_hex = normalize_hex_color(primary_color)
    s_hex = normalize_hex_color(success_color)
    w_hex = normalize_hex_color(warning_color)
    d_hex = normalize_hex_color(danger_color)
    emojis = _parse_emoji_set(emoji_set)

    row = await db.afetchone(
        """INSERT INTO guild_themes
               (guild_id, name, primary_color, success_color, warning_color,
                danger_color, progress_style, emoji_set, updated_by, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,NOW())
           ON CONFLICT (guild_id) DO UPDATE SET
               name=EXCLUDED.name,
               primary_color=EXCLUDED.primary_color,
               success_color=EXCLUDED.success_color,
               warning_color=EXCLUDED.warning_color,
               danger_color=EXCLUDED.danger_color,
               progress_style=EXCLUDED.progress_style,
               emoji_set=EXCLUDED.emoji_set,
               updated_by=EXCLUDED.updated_by,
               updated_at=NOW()
           RETURNING *""",
        (str(guild_id), clean_name, p_hex, s_hex, w_hex, d_hex, style, json.dumps(emojis), str(updated_by)),
    )
    db.query_cache.invalidate_table("guild_themes")
    return _row_to_palette(dict(row), "guild_custom") if row else EffectivePalette(
        name=clean_name,
        primary_color=p_hex,
        success_color=s_hex,
        warning_color=w_hex,
        danger_color=d_hex,
        progress_style=style,
        emoji_set=emojis,
        source="guild_custom",
    )


def _can_query_theme_table(db) -> bool:
    """Return True when the DB pool is ready or `db.afetchone` is mocked in tests."""
    return getattr(db, "_pool", None) is not None or hasattr(db.afetchone, "assert_called")


def _has_palette_fields(row) -> bool:
    return bool(row and (row.get("primary_color") if hasattr(row, "get") else "primary_color" in row))


async def get_guild_theme(guild_id: str) -> Optional[EffectivePalette]:
    """Fetch guild custom palette if configured."""
    from core.database import db
    if not _can_query_theme_table(db):
        return None
    row = await db.afetchone(
        "SELECT * FROM guild_themes WHERE guild_id=$1",
        (str(guild_id),),
    )
    return _row_to_palette(dict(row), "guild_custom") if _has_palette_fields(row) else None


async def resolve_user_palette(
    user_id: str | int,
    guild_id: Optional[str | int] = None,
) -> EffectivePalette:
    """
    Resolve effective palette in priority order:
      1. Active user custom theme (`user_themes`)
      2. Explicit built-in preset (`users.theme` if != 'default')
      3. Guild custom theme (`guild_themes`)
      4. Default Discord blurple palette
    """
    from core.database import db
    from utils.helpers import get_user_theme

    uid = str(user_id)
    if _can_query_theme_table(db):
        custom_row = await db.afetchone(
            "SELECT * FROM user_themes WHERE user_id=$1 AND is_active=TRUE LIMIT 1",
            (uid,),
        )
        if _has_palette_fields(custom_row):
            return _row_to_palette(dict(custom_row), "user_custom")

    preset_key = await get_user_theme(uid)
    if preset_key and preset_key != "default" and preset_key in THEMES:
        th = THEMES[preset_key]
        return EffectivePalette(
            name=th.name,
            primary_color=th.color_hex,
            source="user_preset",
        )

    if guild_id:
        guild_palette = await get_guild_theme(str(guild_id))
        if guild_palette:
            return guild_palette

    return EffectivePalette(name=DEFAULT_THEME.name, primary_color=DEFAULT_THEME.color_hex, source="default")
