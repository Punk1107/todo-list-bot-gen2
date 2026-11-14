"""
handlers/help_ui.py — Interactive Discord UI & Embed Renderers for /help.

Supports:
  - 12-domain browsable catalog with automatic pagination (<= 25 options/fields)
  - Command Detail Cards with syntax, required/optional params, examples & related commands
  - Live Search Modal + result picker dropdown (TH/EN keyword matching)
  - Role-based Workflow Playbooks (Personal, Team Lead, Agile Sprint, Server Admin)
  - Automatic Custom Theme palette color + Compact/Detailed density sync
  - Full backward compatibility with `build_help_embed(category, lang)` & `HelpCategorySelect(lang)`
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Optional

import discord
from discord import ui

from core.config import config
from handlers.help_registry import (
    CATEGORY_MAP,
    HELP_CATEGORIES,
    HELP_WORKFLOWS,
    WORKFLOW_MAP,
    HelpCommandMeta,
    count_commands_for_category,
    get_category_meta,
    get_command_meta,
    get_commands_for_category,
    paginate_commands,
    search_help_commands,
)
from locales.i18n import t

DEFAULT_HELP_COLOR = 0x5865F2


def _clip(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max(1, max_len - 1)].rstrip() + "…"


def _strip_leading_emoji(label: str, emoji: str) -> str:
    text = label.strip()
    if emoji and text.startswith(emoji):
        return text[len(emoji) :].strip()
    return text


def _scope_label(scope: str, lang: str) -> str:
    key = f"help_scope_{scope}"
    val = t(key, lang)
    if val != key:
        return val
    return scope.title()


def user_has_admin_access(interaction: discord.Interaction) -> bool:
    """Return True if caller is a Bot Owner or holds guild Administrator / Manage Server."""
    if interaction.user.id in config.bot.owner_ids:
        return True
    perms = getattr(interaction.user, "guild_permissions", None)
    if perms and (perms.administrator or perms.manage_guild):
        return True
    return False


def _total_page_size(compact: bool) -> int:
    return 12 if compact else 7


# ─────────────────────────────────────────────────────────────────────────────
# Embed Renderers
# ─────────────────────────────────────────────────────────────────────────────

def _build_overview_embed(
    lang: str,
    *,
    color: int,
    include_admin: bool,
) -> discord.Embed:
    total_cmds = count_commands_for_category("overview", include_admin=include_admin)
    badge = (
        f"**{total_cmds}** คำสั่ง / Triggers · **12** หมวดหมู่"
        if lang == "th"
        else f"**{total_cmds}** commands & triggers · **12** categories"
    )
    embed = discord.Embed(
        title=_clip(t("help_title", lang), 256),
        description=_clip(f"{t('help_desc', lang)}\n{badge}", 4096),
        color=color,
    )
    embed.add_field(
        name=_clip(t("help_quickstart_title", lang), 256),
        value=_clip(t("help_quickstart", lang), 1024),
        inline=False,
    )

    browse_cats = [c for c in HELP_CATEGORIES if c.key != "overview"]
    midpoint = (len(browse_cats) + 1) // 2
    col_a = []
    col_b = []
    for idx, cat in enumerate(browse_cats):
        clean_name = _strip_leading_emoji(cat.label(lang), cat.emoji)
        count = count_commands_for_category(cat.key, include_admin=include_admin)
        line = f"{cat.emoji} **{clean_name}** ({count})"
        if idx < midpoint:
            col_a.append(line)
        else:
            col_b.append(line)

    embed.add_field(
        name=_clip(t("help_browse_title", lang) + " (1/2)", 256),
        value=_clip("\n".join(col_a), 1024),
        inline=True,
    )
    embed.add_field(
        name=_clip(t("help_browse_title", lang) + " (2/2)", 256),
        value=_clip("\n".join(col_b), 1024),
        inline=True,
    )
    embed.add_field(
        name=_clip(t("help_overview_playbooks_title", lang), 256),
        value=_clip(t("help_overview_playbooks", lang), 1024),
        inline=False,
    )
    embed.set_footer(text=_clip(t("help_version_footer", lang), 2048))
    return embed


def _build_tips_embed(lang: str, *, color: int) -> discord.Embed:
    cat_meta = get_category_meta("tips")
    title = _strip_leading_emoji(cat_meta.label(lang), cat_meta.emoji)
    embed = discord.Embed(
        title=_clip(f"{cat_meta.emoji} {title}", 256),
        description=_clip(cat_meta.description(lang), 4096),
        color=color,
    )
    tips = [
        (t("help_tip_shorthand_title", lang), t("help_tip_shorthand", lang)),
        (t("help_tip_autocomplete_title", lang), t("help_tip_autocomplete", lang)),
        (t("help_tip_dropdown_title", lang), t("help_tip_dropdown", lang)),
        (t("help_tip_snooze_title", lang), t("help_tip_snooze", lang)),
        (t("help_tip_dm_title", lang), t("help_tip_dm", lang)),
        (t("help_tip_quickcapture_title", lang), t("help_tip_quickcapture", lang)),
        (t("help_tip_themes_title", lang), t("help_tip_themes", lang)),
    ]
    for tip_title, tip_body in tips:
        embed.add_field(
            name=_clip(tip_title, 256),
            value=_clip(f"> {tip_body}", 1024),
            inline=False,
        )
    embed.set_footer(text=_clip(t("help_version_footer", lang), 2048))
    return embed


def _add_compact_subgroup_fields(
    embed: discord.Embed,
    items: list[HelpCommandMeta],
    lang: str,
) -> None:
    grouped: OrderedDict[str, list[str]] = OrderedDict()
    for cmd in items:
        group_name = cmd.subgroup or "Commands"
        admin_tag = " 🔐" if cmd.is_admin else ""
        line = f"{cmd.emoji} **`{cmd.display_command}`**{admin_tag} — {cmd.description(lang)}"
        grouped.setdefault(group_name, []).append(_clip(line, 240))

    for group_name, lines in grouped.items():
        chunk: list[str] = []
        chunk_len = 0
        part = 1
        for line in lines:
            if chunk and chunk_len + len(line) + 1 > 960:
                header = group_name if part == 1 else f"{group_name} ({part})"
                embed.add_field(name=_clip(header, 256), value="\n".join(chunk), inline=False)
                chunk = [line]
                chunk_len = len(line)
                part += 1
            else:
                chunk.append(line)
                chunk_len += len(line) + 1
        if chunk:
            header = group_name if part == 1 else f"{group_name} ({part})"
            embed.add_field(name=_clip(header, 256), value="\n".join(chunk), inline=False)


def build_help_embed(
    category: str,
    lang: str,
    *,
    page: int = 1,
    compact: bool = False,
    color: Optional[int] = None,
    include_admin: bool = True,
) -> discord.Embed:
    """
    Build a Discord-limit-safe Embed for `/help`.

    Preserves the historical 2-argument call `build_help_embed(category, lang)`
    while supporting pagination, compact mobile layout, custom theme palette
    color, and optional admin command filtering.
    """
    embed_color = color if color is not None else DEFAULT_HELP_COLOR
    cat_key = category if category in CATEGORY_MAP else "overview"

    if cat_key == "overview":
        return _build_overview_embed(lang, color=embed_color, include_admin=include_admin)
    if cat_key == "tips":
        return _build_tips_embed(lang, color=embed_color)

    cat_meta = get_category_meta(cat_key)
    cat_title = _strip_leading_emoji(cat_meta.label(lang), cat_meta.emoji)
    cmds = get_commands_for_category(cat_key, include_admin=include_admin)
    page_items, clamped_page, total_pages = paginate_commands(
        cmds, page=page, page_size=_total_page_size(compact)
    )

    page_suffix = f" ({clamped_page}/{total_pages})" if total_pages > 1 else ""
    embed = discord.Embed(
        title=_clip(f"{cat_meta.emoji} {cat_title}{page_suffix}", 256),
        description=_clip(cat_meta.description(lang), 4096),
        color=embed_color,
    )

    if not page_items:
        empty_msg = (
            "ไม่มีคำสั่งที่แสดงในตัวกรองปัจจุบัน ลองเปิดการแสดงคำสั่ง Admin ด้านล่าง"
            if lang == "th"
            else "No commands match the current visibility filter."
        )
        embed.add_field(name="ℹ️", value=empty_msg, inline=False)
    elif compact:
        _add_compact_subgroup_fields(embed, page_items, lang)
    else:
        for cmd in page_items:
            admin_badge = " 🔐" if cmd.is_admin else ""
            field_name = _clip(f"{cmd.emoji} `{cmd.syntax()}`{admin_badge}", 256)
            desc = cmd.description(lang)
            if cmd.example:
                ex_line = f"\n`{cmd.example}`"
                value = _clip(f"> {desc}{ex_line}", 1024)
            else:
                value = _clip(f"> {desc}", 1024)
            embed.add_field(name=field_name, value=value, inline=False)

    footer_text = (
        f"{t('help_version_footer', lang)} • Page {clamped_page}/{total_pages} ({len(cmds)})"
    )
    embed.set_footer(text=_clip(footer_text, 2048))
    return embed


def build_command_detail_embed(
    entry: HelpCommandMeta,
    lang: str,
    *,
    color: Optional[int] = None,
) -> discord.Embed:
    """Render an in-depth Command Detail Card for a single command/trigger."""
    embed_color = color if color is not None else DEFAULT_HELP_COLOR
    cat_meta = get_category_meta(entry.category)
    cat_name = _strip_leading_emoji(cat_meta.label(lang), cat_meta.emoji)

    embed = discord.Embed(
        title=_clip(f"{entry.emoji} {entry.display_command}", 256),
        description=_clip(f"{entry.description(lang)}\n\n{cat_meta.emoji} **{cat_name}** · {entry.subgroup}", 4096),
        color=embed_color,
    )
    embed.add_field(
        name=_clip(t("help_detail_syntax", lang), 256),
        value=_clip(f"`{entry.syntax()}`", 1024),
        inline=False,
    )

    if entry.params:
        param_lines = []
        for p in entry.params:
            req_tag = " *(required)*" if p.endswith("*") else " *(optional)*"
            if lang == "th":
                req_tag = " *(จำเป็น)*" if p.endswith("*") else " *(ไม่บังคับ)*"
            param_lines.append(f"• `{p.rstrip('*')}`{req_tag}")
        params_val = "\n".join(param_lines)
    else:
        params_val = t("help_detail_no_params", lang)
    embed.add_field(
        name=_clip(t("help_detail_params", lang), 256),
        value=_clip(params_val, 1024),
        inline=False,
    )

    if entry.example:
        embed.add_field(
            name=_clip(t("help_detail_example", lang), 256),
            value=_clip(f"`{entry.example}`", 1024),
            inline=False,
        )

    embed.add_field(
        name=_clip(t("help_detail_scope", lang), 256),
        value=_clip(_scope_label(entry.scope, lang), 1024),
        inline=True,
    )

    if entry.related:
        rel_items = []
        for rel_path in entry.related:
            rel_meta = get_command_meta(rel_path)
            rel_items.append(f"`{rel_meta.display_command if rel_meta else '/' + rel_path}`")
        embed.add_field(
            name=_clip(t("help_detail_related", lang), 256),
            value=_clip(", ".join(rel_items), 1024),
            inline=True,
        )

    embed.set_footer(text=_clip(t("help_version_footer", lang), 2048))
    return embed


def build_search_results_embed(
    query: str,
    results: list[HelpCommandMeta],
    lang: str,
    *,
    color: Optional[int] = None,
) -> discord.Embed:
    """Render command search hits inside a clean paginated-friendly embed."""
    embed_color = color if color is not None else DEFAULT_HELP_COLOR
    embed = discord.Embed(
        title=_clip(t("help_search_results_title", lang, query=query), 256),
        color=embed_color,
    )
    if not results:
        embed.description = _clip(t("help_search_no_results", lang, query=query), 4096)
        embed.add_field(
            name=_clip(t("help_quickstart_title", lang), 256),
            value=_clip(t("help_overview_playbooks", lang), 1024),
            inline=False,
        )
        embed.set_footer(text=_clip(t("help_version_footer", lang), 2048))
        return embed

    embed.description = _clip(
        t("help_search_results_desc", lang, count=len(results)), 4096
    )
    for cmd in results[:10]:
        admin_badge = " 🔐" if cmd.is_admin else ""
        embed.add_field(
            name=_clip(f"{cmd.emoji} `{cmd.display_command}`{admin_badge}", 256),
            value=_clip(f"> {cmd.description(lang)}", 1024),
            inline=False,
        )
    embed.set_footer(text=_clip(t("help_version_footer", lang), 2048))
    return embed


def build_workflow_embed(
    workflow_key: Optional[str],
    lang: str,
    *,
    color: Optional[int] = None,
) -> discord.Embed:
    """Render Role-Based Workflow Playbooks (summary or one selected playbook)."""
    embed_color = color if color is not None else DEFAULT_HELP_COLOR
    wf = WORKFLOW_MAP.get(workflow_key or "")
    if wf is None:
        embed = discord.Embed(
            title=_clip(t("help_workflows_title", lang), 256),
            description=_clip(t("help_workflows_desc", lang), 4096),
            color=embed_color,
        )
        for item in HELP_WORKFLOWS:
            steps_preview = "\n".join(item.steps(lang))
            embed.add_field(
                name=_clip(f"{item.emoji} {item.title(lang)}", 256),
                value=_clip(f"*{item.audience(lang)}*\n{steps_preview}", 1024),
                inline=False,
            )
        embed.set_footer(text=_clip(t("help_version_footer", lang), 2048))
        return embed

    embed = discord.Embed(
        title=_clip(f"{wf.emoji} {wf.title(lang)}", 256),
        description=_clip(wf.audience(lang), 4096),
        color=embed_color,
    )
    embed.add_field(
        name=_clip(t("help_workflows_title", lang), 256),
        value=_clip("\n".join(wf.steps(lang)), 1024),
        inline=False,
    )
    embed.set_footer(text=_clip(t("help_version_footer", lang), 2048))
    return embed


# ─────────────────────────────────────────────────────────────────────────────
# Interactive Discord UI Components
# ─────────────────────────────────────────────────────────────────────────────

class HelpCategorySelect(ui.Select):
    """Category dropdown supporting all 12 command domains (backward compatible)."""

    def __init__(
        self,
        lang: str,
        current_category: str = "overview",
        *,
        include_admin: bool = True,
    ) -> None:
        self.lang = lang
        options = []
        for cat in HELP_CATEGORIES:
            clean_label = _strip_leading_emoji(cat.label(lang), cat.emoji)
            cmd_count = count_commands_for_category(cat.key, include_admin=include_admin)
            opt_desc = _clip(f"({cmd_count}) {cat.description(lang)}", 100)
            options.append(
                discord.SelectOption(
                    label=_clip(clean_label, 100),
                    value=cat.key,
                    emoji=cat.emoji,
                    description=opt_desc,
                    default=(cat.key == current_category),
                )
            )
        super().__init__(
            placeholder=_clip(t("help_category_select_placeholder", lang), 150),
            options=options,
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        val = self.values[0]
        if isinstance(self.view, HelpView):
            await self.view.switch_category(interaction, val)
            return
        for opt in self.options:
            opt.default = (opt.value == val)
        embed = build_help_embed(val, self.lang)
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpSearchResultSelect(ui.Select):
    """Dropdown allowing user to drill into any matching command from search results."""

    def __init__(self, results: list[HelpCommandMeta], lang: str) -> None:
        self.lang = lang
        options = [
            discord.SelectOption(
                label=_clip(cmd.display_command, 100),
                value=cmd.path,
                emoji=cmd.emoji,
                description=_clip(cmd.description(lang), 100),
            )
            for cmd in results[:25]
        ]
        super().__init__(
            placeholder=_clip(t("help_search_select_placeholder", lang), 150),
            options=options,
            min_values=1,
            max_values=1,
            row=3,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if isinstance(self.view, HelpView):
            await self.view.open_command_detail(interaction, self.values[0])


class HelpWorkflowSelect(ui.Select):
    """Dropdown to switch between role-based workflow playbooks."""

    def __init__(self, lang: str, current_wf: Optional[str] = None) -> None:
        self.lang = lang
        options = [
            discord.SelectOption(
                label=_clip(wf.title(lang), 100),
                value=wf.key,
                emoji=wf.emoji,
                description=_clip(wf.audience(lang), 100),
                default=(wf.key == current_wf),
            )
            for wf in HELP_WORKFLOWS
        ]
        super().__init__(
            placeholder=_clip(t("help_workflow_select_placeholder", lang), 150),
            options=options,
            min_values=1,
            max_values=1,
            row=3,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if isinstance(self.view, HelpView):
            await self.view.open_workflow(interaction, self.values[0])


class HelpSearchModal(ui.Modal):
    """Modal dialog for fuzzy command search across Thai & English descriptions."""

    def __init__(self, help_view: HelpView) -> None:
        super().__init__(title=_clip(t("help_search_modal_title", help_view.lang), 45))
        self.help_view = help_view
        self.query_input = ui.TextInput(
            label=_clip(t("help_search_input_label", help_view.lang), 45),
            placeholder=_clip(t("help_search_input_placeholder", help_view.lang), 100),
            max_length=80,
            required=True,
        )
        self.add_item(self.query_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.help_view.run_search(interaction, str(self.query_input.value))


class HelpView(ui.View):
    """Stateful interactive Help Center View with pagination, search, density & admin toggle."""

    def __init__(
        self,
        lang: str,
        *,
        author_id: Optional[int] = None,
        category: str = "overview",
        page: int = 1,
        compact: bool = False,
        include_admin: bool = True,
        color: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.lang = lang
        self.author_id = author_id
        self.category = category if category in CATEGORY_MAP else "overview"
        self.page = page
        self.compact = compact
        self.include_admin = include_admin
        self.color = color
        self.mode: str = "category"  # category | detail | search | workflows
        self.detail_path: Optional[str] = None
        self.search_query: str = ""
        self.search_results: list[HelpCommandMeta] = []
        self.workflow_key: Optional[str] = None
        self._message: Optional[discord.Message] = None
        self._rebuild_items()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id is not None and interaction.user.id != self.author_id:
            await interaction.response.send_message(
                t("help_not_author", self.lang),
                ephemeral=True,
            )
            return False
        return True

    def _current_page_bounds(self) -> tuple[int, int]:
        if self.mode != "category" or self.category in ("overview", "tips"):
            return 1, 1
        cmds = get_commands_for_category(self.category, include_admin=self.include_admin)
        _, clamped, total_pages = paginate_commands(
            cmds, page=self.page, page_size=_total_page_size(self.compact)
        )
        return clamped, total_pages

    def render_current_embed(self) -> discord.Embed:
        if self.mode == "detail" and self.detail_path:
            entry = get_command_meta(self.detail_path)
            if entry:
                return build_command_detail_embed(entry, self.lang, color=self.color)
        if self.mode == "search":
            return build_search_results_embed(
                self.search_query, self.search_results, self.lang, color=self.color
            )
        if self.mode == "workflows":
            return build_workflow_embed(self.workflow_key, self.lang, color=self.color)
        return build_help_embed(
            self.category,
            self.lang,
            page=self.page,
            compact=self.compact,
            color=self.color,
            include_admin=self.include_admin,
        )

    def _rebuild_items(self) -> None:
        self.clear_items()
        clamped_page, total_pages = self._current_page_bounds()
        self.page = clamped_page

        # Row 0: Category selector
        self.add_item(
            HelpCategorySelect(
                self.lang,
                current_category=self.category,
                include_admin=self.include_admin,
            )
        )

        # Row 1: Pagination + Search + Playbooks
        prev_btn = ui.Button(
            label=t("help_btn_prev", self.lang),
            emoji="◀️",
            style=discord.ButtonStyle.secondary,
            disabled=(self.mode != "category" or total_pages <= 1 or clamped_page <= 1),
            row=1,
        )
        prev_btn.callback = self._on_prev
        self.add_item(prev_btn)

        page_label = f"{clamped_page}/{total_pages}" if self.mode == "category" else self.mode.title()
        badge_btn = ui.Button(
            label=page_label,
            emoji="📄",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=1,
        )
        self.add_item(badge_btn)

        next_btn = ui.Button(
            label=t("help_btn_next", self.lang),
            emoji="▶️",
            style=discord.ButtonStyle.secondary,
            disabled=(self.mode != "category" or total_pages <= 1 or clamped_page >= total_pages),
            row=1,
        )
        next_btn.callback = self._on_next
        self.add_item(next_btn)

        search_btn = ui.Button(
            label=t("help_btn_search", self.lang),
            emoji="🔍",
            style=discord.ButtonStyle.primary,
            row=1,
        )
        search_btn.callback = self._on_search
        self.add_item(search_btn)

        wf_btn = ui.Button(
            label=t("help_btn_workflows", self.lang),
            emoji="🧭",
            style=discord.ButtonStyle.primary if self.mode != "workflows" else discord.ButtonStyle.success,
            row=1,
        )
        wf_btn.callback = self._on_workflows
        self.add_item(wf_btn)

        # Row 2: Quick controls (Overview, Density, Admin Filter, Back)
        home_btn = ui.Button(
            label=t("help_btn_home", self.lang),
            emoji="🏠",
            style=discord.ButtonStyle.secondary,
            disabled=(self.mode == "category" and self.category == "overview"),
            row=2,
        )
        home_btn.callback = self._on_home
        self.add_item(home_btn)

        density_btn = ui.Button(
            label=t("help_btn_detailed" if self.compact else "help_btn_compact", self.lang),
            emoji="📖" if self.compact else "📱",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        density_btn.callback = self._on_toggle_density
        self.add_item(density_btn)

        admin_btn = ui.Button(
            label=t("help_btn_admin_show" if self.include_admin else "help_btn_admin_hide", self.lang),
            emoji="🔐",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        admin_btn.callback = self._on_toggle_admin
        self.add_item(admin_btn)

        if self.mode != "category":
            back_btn = ui.Button(
                label=t("help_btn_back_category", self.lang),
                emoji="↩️",
                style=discord.ButtonStyle.secondary,
                row=2,
            )
            back_btn.callback = self._on_back_category
            self.add_item(back_btn)

        # Row 3: Contextual Picker for Search Results or Workflow Playbooks
        if self.mode == "search" and self.search_results:
            self.add_item(HelpSearchResultSelect(self.search_results, self.lang))
        elif self.mode == "workflows":
            self.add_item(HelpWorkflowSelect(self.lang, current_wf=self.workflow_key))

    async def _refresh_message(self, interaction: discord.Interaction) -> None:
        self._rebuild_items()
        embed = self.render_current_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def switch_category(self, interaction: discord.Interaction, category: str) -> None:
        self.category = category if category in CATEGORY_MAP else "overview"
        self.mode = "category"
        self.page = 1
        await self._refresh_message(interaction)

    async def open_command_detail(self, interaction: discord.Interaction, command_path: str) -> None:
        entry = get_command_meta(command_path)
        if entry is not None:
            self.category = entry.category
            self.detail_path = entry.path
            self.mode = "detail"
        await self._refresh_message(interaction)

    async def open_workflow(self, interaction: discord.Interaction, workflow_key: Optional[str]) -> None:
        self.mode = "workflows"
        self.workflow_key = workflow_key
        await self._refresh_message(interaction)

    async def run_search(self, interaction: discord.Interaction, query: str) -> None:
        self.search_query = query.strip()
        exact = get_command_meta(self.search_query)
        if exact and (self.include_admin or not exact.is_admin):
            self.category = exact.category
            self.detail_path = exact.path
            self.mode = "detail"
        else:
            matches = search_help_commands(
                self.search_query, self.lang, include_admin=self.include_admin, limit=25
            )
            if len(matches) == 1:
                self.category = matches[0].category
                self.detail_path = matches[0].path
                self.mode = "detail"
            else:
                self.search_results = matches
                self.mode = "search"
        await self._refresh_message(interaction)

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        self.page = max(1, self.page - 1)
        await self._refresh_message(interaction)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        self.page += 1
        await self._refresh_message(interaction)

    async def _on_search(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(HelpSearchModal(self))

    async def _on_workflows(self, interaction: discord.Interaction) -> None:
        self.mode = "workflows"
        self.workflow_key = None
        await self._refresh_message(interaction)

    async def _on_home(self, interaction: discord.Interaction) -> None:
        await self.switch_category(interaction, "overview")

    async def _on_toggle_density(self, interaction: discord.Interaction) -> None:
        self.compact = not self.compact
        self.page = 1
        await self._refresh_message(interaction)

    async def _on_toggle_admin(self, interaction: discord.Interaction) -> None:
        self.include_admin = not self.include_admin
        self.page = 1
        await self._refresh_message(interaction)

    async def _on_back_category(self, interaction: discord.Interaction) -> None:
        self.mode = "category"
        await self._refresh_message(interaction)

    async def on_timeout(self) -> None:
        for child in self.children:
            try:
                child.disabled = True  # type: ignore[attr-defined]
            except Exception:
                pass
        try:
            if self._message:
                await self._message.edit(view=self)
        except Exception:
            pass
