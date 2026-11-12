"""
changelog/service.py — Pure Python Conventional Commit Classifier, Release Collector & Exporter.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import discord

from changelog.models import (
    CATEGORY_HEADINGS,
    ORDERED_CATEGORIES,
    ChangelogEntry,
    GeneratedChangelog,
    ReleaseCategory,
)
from core.database import db
from locales.i18n import t

log = logging.getLogger(__name__)

_CONVENTIONAL_RE = re.compile(
    r"^\s*(feat|feature|fix|bugfix|hotfix|docs|doc|perf|performance|refactor|chore|test|ci|build|style)"
    r"(?:\(([^)]+)\))?(!)?:\s*(.+)$",
    re.IGNORECASE,
)

_PREFIX_TO_CAT: dict[str, ReleaseCategory] = {
    "feat":        ReleaseCategory.FEATURES,
    "feature":     ReleaseCategory.FEATURES,
    "fix":         ReleaseCategory.FIXES,
    "bugfix":      ReleaseCategory.FIXES,
    "hotfix":      ReleaseCategory.FIXES,
    "docs":        ReleaseCategory.DOCS,
    "doc":         ReleaseCategory.DOCS,
    "perf":        ReleaseCategory.PERF,
    "performance": ReleaseCategory.PERF,
}

_TAG_TO_CAT: dict[str, ReleaseCategory] = {
    "feat": ReleaseCategory.FEATURES,
    "feature": ReleaseCategory.FEATURES,
    "features": ReleaseCategory.FEATURES,
    "enhancement": ReleaseCategory.FEATURES,
    "ฟีเจอร์": ReleaseCategory.FEATURES,
    "fix": ReleaseCategory.FIXES,
    "bug": ReleaseCategory.FIXES,
    "bugfix": ReleaseCategory.FIXES,
    "hotfix": ReleaseCategory.FIXES,
    "บั๊ก": ReleaseCategory.FIXES,
    "แก้บั๊ก": ReleaseCategory.FIXES,
    "docs": ReleaseCategory.DOCS,
    "doc": ReleaseCategory.DOCS,
    "documentation": ReleaseCategory.DOCS,
    "wiki": ReleaseCategory.DOCS,
    "เอกสาร": ReleaseCategory.DOCS,
    "perf": ReleaseCategory.PERF,
    "performance": ReleaseCategory.PERF,
    "optimize": ReleaseCategory.PERF,
    "optimization": ReleaseCategory.PERF,
    "ประสิทธิภาพ": ReleaseCategory.PERF,
}


class ChangelogError(Exception):
    """Base error carrying an i18n key for changelog generation & publishing."""


def classify_task(
    title: str,
    tags: Optional[str] = None,
) -> tuple[ReleaseCategory, Optional[str], str, bool]:
    """Classify a completed task into a semantic category without any external APIs.

    Returns ``(category, scope, clean_summary, is_breaking)``.
    """
    raw_title = (title or "").strip()
    scope: Optional[str] = None
    is_breaking = False
    clean_summary = raw_title
    cat: Optional[ReleaseCategory] = None

    m = _CONVENTIONAL_RE.match(raw_title)
    if m:
        prefix = m.group(1).lower()
        scope = m.group(2).strip() if m.group(2) else None
        is_breaking = bool(m.group(3))
        clean_summary = m.group(4).strip()
        cat = _PREFIX_TO_CAT.get(prefix)

    if cat is None and tags:
        for tag in tags.split(","):
            t_low = tag.strip().lower()
            if t_low in _TAG_TO_CAT:
                cat = _TAG_TO_CAT[t_low]
                break

    if cat is None:
        cat = ReleaseCategory.OTHER

    return cat, scope, clean_summary or raw_title, is_breaking


def _parse_date_input(raw: Optional[str]) -> Optional[datetime]:
    if not raw or not raw.strip():
        return None
    s = raw.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ChangelogError("changelog_invalid_date")


async def generate_changelog(
    project_id: int,
    guild_id: str,
    sprint_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    version: Optional[str] = None,
    actor_id: Optional[str] = None,
    is_guild_admin: bool = False,
) -> GeneratedChangelog:
    """Collect completed project tasks by sprint or date range and classify them into Release Notes."""
    from collaboration import service as collab_service

    proj = await collab_service.get_project(project_id, guild_id)
    if actor_id is not None and not is_guild_admin and proj.owner_id != actor_id:
        role = await collab_service.get_member_role(project_id, actor_id)
        if not role:
            raise ChangelogError("proj_no_permission")

    sprint_name: Optional[str] = None
    period_label = ""
    rows: Any

    if sprint_id is not None:
        from agile import service as agile_service
        sprint = await agile_service.get_sprint(sprint_id)
        if not sprint or sprint.project_id != project_id:
            raise ChangelogError("changelog_sprint_not_found")
        sprint_name = sprint.name
        period_label = f"Sprint #{sprint.sprint_id}: {sprint.name}"
        rows = await db.afetchall(
            """SELECT task_id, task, tags, COALESCE(story_points, 0) AS story_points,
                      COALESCE(completed_at, updated_at) AS done_at
               FROM tasks
               WHERE project_id = $1 AND guild_id = $2
                 AND sprint_id = $3
                 AND status = 'Completed'
                 AND is_deleted = FALSE
               ORDER BY done_at DESC, task_id DESC""",
            (project_id, guild_id, sprint_id),
        )
    else:
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        dt_start = _parse_date_input(start_date)
        dt_end = _parse_date_input(end_date)
        if dt_start is None and dt_end is None:
            dt_end = now_naive
            dt_start = (now_naive - timedelta(days=14)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif dt_start is not None and dt_end is None:
            dt_end = now_naive
        elif dt_start is None and dt_end is not None:
            dt_start = (dt_end - timedelta(days=14)).replace(hour=0, minute=0, second=0, microsecond=0)

        dt_start = dt_start.replace(hour=0, minute=0, second=0, microsecond=0)
        dt_end = dt_end.replace(hour=23, minute=59, second=59, microsecond=999999)
        if dt_start > dt_end:
            raise ChangelogError("changelog_invalid_date_range")

        period_label = f"{dt_start.strftime('%Y-%m-%d')} → {dt_end.strftime('%Y-%m-%d')}"
        rows = await db.afetchall(
            """SELECT task_id, task, tags, COALESCE(story_points, 0) AS story_points,
                      COALESCE(completed_at, updated_at) AS done_at
               FROM tasks
               WHERE project_id = $1 AND guild_id = $2
                 AND status = 'Completed'
                 AND is_deleted = FALSE
                 AND COALESCE(completed_at, updated_at) >= $3
                 AND COALESCE(completed_at, updated_at) <= $4
               ORDER BY done_at DESC, task_id DESC""",
            (project_id, guild_id, dt_start, dt_end),
        )

    grouped: dict[ReleaseCategory, list[ChangelogEntry]] = {cat: [] for cat in ORDERED_CATEGORIES}
    total_points = 0
    for r in (rows or []):
        cat, scope, summary, is_breaking = classify_task(str(r["task"]), r.get("tags"))
        pts = int(r.get("story_points") or 0)
        total_points += pts
        grouped[cat].append(
            ChangelogEntry(
                task_id=int(r["task_id"]),
                category=cat,
                scope=scope,
                summary=summary,
                is_breaking=is_breaking,
                raw_tags=r.get("tags"),
                story_points=pts,
                completed_at=r.get("done_at"),
            )
        )

    total_tasks = sum(len(items) for items in grouped.values())
    ver = (version or "").strip() or (
        sprint_name if sprint_name else f"Release {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    )
    return GeneratedChangelog(
        project_id=project_id,
        project_name=proj.name,
        guild_id=guild_id,
        version_label=ver,
        period_label=period_label,
        sprint_id=sprint_id,
        sprint_name=sprint_name,
        grouped=grouped,
        total_tasks=total_tasks,
        total_points=total_points,
    )


def render_release_embed(changelog: GeneratedChangelog, lang: str = "th") -> discord.Embed:
    """Render a Discord Embed preview/announcement for ``GeneratedChangelog``."""
    embed = discord.Embed(
        title=f"📦 {changelog.project_name} — {changelog.version_label}",
        description=(
            f"🗓️ **{changelog.period_label}**\n"
            f"✅ **{changelog.total_tasks}** {t('changelog_completed_count', lang)}"
            + (f" · ⭐ **{changelog.total_points} pts**" if changelog.total_points > 0 else "")
        ),
        color=0x10B981 if changelog.total_tasks > 0 else 0x9CA3AF,
        timestamp=changelog.generated_at,
    )
    if changelog.total_tasks == 0:
        embed.add_field(
            name=t("changelog_empty_header", lang),
            value=f"> {t('changelog_empty_body', lang)}",
            inline=False,
        )
        embed.set_footer(text=t("footer_text", lang))
        return embed

    for cat in ORDERED_CATEGORIES:
        entries = changelog.grouped.get(cat, [])
        if not entries:
            continue
        lines: list[str] = []
        char_count = 0
        omitted = 0
        for entry in entries:
            bullet = entry.format_bullet()
            if char_count + len(bullet) + 40 > 1000:
                omitted = len(entries) - len(lines)
                break
            lines.append(bullet)
            char_count += len(bullet) + 1
        if omitted > 0:
            lines.append(f"*... +{omitted} more in CHANGELOG.md*")
        embed.add_field(
            name=f"{CATEGORY_HEADINGS[cat]} ({len(entries)})",
            value="\n".join(lines),
            inline=False,
        )

    embed.set_footer(text=t("footer_text", lang))
    return embed


def render_markdown_changelog(changelog: GeneratedChangelog) -> bytes:
    """Render a standard Keep-a-Changelog UTF-8 ``CHANGELOG.md`` file in memory."""
    date_str = changelog.generated_at.strftime("%Y-%m-%d")
    lines = [
        f"# Changelog — {changelog.project_name}",
        "",
        f"## [{changelog.version_label}] - {date_str}",
        f"> Scope: {changelog.period_label} | Completed tasks: {changelog.total_tasks}",
        "",
    ]
    if changelog.total_tasks == 0:
        lines.append("_No completed tasks recorded in this release window._")
    else:
        for cat in ORDERED_CATEGORIES:
            entries = changelog.grouped.get(cat, [])
            if not entries:
                continue
            lines.append(f"### {CATEGORY_HEADINGS[cat]}")
            for entry in entries:
                lines.append(entry.format_bullet())
            lines.append("")

    return "\n".join(lines).encode("utf-8")


async def set_release_channel(
    project_id: int,
    guild_id: str,
    channel_id: int,
    actor_id: str,
    is_guild_admin: bool = False,
) -> None:
    """Configure per-project release announcement channel (Lead / Owner / Admin)."""
    from collaboration import service as collab_service

    proj = await collab_service.get_project(project_id, guild_id)
    try:
        await collab_service.require_role(proj, actor_id, "lead", is_guild_admin=is_guild_admin)
    except collab_service.ProjectPermissionError:
        raise ChangelogError("proj_no_permission")

    await db.aexecute(
        "UPDATE projects SET release_channel_id = $1, updated_at = NOW() WHERE project_id = $2 AND guild_id = $3",
        (channel_id, project_id, guild_id),
    )
    await db.set_guild_setting(guild_id, "releases_channel_id", str(channel_id))
    db.query_cache.invalidate_tables(["projects", "guild_settings"])


async def resolve_releases_channel(
    guild: discord.Guild,
    project_id: int,
) -> Optional[discord.TextChannel]:
    """Resolve target release channel: project.release_channel_id -> guild setting -> #releases -> project.channel_id."""
    row = await db.afetchone(
        "SELECT release_channel_id, channel_id FROM projects WHERE project_id = $1",
        (project_id,),
    )
    candidate_ids: list[int] = []
    if row:
        if row.get("release_channel_id"):
            candidate_ids.append(int(row["release_channel_id"]))

    guild_rel = await db.get_guild_setting(str(guild.id), "releases_channel_id")
    if guild_rel and str(guild_rel).isdigit():
        candidate_ids.append(int(guild_rel))

    for cid in candidate_ids:
        ch = guild.get_channel(cid)
        if isinstance(ch, discord.TextChannel):
            return ch

    for ch in guild.text_channels:
        if ch.name.lower() in ("releases", "release-notes", "changelog"):
            return ch

    if row and row.get("channel_id"):
        ch = guild.get_channel(int(row["channel_id"]))
        if isinstance(ch, discord.TextChannel):
            return ch
    return None

