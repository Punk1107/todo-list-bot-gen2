"""
handlers/settings_cog.py — Setup, language, category, and admin commands v4 (PostgreSQL)
Changes over v3:
  - SQL placeholders: ? → $N (PostgreSQL/asyncpg)
  - category_created: INSERT ... RETURNING category_id (replaces cur.lastrowid)
  - admin_stats: 5 separate queries → 1 aggregate query
  - admin_backup: removed (Supabase manages backups automatically)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands, ui
from discord.ext import commands
import pytz

from core.database import db
from core.security import rate_limit_check, validator
from core.config import config
from locales.i18n import t, SUPPORTED_LANGS, locale_to_lang
from utils.helpers import (
    get_user_lang, get_user_timezone, get_user_role, get_user_theme,
    get_user_display_mode, set_user_display_mode,
    ensure_user, save_user_settings,
)
from core.theme import (
    EMOJI_PRESETS,
    THEMES,
    VALID_PROGRESS_STYLES,
    activate_user_custom_theme,
    delete_user_custom_theme,
    get_theme,
    hex_to_int,
    list_themes,
    list_user_custom_themes,
    normalize_hex_color,
    render_progress_bar,
    resolve_user_palette,
    save_guild_theme,
    save_user_custom_theme,
    set_user_theme,
)
from handlers.task_views import LanguageView

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Admin check helper
# ─────────────────────────────────────────────────────────────────────────────

def _is_owner(user_id: int) -> bool:
    return user_id in config.bot.owner_ids


# ─────────────────────────────────────────────────────────────────────────────
# Category modals
# ─────────────────────────────────────────────────────────────────────────────

class AddCategoryModal(discord.ui.Modal):
    def __init__(self, lang: str) -> None:
        super().__init__(title=t("cat_add_title", lang))
        self.lang = lang
        self.cat_name = discord.ui.TextInput(
            label=t("cat_name_label", lang),
            max_length=50, required=True,
        )
        self.cat_emoji = discord.ui.TextInput(
            label=t("cat_emoji_label", lang),
            max_length=8, required=False, default="📝",
        )
        self.add_item(self.cat_name)
        self.add_item(self.cat_emoji)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        uid  = str(interaction.user.id)
        lang = self.lang
        name = validator.sanitize(self.cat_name.value, 50)
        if not name:
            await interaction.response.send_message(t("err_input_invalid", lang, detail="name"), ephemeral=True)
            return
        if validator.is_suspicious(name):
            await interaction.response.send_message(t("err_suspicious", lang), ephemeral=True)
            return
        emoji = (self.cat_emoji.value or "📝").strip() or "📝"
        await ensure_user(uid, lang)
        try:
            # RETURNING lets us get the new ID without lastrowid (not supported by asyncpg)
            row = await db.afetchone(
                "INSERT INTO categories (name, emoji, owner_id) VALUES ($1,$2,$3) RETURNING category_id",
                (name, emoji, uid),
            )
            new_id = row["category_id"] if row else None
            await db.alog_action(uid, "category_created", str(new_id), name)
            await interaction.response.send_message(
                t("cat_created", lang, name=f"{emoji} {name}"), ephemeral=True
            )
        except Exception as exc:
            log.error("Category create failed: %s", exc)
            await interaction.response.send_message(t("err_db", lang), ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.error("AddCategoryModal error: %s", error)
        lang = await get_user_lang(interaction.user.id)
        await interaction.response.send_message(t("err_generic", lang), ephemeral=True)


# ─────────────────────────────────────────────────────────────────────────────
# Help UI Components (Modularized in handlers/help_registry.py & help_ui.py)
# Re-exported here to preserve backward-compatible imports.
# ─────────────────────────────────────────────────────────────────────────────

from handlers.help_registry import (
    HELP_CATEGORIES,
    get_command_meta,
    search_help_commands,
)
from handlers.help_ui import (
    HelpCategorySelect,
    HelpView,
    build_command_detail_embed,
    build_help_embed,
    build_search_results_embed,
    user_has_admin_access,
)


# ─────────────────────────────────────────────────────────────────────────────
# Theme Personalization UI Components
# ─────────────────────────────────────────────────────────────────────────────

def build_theme_preview_embed(theme_key: str, lang: str) -> discord.Embed:
    theme = get_theme(theme_key)
    embed = discord.Embed(
        title=f"🎨 {theme.emoji} {theme.name}",
        description=f"> *{theme.description}*\n\n{t('theme_preview_body', lang)}",
        color=theme.color_int,
    )
    sample_field = t("theme_preview_field", lang) if t("theme_preview_field", lang) != "theme_preview_field" else "📋 Sample Task Preview"
    embed.add_field(
        name=sample_field,
        value=f"• 🔴 **#101** Production Bug Hotfix\n• 📅 Tomorrow at 15:00\n• ⚡ Status: `In_Progress`",
        inline=False,
    )
    embed.set_footer(text=f"Color: {theme.color_hex} • {t('footer_text', lang)}")
    return embed


class ThemeSelectView(discord.ui.View):
    def __init__(self, user_id: str, current_theme: str, lang: str, timeout: float = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.selected_theme = current_theme
        self.lang = lang
        self._message: Optional[discord.InteractionMessage] = None
        self._build_components()

    def _build_components(self) -> None:
        self.clear_items()
        options = []
        for th in list_themes():
            is_def = (th.key == self.selected_theme)
            options.append(
                discord.SelectOption(
                    label=f"{th.emoji} {th.name}",
                    value=th.key,
                    description=th.description[:50],
                    default=is_def,
                )
            )

        placeholder = t("theme_select_placeholder", self.lang)
        if placeholder == "theme_select_placeholder":
            placeholder = "Select your preferred color theme..."

        select = discord.ui.Select(
            placeholder=placeholder,
            options=options,
            row=0,
        )
        select.callback = self._on_select_theme
        self.add_item(select)

        save_label = t("confirm", self.lang)
        btn_save = discord.ui.Button(
            label=save_label,
            emoji="💾",
            style=discord.ButtonStyle.success,
            row=1,
        )
        btn_save.callback = self._on_save
        self.add_item(btn_save)

    async def _on_select_theme(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        self.selected_theme = interaction.data["values"][0]  # type: ignore
        self._build_components()
        embed = build_theme_preview_embed(self.selected_theme, self.lang)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_save(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        await set_user_theme(self.user_id, self.selected_theme)
        embed = build_theme_preview_embed(self.selected_theme, self.lang)
        th_name = THEMES[self.selected_theme].name if self.selected_theme in THEMES else self.selected_theme
        success_msg = t("theme_updated_success", self.lang, theme=th_name)
        await interaction.response.edit_message(
            content=f"✅ {success_msg}",
            embed=embed,
            view=None,
        )


class CustomThemeBuilderView(discord.ui.View):
    """Interactive Progress Bar Style & Emoji Set selector after hex palette input (Feature 43)."""

    def __init__(
        self,
        *,
        user_id: str,
        lang: str,
        guild_id: Optional[str],
        is_guild_scope: bool,
        name: str,
        primary_color: str,
        success_color: str,
        warning_color: str,
        danger_color: str,
    ) -> None:
        super().__init__(timeout=180)
        self.user_id = user_id
        self.lang = lang
        self.guild_id = guild_id
        self.is_guild_scope = is_guild_scope
        self.theme_name = name
        self.primary_color = primary_color
        self.success_color = success_color
        self.warning_color = warning_color
        self.danger_color = danger_color
        self.progress_style = "neon"
        self.emoji_preset = "classic"
        self._build_controls()

    def _build_controls(self) -> None:
        self.clear_items()
        style_opts = [
            discord.SelectOption(label="✨ Neon (▰▰▱▱)", value="neon", default=(self.progress_style == "neon")),
            discord.SelectOption(label="🕹️ Retro ([##--])", value="retro", default=(self.progress_style == "retro")),
            discord.SelectOption(label="⚪ Minimal (●●○○)", value="minimal", default=(self.progress_style == "minimal")),
            discord.SelectOption(label="🟩 Blocks (🟩🟩⬜⬜)", value="blocks", default=(self.progress_style == "blocks")),
        ]
        s_select = discord.ui.Select(placeholder=t("theme_style_placeholder", self.lang), options=style_opts, row=0)
        s_select.callback = self._on_style_change
        self.add_item(s_select)

        emoji_opts = [
            discord.SelectOption(label="Classic (⏳🔄✅🚨)", value="classic", default=(self.emoji_preset == "classic")),
            discord.SelectOption(label="Neon (🔮⚡💎💥)", value="neon", default=(self.emoji_preset == "neon")),
            discord.SelectOption(label="Retro (🕹️⚙️🏆👾)", value="retro", default=(self.emoji_preset == "retro")),
            discord.SelectOption(label="Minimal (○◐●!)", value="minimal", default=(self.emoji_preset == "minimal")),
        ]
        e_select = discord.ui.Select(placeholder=t("theme_emoji_placeholder", self.lang), options=emoji_opts, row=1)
        e_select.callback = self._on_emoji_change
        self.add_item(e_select)

        btn_save = discord.ui.Button(label=t("confirm", self.lang), emoji="🎨", style=discord.ButtonStyle.success, row=2)
        btn_save.callback = self._on_save
        self.add_item(btn_save)

    def make_preview_embed(self) -> discord.Embed:
        bar = render_progress_bar(70, self.progress_style, width=10)
        emojis = EMOJI_PRESETS.get(self.emoji_preset, EMOJI_PRESETS["classic"])
        embed = discord.Embed(
            title=f"🎨 {self.theme_name}",
            description=(
                f"`Primary` `{self.primary_color}` · `Success` `{self.success_color}`\n"
                f"`Warning` `{self.warning_color}` · `Danger` `{self.danger_color}`\n\n"
                f"**Progress ({self.progress_style})**: {bar} `70%`\n"
                f"**Icons**: {emojis['pending']} Pending · {emojis['in_progress']} Active · "
                f"{emojis['done']} Done · {emojis['overdue']} Overdue"
            ),
            color=hex_to_int(self.primary_color, 0x5865F2),
        )
        embed.set_footer(text=t("footer_text", self.lang))
        return embed

    async def _on_style_change(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        self.progress_style = interaction.data["values"][0]  # type: ignore[index]
        self._build_controls()
        await interaction.response.edit_message(embed=self.make_preview_embed(), view=self)

    async def _on_emoji_change(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        self.emoji_preset = interaction.data["values"][0]  # type: ignore[index]
        self._build_controls()
        await interaction.response.edit_message(embed=self.make_preview_embed(), view=self)

    async def _on_save(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(t("permission_denied", self.lang), ephemeral=True)
            return
        emojis = EMOJI_PRESETS.get(self.emoji_preset, EMOJI_PRESETS["classic"])
        if self.is_guild_scope and self.guild_id:
            palette = await save_guild_theme(
                self.guild_id,
                self.user_id,
                name=self.theme_name,
                primary_color=self.primary_color,
                success_color=self.success_color,
                warning_color=self.warning_color,
                danger_color=self.danger_color,
                progress_style=self.progress_style,
                emoji_set=emojis,
            )
        else:
            palette = await save_user_custom_theme(
                self.user_id,
                self.theme_name,
                primary_color=self.primary_color,
                success_color=self.success_color,
                warning_color=self.warning_color,
                danger_color=self.danger_color,
                progress_style=self.progress_style,
                emoji_set=emojis,
                activate=True,
            )
        await interaction.response.edit_message(
            content=f"✅ {t('theme_custom_saved', self.lang, name=palette.name)}",
            embed=self.make_preview_embed(),
            view=None,
        )


class CustomThemeModal(discord.ui.Modal):
    """Modal collecting hex colors (#RRGGBB) for Custom Theme Creator (Feature 43)."""

    def __init__(
        self,
        *,
        user_id: str,
        lang: str,
        guild_id: Optional[str] = None,
        is_guild_scope: bool = False,
    ) -> None:
        super().__init__(title=t("theme_modal_title", lang)[:45])
        self.user_id = user_id
        self.lang = lang
        self.guild_id = guild_id
        self.is_guild_scope = is_guild_scope

        self.theme_name = discord.ui.TextInput(
            label=t("theme_modal_name_label", lang)[:45],
            default="Server Theme" if is_guild_scope else "My Custom Palette",
            required=True,
            max_length=40,
        )
        self.primary_hex = discord.ui.TextInput(
            label="Primary Hex (#5865F2)",
            default="#5865F2",
            required=True,
            max_length=7,
        )
        self.success_hex = discord.ui.TextInput(
            label="Success Hex (#57F287)",
            default="#57F287",
            required=True,
            max_length=7,
        )
        self.warning_hex = discord.ui.TextInput(
            label="Warning Hex (#FEE75C)",
            default="#FEE75C",
            required=True,
            max_length=7,
        )
        self.danger_hex = discord.ui.TextInput(
            label="Danger Hex (#ED4245)",
            default="#ED4245",
            required=True,
            max_length=7,
        )
        self.add_item(self.theme_name)
        self.add_item(self.primary_hex)
        self.add_item(self.success_hex)
        self.add_item(self.warning_hex)
        self.add_item(self.danger_hex)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            p_hex = normalize_hex_color(self.primary_hex.value)
            s_hex = normalize_hex_color(self.success_hex.value)
            w_hex = normalize_hex_color(self.warning_hex.value)
            d_hex = normalize_hex_color(self.danger_hex.value)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        builder = CustomThemeBuilderView(
            user_id=self.user_id,
            lang=self.lang,
            guild_id=self.guild_id,
            is_guild_scope=self.is_guild_scope,
            name=self.theme_name.value.strip() or "Custom",
            primary_color=p_hex,
            success_color=s_hex,
            warning_color=w_hex,
            danger_color=d_hex,
        )
        await interaction.response.send_message(
            embed=builder.make_preview_embed(), view=builder, ephemeral=True
        )


# ─────────────────────────────────────────────────────────────────────────────
# Settings Cog
# ─────────────────────────────────────────────────────────────────────────────

class SettingsCog(commands.Cog, name="Settings"):
    """Setup, language, categories, and admin commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /setup ───────────────────────────────────────────────────────────────

    @app_commands.command(name="setup", description="⚙️ ตั้งค่า Bot / Configure the bot")
    @app_commands.describe(timezone="เช่น Asia/Bangkok, UTC, America/New_York")
    @rate_limit_check("command")
    async def setup(self, interaction: discord.Interaction, timezone: str) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)

        tz_clean = validator.sanitize(timezone, 50)
        if validator.is_suspicious(tz_clean):
            await interaction.response.send_message(t("err_suspicious", lang), ephemeral=True)
            return
        try:
            pytz.timezone(tz_clean)
        except pytz.exceptions.UnknownTimeZoneError:
            await interaction.response.send_message(
                t("setup_invalid_tz", lang, tz=tz_clean), ephemeral=True
            )
            return

        # Fetch previous timezone to display transition if changed
        curr_row = await db.afetchone("SELECT timezone FROM users WHERE user_id=$1", (uid,))
        prev_tz = curr_row["timezone"] if curr_row and curr_row["timezone"] else None

        channel_id = interaction.channel_id
        await ensure_user(uid, lang)
        await save_user_settings(uid, timezone=tz_clean, channel_id=channel_id)
        await db.alog_action(uid, "setup", detail=f"tz={tz_clean}")

        ch_mention = f"<#{channel_id}>" if channel_id else "—"
        embed = discord.Embed(
            title=t("setup_title", lang),
            description=t("setup_success", lang, tz=tz_clean, channel=ch_mention),
            color=0x57F287,
        )
        # Checklist showing what's configured
        embed.add_field(
            name="✅ Setup Checklist",
            value=t("setup_checklist", lang),
            inline=False,
        )
        if prev_tz and prev_tz != tz_clean:
            tz_val = f"`{prev_tz}` ➔ **`{tz_clean}`**"
        else:
            tz_val = f"**`{tz_clean}`**"
        embed.add_field(
            name="🕒 Timezone",
            value=t("setup_current_tz", lang, tz=tz_val),
            inline=True,
        )
        embed.add_field(
            name=t("setup_lang_field", lang),
            value="Use `/lang` to switch language | ใช้ `/lang` เพื่อเปลี่ยนภาษา",
            inline=True,
        )
        embed.set_footer(text=t("footer_text", lang))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /lang ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="lang", description="🌐 เปลี่ยนภาษา / Change language / 言語変更 / 언어변경")
    @rate_limit_check("command")
    async def lang(self, interaction: discord.Interaction) -> None:
        uid          = str(interaction.user.id)
        discord_locale = str(interaction.locale)
        # For brand-new users: seed their language from Discord locale
        await ensure_user(uid, discord_locale=discord_locale)
        current_lang = await get_user_lang(uid)

        from locales.i18n import get_flag, get_lang_name
        flag = get_flag(current_lang)
        lang_name = get_lang_name(current_lang)
        active_str = t("lang_current_active", current_lang, flag=flag, name=lang_name)

        embed = discord.Embed(
            title=t("lang_select_title", current_lang),
            description=f"> **{active_str}**\n\n{t('lang_select_desc', current_lang)}",
            color=0x5865F2,
        )
        view = LanguageView(current_lang)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        # Store message so on_timeout can edit it with disabled select
        view._message = await interaction.original_response()


    # ── /help ─────────────────────────────────────────────────────────────────

    def _quick_autocomplete_lang(self, interaction: discord.Interaction) -> str:
        cached = db.user_cache.get(str(interaction.user.id))
        if cached and getattr(cached, "language", None):
            return str(cached.language)
        return locale_to_lang(str(getattr(interaction, "locale", "en")))

    @app_commands.command(name="help", description="📖 ดูวิธีใช้และค้นหาคำสั่ง / Interactive Help Center")
    @app_commands.describe(
        query="ค้นหาคำสั่งหรือฟีเจอร์ (เช่น sprint, gantt, focus) / Search command or keyword",
        category="เปิดหมวดหมู่ที่ต้องการโดยตรง / Jump directly to a category",
        ephemeral="ซ่อนให้เห็นเฉพาะคุณ (ค่าเริ่มต้น False) / Show only to you (default False)",
    )
    @rate_limit_check("command")
    async def help_cmd(
        self,
        interaction: discord.Interaction,
        query: Optional[str] = None,
        category: Optional[str] = None,
        ephemeral: bool = False,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)

        color = None
        try:
            palette = await resolve_user_palette(uid, guild_id=interaction.guild_id)
            color = palette.color_for("primary")
        except Exception:
            color = None

        compact = False
        try:
            compact = (await get_user_display_mode(uid)) == "compact"
        except Exception:
            compact = False

        include_admin = user_has_admin_access(interaction)
        target_category = category or "overview"
        bound_author = interaction.user.id if ephemeral else None
        view = HelpView(
            lang,
            author_id=bound_author,
            category=target_category,
            compact=compact,
            include_admin=include_admin,
            color=color,
            timeout=None,
        )

        if query and query.strip():
            cleaned = query.strip()
            exact = get_command_meta(cleaned)
            if exact and (include_admin or not exact.is_admin):
                view.category = exact.category
                view.detail_path = exact.path
                view.mode = "detail"
            else:
                matches = search_help_commands(
                    cleaned, lang, include_admin=include_admin, limit=25
                )
                if len(matches) == 1:
                    view.category = matches[0].category
                    view.detail_path = matches[0].path
                    view.mode = "detail"
                else:
                    view.search_query = cleaned
                    view.search_results = matches
                    view.mode = "search"
            view._rebuild_items()

        embed = view.render_current_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)
        view._message = await interaction.original_response()

    @help_cmd.autocomplete("query")
    async def help_query_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        lang = self._quick_autocomplete_lang(interaction)
        include_admin = user_has_admin_access(interaction)
        matches = search_help_commands(current, lang, include_admin=include_admin, limit=25)
        choices: list[app_commands.Choice[str]] = []
        for entry in matches[:25]:
            label = f"{entry.emoji} {entry.display_command} — {entry.description(lang)}"
            if len(label) > 100:
                label = label[:99].rstrip() + "…"
            choices.append(app_commands.Choice(name=label, value=entry.path))
        return choices

    @help_cmd.autocomplete("category")
    async def help_category_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        lang = self._quick_autocomplete_lang(interaction)
        q = current.strip().lower()
        choices: list[app_commands.Choice[str]] = []
        for cat in HELP_CATEGORIES:
            label_text = cat.label(lang)
            if not q or q in cat.key or q in label_text.lower() or q in cat.description(lang).lower():
                name = label_text if label_text.startswith(cat.emoji) else f"{cat.emoji} {label_text}"
                choices.append(app_commands.Choice(name=name[:100], value=cat.key))
        return choices[:25]


    # ── /theme group & /settings theme + /settings display ────────────────────

    settings_group = app_commands.Group(
        name="settings",
        description="⚙️ ตั้งค่าระบบ / Bot settings",
    )

    @settings_group.command(name="theme", description="🎨 ปรับแต่งสี Embed / Personalize embed theme")
    @app_commands.describe(theme="เลือกธีมสีประจำตัว / Choose embed theme")
    @rate_limit_check("command")
    async def settings_theme(
        self, interaction: discord.Interaction, theme: Optional[str] = None
    ) -> None:
        await self._handle_theme_cmd(interaction, theme)

    @settings_group.command(
        name="display",
        description="📱 สลับโหมดแสดงผล (Standard / Compact สำหรับมือถือ) / Toggle display view mode",
    )
    @app_commands.describe(mode="เลือกรูปแบบการแสดงผลรายการงาน / Task list display density")
    @app_commands.choices(mode=[
        app_commands.Choice(name="🖥️ Standard (แบบเต็ม พร้อมวันเวลาละเอียด)", value="standard"),
        app_commands.Choice(name="📱 Compact (1 บรรทัดต่องาน ประหยัดพื้นที่มือถือ)", value="compact"),
    ])
    @rate_limit_check("command")
    async def settings_display(
        self, interaction: discord.Interaction, mode: Optional[str] = None
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)

        if mode is None:
            current = await get_user_display_mode(uid)
            await interaction.response.send_message(
                t("display_mode_current", lang, mode=current), ephemeral=True
            )
            return

        saved = await set_user_display_mode(uid, mode)
        await interaction.response.send_message(
            f"✅ {t('display_mode_updated', lang, mode=saved)}", ephemeral=True
        )

    theme_group = app_commands.Group(
        name="theme",
        description="🎨 ปรับแต่งสี ธีม และสร้างจานสี Hex ประจำตัว / Personalize & create custom palettes",
    )

    @theme_group.command(name="select", description="🎨 เลือกใช้ธีมสีที่บันทึกไว้ / Select preset or custom theme")
    @app_commands.describe(theme="ชื่อธีม / Theme key or custom palette name")
    @rate_limit_check("command")
    async def theme_select(
        self, interaction: discord.Interaction, theme: Optional[str] = None
    ) -> None:
        await self._handle_theme_cmd(interaction, theme)

    @theme_group.command(name="create", description="🖌️ สร้างจานสี Hex & สไตล์ Progress Bar เอง / Create custom theme")
    @rate_limit_check("command")
    async def theme_create(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        modal = CustomThemeModal(user_id=uid, lang=lang, is_guild_scope=False)
        await interaction.response.send_modal(modal)

    @theme_group.command(
        name="guild",
        description="🏰 กำหนดธีมสีประจำเซิร์ฟเวอร์ (Admin) / Set server-wide custom palette",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @rate_limit_check("command")
    async def theme_guild(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)
        modal = CustomThemeModal(
            user_id=uid,
            lang=lang,
            guild_id=str(interaction.guild_id),
            is_guild_scope=True,
        )
        await interaction.response.send_modal(modal)

    @theme_group.command(name="list", description="🗂️ ดูรายการธีมสีของคุณและเซิร์ฟเวอร์ / List active & saved palettes")
    @rate_limit_check("command")
    async def theme_list(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        gid = str(interaction.guild_id) if interaction.guild_id else None
        await interaction.response.defer(ephemeral=True)

        palette = await resolve_user_palette(uid, guild_id=gid)
        custom_rows = await list_user_custom_themes(uid)
        lines = [
            f"**{t('theme_active_label', lang)}**: `{palette.name}` (`{palette.primary_color}`, `{palette.progress_style}`, source: `{palette.source}`)",
            "",
        ]
        if custom_rows:
            lines.append(f"**{t('theme_custom_section', lang)}**:")
            for row in custom_rows:
                mark = "✅" if row.get("is_active") else "▫️"
                lines.append(
                    f"{mark} **{row['name']}** — `{row['primary_color']}` / `{row['success_color']}` ({row['progress_style']})"
                )
        else:
            lines.append(t("theme_custom_empty", lang))

        embed = discord.Embed(
            title=t("theme_list_title", lang),
            description="\n".join(lines),
            color=palette.primary_int,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @theme_group.command(name="delete", description="🗑️ ลบธีมสีส่วนตัวที่สร้างไว้ / Delete one of your custom themes")
    @app_commands.describe(name="ชื่อธีมส่วนตัว / Custom theme name")
    @rate_limit_check("command")
    async def theme_delete(self, interaction: discord.Interaction, name: str) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await interaction.response.defer(ephemeral=True)
        deleted = await delete_user_custom_theme(uid, name)
        if not deleted:
            await interaction.followup.send(t("theme_not_found_custom", lang, name=name), ephemeral=True)
            return
        await interaction.followup.send(f"🗑️ {t('theme_custom_deleted', lang, name=name)}", ephemeral=True)

    async def _handle_theme_cmd(
        self, interaction: discord.Interaction, theme: Optional[str] = None
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid)

        if theme:
            clean_key = theme.strip().lower()
            if clean_key in THEMES:
                await set_user_theme(uid, clean_key)
                embed = build_theme_preview_embed(clean_key, lang)
                th_name = THEMES[clean_key].name
                success_msg = t("theme_updated_success", lang, theme=th_name)
                await interaction.response.send_message(
                    content=f"✅ {success_msg}", embed=embed, ephemeral=True
                )
                return
            custom = await activate_user_custom_theme(uid, theme.strip())
            if custom:
                await interaction.response.send_message(
                    content=f"✅ {t('theme_updated_success', lang, theme=custom.name)}",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                f"❌ Unknown theme '{theme}'. Use the dropdown below to browse.", ephemeral=True
            )
            return

        current_theme = await get_user_theme(uid)
        embed = build_theme_preview_embed(current_theme, lang)
        view = ThemeSelectView(user_id=uid, current_theme=current_theme, lang=lang)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view._message = await interaction.original_response()

    @settings_theme.autocomplete("theme")
    @theme_select.autocomplete("theme")
    async def theme_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        choices = []
        uid = str(interaction.user.id)
        for th in list_themes():
            if not current or current.lower() in th.name.lower() or current.lower() in th.key.lower():
                choices.append(app_commands.Choice(name=f"{th.emoji} {th.name}", value=th.key))
            if len(choices) >= 20:
                break
        try:
            for row in await list_user_custom_themes(uid):
                rname = str(row["name"])
                if not current or current.lower() in rname.lower():
                    choices.append(app_commands.Choice(name=f"🎨 {rname}", value=rname))
                if len(choices) >= 25:
                    break
        except Exception:
            pass
        return choices[:25]

    # ── /category group ───────────────────────────────────────────────────────

    category_group = app_commands.Group(
        name="category",
        description="🏷️ จัดการหมวดหมู่ / Manage categories",
    )

    @category_group.command(name="list", description="📂 รายการหมวดหมู่ / List categories")
    @rate_limit_check("command")
    async def category_list(self, interaction: discord.Interaction) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await ensure_user(uid, lang)

        cats = await db.afetchall(
            """SELECT c.category_id, c.name, c.emoji, c.owner_id,
                      COUNT(t.task_id) AS task_count
               FROM categories c
               LEFT JOIN tasks t ON t.category_id = c.category_id AND t.owner_id = $1 AND t.status != 'Cancelled'
               WHERE c.owner_id = $1 OR c.owner_id = 'system'
               GROUP BY c.category_id, c.name, c.emoji, c.owner_id
               ORDER BY c.owner_id DESC, c.name ASC""",
            (uid,),
        )
        embed = discord.Embed(title=t("cat_list_title", lang), color=0x5865F2)
        if not cats:
            embed.description = t("cat_empty", lang)
        else:
            default_lines = []
            custom_lines  = []
            for row in cats:
                tc = row["task_count"]
                count_str = f"• *{t('cat_task_count', lang, count=tc)}*"
                line = f"{row['emoji']} **{row['name']}**  `#{row['category_id']}`  {count_str}"
                if row["owner_id"] == "system":
                    default_lines.append(line)
                else:
                    custom_lines.append(line)

            if default_lines:
                embed.add_field(
                    name=f"📌 {t('cat_section_default', lang)}",
                    value="\n".join(default_lines),
                    inline=False,
                )
            if custom_lines:
                embed.add_field(
                    name=f"🗂️ {t('cat_section_custom', lang)}",
                    value="\n".join(custom_lines),
                    inline=False,
                )
            elif not default_lines:
                embed.description = t("cat_empty", lang)
        embed.set_footer(text=t("footer_text", lang))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @category_group.command(name="add", description="➕ เพิ่มหมวดหมู่ / Add category")
    @rate_limit_check("command")
    async def category_add(self, interaction: discord.Interaction) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await interaction.response.send_modal(AddCategoryModal(lang))

    @category_group.command(name="remove", description="🗑️ ลบหมวดหมู่ / Remove category")
    @app_commands.describe(category_id="Category ID to remove")
    @rate_limit_check("command")
    async def category_remove(self, interaction: discord.Interaction, category_id: int) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)
        row  = await db.afetchone(
            "SELECT name, owner_id FROM categories WHERE category_id=$1", (category_id,)
        )
        if not row:
            await interaction.response.send_message(t("cat_not_found", lang), ephemeral=True)
            return
        if row["owner_id"] not in (uid, "system") and not _is_owner(interaction.user.id):
            await interaction.response.send_message(t("permission_denied", lang), ephemeral=True)
            return
        if row["owner_id"] == "system":
            await interaction.response.send_message(t("cat_cannot_remove_default", lang), ephemeral=True)
            return
        cat_owner = str(row["owner_id"])
        # Nullify tasks referencing this category
        await db.aexecute(
            "UPDATE tasks SET category_id=NULL WHERE category_id=$1 AND owner_id=$2",
            (category_id, cat_owner),
        )
        await db.aexecute(
            "DELETE FROM categories WHERE category_id=$1 AND owner_id=$2", (category_id, cat_owner)
        )
        await db.alog_action(uid, "category_deleted", str(category_id), row["name"])
        db.invalidate_stats(cat_owner)
        if cat_owner != uid:
            db.invalidate_stats(uid)
        db.query_cache.invalidate_tables(["categories", "tasks"])
        await interaction.response.send_message(
            t("cat_removed", lang, name=row["name"]), ephemeral=True
        )

    # ── /admin group (owner-only) ─────────────────────────────────────────────

    admin_group = app_commands.Group(
        name="admin",
        description="🔐 Admin commands (owner only)",
    )

    @admin_group.command(name="stats", description="📊 Bot-wide statistics")
    async def admin_stats(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction.user.id):
            lang = await get_user_lang(str(interaction.user.id))
            await interaction.response.send_message(t("err_owner_only", lang), ephemeral=True)
            return

        # Single query: COUNT(DISTINCT) for users avoids double-counting rows from the LEFT JOIN.
        # Task aggregates use SUM(CASE) so one round-trip fetches everything.
        stats_row = await db.afetchone(
            """SELECT
                COUNT(DISTINCT users.user_id)                                         AS total_users,
                SUM(CASE WHEN tasks.status='Completed' THEN 1 ELSE 0 END)             AS done_tasks,
                SUM(CASE WHEN tasks.status='Pending'   THEN 1 ELSE 0 END)             AS pending,
                SUM(CASE WHEN tasks.status='Pending' AND tasks.deadline < $1
                         THEN 1 ELSE 0 END)                                           AS overdue
               FROM users
               LEFT JOIN tasks ON tasks.owner_id = users.user_id""",
            (datetime.now(timezone.utc).isoformat(),),
        )
        total_users = int(stats_row["total_users"] or 0)
        total_tasks = int(stats_row["done_tasks"] or 0) + int(stats_row["pending"] or 0)
        done_tasks  = int(stats_row["done_tasks"] or 0)
        pending     = int(stats_row["pending"] or 0)
        overdue     = int(stats_row["overdue"] or 0)
        cache_sz    = db.user_cache.size

        from core.security import rate_limiter
        rl_stats = rate_limiter.stats

        embed = discord.Embed(title="🔐 Admin — Bot Statistics", color=0xED4245)
        embed.add_field(name="👤 Total Users",       value=str(total_users), inline=True)
        embed.add_field(name="📝 Total Tasks",        value=str(total_tasks), inline=True)
        embed.add_field(name="✅ Completed",           value=str(done_tasks),  inline=True)
        embed.add_field(name="⏳ Pending",             value=str(pending),     inline=True)
        embed.add_field(name="🚨 Overdue",             value=str(overdue),     inline=True)
        embed.add_field(name="🗄️ User Cache Size",    value=str(cache_sz),    inline=True)
        embed.add_field(name="🛡️ RL Total Requests",  value=str(rl_stats.get("total", 0)), inline=True)
        embed.add_field(name="🚫 RL Blocked",          value=str(rl_stats.get("blocked", 0)), inline=True)
        embed.set_footer(text=t("footer_text", "en"))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @admin_group.command(name="cache_purge", description="🗑️ Purge expired user cache entries")
    async def admin_cache_purge(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction.user.id):
            lang = await get_user_lang(str(interaction.user.id))
            await interaction.response.send_message(t("err_owner_only", lang), ephemeral=True)
            return
        removed = db.user_cache.purge_expired()
        await interaction.response.send_message(
            f"✅ Purged {removed} expired cache entries.", ephemeral=True
        )

    @admin_group.command(
        name="janitor",
        description="🧹 บำรุงรักษาฐานข้อมูล (Archive >90d, Purge Trash >30d, Compact Audit >180d)",
    )
    @app_commands.describe(
        action="สถานะ หรือ สั่งทำงานทันที / Action to perform",
        archive_days="Archive completed tasks older than N days (default 90)",
        trash_days="Purge recycle bin older than N days (default 30)",
        audit_days="Compact audit_log older than N days (default 180)",
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="🧹 Run Now (ทำความสะอาดทันที)", value="run_now"),
        app_commands.Choice(name="📊 Status (ดูสถานะข้อมูลรอจัดการ)", value="status"),
        app_commands.Choice(name="🔎 Dry Run (จำลองผลโดยไม่ลบ)", value="dry_run"),
    ])
    async def admin_janitor(
        self,
        interaction: discord.Interaction,
        action: str = "run_now",
        archive_days: int = 90,
        trash_days: int = 30,
        audit_days: int = 180,
    ) -> None:
        lang = await get_user_lang(str(interaction.user.id))
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message(t("err_owner_only", lang), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        from recovery import janitor

        if action == "status":
            stats = await janitor.get_janitor_stats(
                archive_days=archive_days, trash_days=trash_days, audit_days=audit_days
            )
            embed = discord.Embed(title=t("janitor_status_title", lang), color=0x5865F2)
            embed.add_field(name=t("janitor_archived_total", lang), value=str(stats["tasks_archive_total"]), inline=True)
            embed.add_field(name=t("janitor_eligible_archive", lang), value=str(stats["eligible_archive"]), inline=True)
            embed.add_field(name=t("janitor_eligible_trash", lang), value=str(stats["eligible_trash"]), inline=True)
            embed.add_field(name=t("janitor_eligible_audit", lang), value=str(stats["eligible_audit"]), inline=True)
            embed.add_field(name=t("janitor_compacted_total", lang), value=str(stats["compacted_audit_total"]), inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        is_dry = (action == "dry_run")
        report = await janitor.run_janitor_cycle(
            archive_days=archive_days,
            trash_days=trash_days,
            audit_days=audit_days,
            dry_run=is_dry,
        )
        title_key = "janitor_dryrun_title" if is_dry else "janitor_done_title"
        embed = discord.Embed(
            title=t(title_key, lang),
            description=t(
                "janitor_report_desc",
                lang,
                archived=report.archived_tasks,
                purged=report.purged_trash,
                compacted=report.compacted_audit_logs,
            ),
            color=0xFEE75C if is_dry else 0x57F287,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SettingsCog(bot))
