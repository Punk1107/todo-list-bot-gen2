"""
tests/test_changelog.py — Unit tests for Feature 37: Automated Semantic Release Notes & CHANGELOG.md.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from changelog import service as cl_service
from changelog.models import ReleaseCategory
from changelog.views import ChangelogPreviewView


def test_conventional_commit_and_tag_classifier():
    c1, scope1, sum1, brk1 = cl_service.classify_task("feat(auth)!: Add OAuth2 PKCE login")
    assert c1 == ReleaseCategory.FEATURES
    assert scope1 == "auth"
    assert sum1 == "Add OAuth2 PKCE login"
    assert brk1 is True

    c2, _, sum2, _ = cl_service.classify_task("fix: Resolve memory leak in worker")
    assert c2 == ReleaseCategory.FIXES
    assert sum2 == "Resolve memory leak in worker"

    c3, _, _, _ = cl_service.classify_task("docs(readme): Update API guide")
    assert c3 == ReleaseCategory.DOCS

    c4, _, _, _ = cl_service.classify_task("perf: Speed up heatmap rendering")
    assert c4 == ReleaseCategory.PERF

    # Fallback via tags when no Conventional Commit prefix
    c5, _, _, _ = cl_service.classify_task("Optimize Postgres query plan", tags="backend, performance")
    assert c5 == ReleaseCategory.PERF

    c6, _, _, _ = cl_service.classify_task("Refactor helper utilities", tags="cleanup")
    assert c6 == ReleaseCategory.OTHER


@pytest.mark.asyncio
async def test_generate_changelog_sprint_and_markdown_export():
    fake_proj = SimpleNamespace(project_id=9, guild_id="g1", owner_id="u1", name="Gen5Platform")
    fake_sprint = SimpleNamespace(sprint_id=14, project_id=9, name="Sprint 14")
    done_rows = [
        {"task_id": 1, "task": "feat(ui): Dark mode toggle", "tags": "frontend", "story_points": 5, "done_at": datetime.now(timezone.utc)},
        {"task_id": 2, "task": "fix: Handle null deadline cleanly", "tags": None, "story_points": 2, "done_at": datetime.now(timezone.utc)},
        {"task_id": 3, "task": "Write onboarding SOP", "tags": "เอกสาร", "story_points": 1, "done_at": datetime.now(timezone.utc)},
    ]

    with patch("collaboration.service.get_project", new=AsyncMock(return_value=fake_proj)), \
         patch("agile.service.get_sprint", new=AsyncMock(return_value=fake_sprint)), \
         patch.object(cl_service.db, "afetchall", new=AsyncMock(return_value=done_rows)):
        gen = await cl_service.generate_changelog(
            project_id=9,
            guild_id="g1",
            sprint_id=14,
            version="v2.5.0",
            actor_id="u1",
        )

    assert gen.total_tasks == 3
    assert gen.total_points == 8
    assert len(gen.grouped[ReleaseCategory.FEATURES]) == 1
    assert len(gen.grouped[ReleaseCategory.FIXES]) == 1
    assert len(gen.grouped[ReleaseCategory.DOCS]) == 1

    md_text = cl_service.render_markdown_changelog(gen).decode("utf-8")
    assert "# Changelog — Gen5Platform" in md_text
    assert "## [v2.5.0]" in md_text
    assert "### 🚀 Features" in md_text
    assert "Dark mode toggle" in md_text

    embed = cl_service.render_release_embed(gen, lang="en")
    assert "Gen5Platform — v2.5.0" in embed.title
    assert any("Features" in f.name for f in embed.fields)

    view = ChangelogPreviewView(changelog=gen, user_id="u1", lang="en")
    assert view.publish_btn.disabled is False


@pytest.mark.asyncio
async def test_resolve_releases_channel_priority():
    rel_ch = MagicMock(spec=discord.TextChannel)
    rel_ch.name = "releases"
    rel_ch.id = 999

    fallback_ch = MagicMock(spec=discord.TextChannel)
    fallback_ch.name = "general"
    fallback_ch.id = 111

    guild = MagicMock(spec=discord.Guild)
    guild.id = 123
    guild.get_channel.side_effect = lambda cid: rel_ch if cid == 999 else None
    guild.text_channels = [fallback_ch, rel_ch]

    with patch.object(cl_service.db, "afetchone", new=AsyncMock(return_value={"release_channel_id": 999, "channel_id": 111})), \
         patch.object(cl_service.db, "get_guild_setting", new=AsyncMock(return_value=None)):
        resolved = await cl_service.resolve_releases_channel(guild, project_id=9)
    assert resolved is rel_ch

