"""
tests/test_help_system.py — Zero-Drift Command Parity, Discord Limits & UX Tests for /help
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
from discord.ext import commands
import pytest

import main
from handlers.help_registry import (
    HELP_CATEGORIES,
    HELP_COMMANDS,
    HELP_WORKFLOWS,
    audit_tree_coverage,
    get_command_meta,
    get_commands_for_category,
    paginate_commands,
    search_help_commands,
)
from handlers.help_ui import (
    HelpCategorySelect,
    HelpView,
    build_command_detail_embed,
    build_help_embed,
    build_search_results_embed,
    build_workflow_embed,
)
from locales.i18n import SUPPORTED_LANGS


def _embed_char_count(embed: discord.Embed) -> int:
    total = len(embed.title or "") + len(embed.description or "")
    if embed.footer and embed.footer.text:
        total += len(embed.footer.text)
    if embed.author and embed.author.name:
        total += len(embed.author.name)
    for f in embed.fields:
        total += len(f.name or "") + len(f.value or "")
    return total


def _assert_valid_discord_embed(embed: discord.Embed) -> None:
    assert embed is not None
    assert len(embed.fields) > 0
    assert len(embed.fields) <= 25
    assert len(embed.title or "") <= 256
    assert len(embed.description or "") <= 4096
    assert len((embed.footer.text if embed.footer else "") or "") <= 2048
    for f in embed.fields:
        assert 1 <= len(f.name or "") <= 256
        assert 1 <= len(f.value or "") <= 1024
    assert _embed_char_count(embed) <= 6000


class TestHelpTreeParity:
    """Guarantee 100% 1:1 coverage between live CommandTree across all Cogs and /help."""

    @pytest.mark.asyncio
    async def test_all_live_commands_documented_with_zero_drift(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        try:
            for cog_path in main.COGS:
                await bot.load_extension(cog_path)
            missing, stale = audit_tree_coverage(bot.tree)
        finally:
            # Cancel background @tasks.loop timers started during Cog load
            for cog in bot.cogs.values():
                for attr_name in dir(cog):
                    attr = getattr(cog, attr_name, None)
                    if hasattr(attr, "cancel") and callable(attr.cancel):
                        try:
                            attr.cancel()
                        except Exception:
                            pass
            await bot.close()

        assert missing == set(), f"Commands missing from HELP_COMMANDS: {sorted(missing)}"
        assert stale == set(), f"Stale entries in HELP_COMMANDS not in bot.tree: {sorted(stale)}"

    def test_reaction_triggers_and_context_menu_documented(self) -> None:
        assert get_command_meta("Add to To-Do") is not None
        assert get_command_meta("reactions") is not None
        assert len(HELP_COMMANDS) >= 190


class TestHelpDiscordLimits:
    """Verify every category, page, density, and language respects Discord API limits."""

    def test_select_options_within_limits_all_languages(self) -> None:
        for lang in SUPPORTED_LANGS:
            select = HelpCategorySelect(lang)
            assert len(select.options) == len(HELP_CATEGORIES)
            assert 1 <= len(select.options) <= 25
            for opt in select.options:
                assert 1 <= len(opt.label) <= 100
                if opt.description:
                    assert len(opt.description) <= 100

    def test_all_categories_all_pages_standard_and_compact(self) -> None:
        for lang in ("en", "th"):
            for compact in (False, True):
                page_size = 12 if compact else 7
                for cat in HELP_CATEGORIES:
                    if cat.key in ("overview", "tips"):
                        embed = build_help_embed(cat.key, lang, compact=compact)
                        _assert_valid_discord_embed(embed)
                        continue
                    cmds = get_commands_for_category(cat.key, include_admin=True)
                    _, _, total_pages = paginate_commands(cmds, page=1, page_size=page_size)
                    for page in range(1, total_pages + 1):
                        embed = build_help_embed(
                            cat.key,
                            lang,
                            page=page,
                            compact=compact,
                            color=0xFF007F,
                            include_admin=True,
                        )
                        _assert_valid_discord_embed(embed)
                        assert embed.color is not None and embed.color.value == 0xFF007F

    def test_all_9_languages_render_cleanly(self) -> None:
        for lang in SUPPORTED_LANGS:
            for cat in HELP_CATEGORIES:
                embed = build_help_embed(cat.key, lang)
                _assert_valid_discord_embed(embed)


class TestHelpSearchDetailWorkflowsAndView:
    """Test command detail cards, EN/TH search, playbooks, and interactive view state."""

    def test_lookup_and_search_bilingual(self) -> None:
        assert get_command_meta("/sprint burndown") is not None
        assert get_command_meta("admin janitor") is not None

        gantt_hits = search_help_commands("gantt", "en")
        assert any(h.path == "project gantt" for h in gantt_hits)

        th_vacation_hits = search_help_commands("วันลา", "th")
        assert any(h.path.startswith("vacation") for h in th_vacation_hits)

        th_trash_hits = search_help_commands("ถังขยะ", "th")
        assert any(h.path in ("trash", "restore") for h in th_trash_hits)

    def test_admin_filtering_in_search_and_category(self) -> None:
        assert any(c.path == "admin janitor" for c in search_help_commands("janitor", "en", include_admin=True))
        assert search_help_commands("janitor", "en", include_admin=False) == []

        with_admin = get_commands_for_category("settings", include_admin=True)
        without_admin = get_commands_for_category("settings", include_admin=False)
        assert len(with_admin) > len(without_admin)
        assert all(not c.is_admin for c in without_admin)

    def test_detail_search_and_workflow_embeds(self) -> None:
        for path in ("sprint create", "trash", "Add to To-Do", "reactions"):
            entry = get_command_meta(path)
            assert entry is not None
            for lang in ("en", "th"):
                _assert_valid_discord_embed(build_command_detail_embed(entry, lang, color=0x2ECC71))

        matches = search_help_commands("sprint", "en")
        _assert_valid_discord_embed(build_search_results_embed("sprint", matches, "en"))
        _assert_valid_discord_embed(build_search_results_embed("nonexistent_xyz_cmd", [], "th"))

        _assert_valid_discord_embed(build_workflow_embed(None, "en"))
        for wf in HELP_WORKFLOWS:
            for lang in ("en", "th"):
                _assert_valid_discord_embed(build_workflow_embed(wf.key, lang))

    @pytest.mark.asyncio
    async def test_help_view_interactions_and_author_guard(self) -> None:
        view = HelpView("en", author_id=1001, category="collab", compact=False, color=0x123456)
        assert view.page == 1

        # Pagination next/prev
        owner_inter = MagicMock(spec=discord.Interaction)
        owner_inter.user = MagicMock(id=1001)
        owner_inter.response = AsyncMock()

        await view._on_next(owner_inter)
        assert view.page == 2
        assert owner_inter.response.edit_message.await_count == 1

        await view._on_prev(owner_inter)
        assert view.page == 1

        # Search jump -> single hit goes straight to detail mode
        await view.run_search(owner_inter, "admin janitor")
        assert view.mode == "detail"
        assert view.detail_path == "admin janitor"

        # Toggle compact density
        await view._on_toggle_density(owner_inter)
        assert view.compact is True

        # Non-author interaction blocked politely
        stranger_inter = MagicMock(spec=discord.Interaction)
        stranger_inter.user = MagicMock(id=9999)
        stranger_inter.response = AsyncMock()
        allowed = await view.interaction_check(stranger_inter)
        assert allowed is False
        stranger_inter.response.send_message.assert_awaited_once()

