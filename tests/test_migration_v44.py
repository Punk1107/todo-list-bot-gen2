"""Migration v44 & Discord Command Tree Integrity Tests for Gen 5.0 Pillar 10."""
from __future__ import annotations

import asyncio
import importlib

from core.database import MIGRATIONS, SCHEMA_VERSION, _KNOWN_TABLES, _split_sql_statements
import discord
from discord.ext import commands
import main


def test_schema_version_is_44():
    assert SCHEMA_VERSION == 44


def test_known_tables_include_pillar10_tables():
    expected = {
        "project_federation_guilds",
        "federation_invites",
        "task_assignees",
        "task_role_assignments",
        "task_assignment_signoffs",
        "tasks_archive",
        "audit_log_summary",
        "user_themes",
        "guild_themes",
        "checklist_templates",
    }
    missing = expected - _KNOWN_TABLES
    assert not missing, f"Missing from _KNOWN_TABLES: {missing}"


def test_migration_v44_statements_split_cleanly():
    versions = {ver: sql for ver, sql in MIGRATIONS}
    assert 44 in versions
    stmts = _split_sql_statements(versions[44])
    assert len(stmts) >= 15
    joined = "\n".join(stmts)
    for needle in (
        "INSERT INTO users (user_id, lang, timezone, role, theme)",
        "federation_invites",
        "task_role_assignments",
        "task_assignment_signoffs",
        "tasks_archive",
        "audit_log_summary",
        "user_themes",
        "guild_themes",
        "display_mode",
        "checklist_templates",
        "INSERT INTO schema_version VALUES (44)",
    ):
        assert needle in joined


def test_all_cogs_load_and_respect_discord_limits():
    async def _check():
        intents = discord.Intents.default()
        bot = commands.Bot(command_prefix="!", intents=intents)
        try:
            for ext in main.COGS:
                # Import rather than bot.load_extension so pre-collected modules in other
                # test files keep matching sys.modules entries for unittest.mock.patch.
                mod = importlib.import_module(ext)
                await mod.setup(bot)

            top_cmds = bot.tree.get_commands()
            assert len(top_cmds) <= 100, f"Exceeded Discord 100 top-level limit: {len(top_cmds)}"
            cmd_names = {c.name for c in top_cmds}
            for expected in ("federation", "assign", "privacy", "checklist", "theme", "settings", "admin", "export"):
                assert expected in cmd_names

            for cmd in top_cmds:
                if hasattr(cmd, "commands"):
                    assert len(cmd.commands) <= 25, f"/{cmd.name} has {len(cmd.commands)} (>25) children"
        finally:
            await bot.close()

    asyncio.run(_check())
