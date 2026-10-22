"""Unit & Integration tests for Category 9 (Item 26): Embed Theme Personalization."""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest
import discord

from core.database import db
from core.theme import (
    THEMES,
    get_theme,
    get_theme_color,
    list_themes,
    set_user_theme,
)
from handlers.settings_cog import build_theme_preview_embed, ThemeSelectView
from utils.helpers import get_user_theme, get_user_theme_color, save_user_settings


# ─────────────────────────────────────────────────────────────────────────────
# 1. Theme Definitions & Engine Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_ten_themes_defined_and_valid():
    assert len(THEMES) == 10
    hex_pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")

    expected_keys = {
        "default",
        "cyberpunk",
        "emerald",
        "sunset",
        "pastel_pink",
        "midnight",
        "crimson",
        "ocean",
        "gold",
        "obsidian",
    }
    assert set(THEMES.keys()) == expected_keys

    for key, th in THEMES.items():
        assert th.key == key
        assert len(th.name) > 0
        assert len(th.emoji) > 0
        assert hex_pattern.match(th.color_hex), f"Invalid hex color for {key}: {th.color_hex}"
        assert 0 <= th.color_int <= 0xFFFFFF
        # Int matches hex
        assert f"#{th.color_int:06X}".upper() == th.color_hex.upper()
        assert len(th.description) > 0


def test_get_theme_lookup():
    # Valid key
    th = get_theme("cyberpunk")
    assert th.name == "Cyberpunk Neon"
    assert th.color_hex.upper() == "#FF007F"

    # Case-insensitive
    th_upper = get_theme("CYBERPUNK")
    assert th_upper.key == "cyberpunk"

    # Fallback to default
    th_invalid = get_theme("unknown_rainbow_theme")
    assert th_invalid.key == "default"

    th_none = get_theme(None)
    assert th_none.key == "default"


def test_get_theme_color():
    color = get_theme_color("emerald")
    assert color == 0x2ECC71

    # Fallback
    fallback = get_theme_color("non_existent")
    assert fallback == 0x5865F2


def test_list_themes():
    themes = list_themes()
    assert len(themes) == 10
    assert themes[0].key == "default"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Persistence & Cache Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_user_theme_success():
    with patch.object(db, "aexecute", new=AsyncMock(return_value="UPDATE 1")):
        # Prepopulate cache
        db.user_cache.set("user_test", "en", "UTC", 0, "admin", "default")
        assert db.user_cache.get("user_test").theme == "default"

        res = await set_user_theme("user_test", "sunset")
        assert res is True
        assert db.user_cache.get("user_test").theme == "sunset"


@pytest.mark.asyncio
async def test_set_user_theme_invalid_rejected():
    res = await set_user_theme("user_test", "non_existent_galaxy")
    assert res is False


@pytest.mark.asyncio
async def test_get_user_theme_helpers():
    # 1. From cache
    db.user_cache.set("user_cached", "en", "UTC", 0, "admin", "pastel_pink")
    theme = await get_user_theme("user_cached")
    assert theme == "pastel_pink"

    color = await get_user_theme_color("user_cached")
    assert color == 0xFD79A8

    # 2. From DB when not cached
    db.user_cache.invalidate("user_db")
    mock_user_row = {"lang": "en", "timezone": "UTC", "channel_id": None, "role": "member", "theme": "gold"}
    with patch.object(db, "afetchone", new=AsyncMock(return_value=mock_user_row)):
        theme_from_db = await get_user_theme("user_db")
        assert theme_from_db == "gold"
        color_from_db = await get_user_theme_color("user_db")
        assert color_from_db == 0xF1C40F

    # 3. Default when row is None
    db.user_cache.invalidate("user_empty")
    with patch.object(db, "afetchone", new=AsyncMock(return_value=None)):
        theme_default = await get_user_theme("user_empty")
        assert theme_default == "default"


@pytest.mark.asyncio
async def test_save_user_settings_theme_persistence():
    with patch.object(db, "aexecute", new=AsyncMock(return_value="UPDATE 1")):
        db.user_cache.set("u_settings", "en", "UTC", 0, "member", "default")
        await save_user_settings("u_settings", lang="th", theme="midnight")
        
        cached = db.user_cache.get("u_settings")
        assert cached.lang == "th"
        assert cached.theme == "midnight"


# ─────────────────────────────────────────────────────────────────────────────
# 3. UI Embed & View Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_build_theme_preview_embed():
    embed = build_theme_preview_embed("cyberpunk", lang="en")
    assert "Cyberpunk Neon" in embed.title
    assert embed.color.value == 0xFF007F
    assert len(embed.fields) >= 1
    assert "#FF007F" in embed.footer.text


def test_theme_select_view_components():
    view = ThemeSelectView(user_id="u1", current_theme="emerald", lang="en")
    # Has select dropdown + save button
    assert len(view.children) == 2

    select: discord.ui.Select = view.children[0]
    assert len(select.options) == 10
    # Emerald is selected by default
    selected_option = next(opt for opt in select.options if opt.value == "emerald")
    assert selected_option.default is True
