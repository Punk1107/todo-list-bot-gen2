"""
handlers/settings_cog.py — Setup, language, category, and admin commands v2
New: Category CRUD subcommands, /admin stats/backup (owner-only)
All DB calls async.
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
import pytz

from core.database import db
from core.security import rate_limit_check, validator
from core.config import config
from locales.i18n import t, SUPPORTED_LANGS
from utils.helpers import (
    get_user_lang, get_user_timezone, get_user_role,
    ensure_user, save_user_settings,
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
        if validator.is_suspicious(name):
            await interaction.response.send_message(t("err_suspicious", lang), ephemeral=True)
            return
        emoji = (self.cat_emoji.value or "📝").strip() or "📝"
        ensure_user(uid, lang)
        try:
            cur = await db.aexecute(
                "INSERT INTO categories (name, emoji, owner_id) VALUES (?,?,?)",
                (name, emoji, uid),
            )
            await db.alog_action(uid, "category_created", str(cur.lastrowid), name)
            await interaction.response.send_message(
                t("cat_created", lang, name=f"{emoji} {name}"), ephemeral=True
            )
        except Exception as exc:
            log.error("Category create failed: %s", exc)
            await interaction.response.send_message(t("err_db", lang), ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.error("AddCategoryModal error: %s", error)
        lang = get_user_lang(interaction.user.id)
        await interaction.response.send_message(t("err_generic", lang), ephemeral=True)


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
        lang = get_user_lang(uid)

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

        channel_id = interaction.channel_id
        ensure_user(uid, lang)
        save_user_settings(uid, timezone=tz_clean, channel_id=channel_id)
        await db.alog_action(uid, "setup", detail=f"tz={tz_clean}")

        ch_mention = f"<#{channel_id}>" if channel_id else "—"
        embed = discord.Embed(
            title=t("setup_title", lang),
            description=t("setup_success", lang, tz=tz_clean, channel=ch_mention),
            color=0x2ECC71,
        )
        embed.add_field(
            name="🌐 Language / ภาษา",
            value="Use `/lang` to switch language | ใช้ `/lang` เพื่อเปลี่ยนภาษา",
            inline=False,
        )
        embed.set_footer(text=t("footer_text", lang))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /lang ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="lang", description="🌐 เปลี่ยนภาษา / Change language")
    @rate_limit_check("command")
    async def lang(self, interaction: discord.Interaction) -> None:
        uid          = str(interaction.user.id)
        current_lang = get_user_lang(uid)
        ensure_user(uid, current_lang)

        embed = discord.Embed(
            title=t("lang_select_title", current_lang),
            description=t("lang_select_desc", current_lang),
            color=0x5865F2,
        )
        view = LanguageView(current_lang)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── /help ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="help", description="📖 ดูวิธีใช้ / View help")
    @rate_limit_check("command")
    async def help_cmd(self, interaction: discord.Interaction) -> None:
        uid  = str(interaction.user.id)
        lang = get_user_lang(uid)

        embed = discord.Embed(
            title=t("help_title", lang),
            description=t("help_desc", lang),
            color=0x5865F2,
        )

        # Task commands
        task_cmds = {
            "/add":              t("help_add", lang),
            "/list":             t("help_list", lang),
            "/today":            "📅 " + ("ดู Task วันนี้" if lang == "th" else "Tasks due today"),
            "/overdue":          "🚨 " + ("Task เกินกำหนด" if lang == "th" else "Overdue tasks"),
            "/task [id]":        "📌 " + ("รายละเอียด Task" if lang == "th" else "Task detail"),
            "/done [id]":        t("help_done", lang),
            "/delete [id]":      t("help_delete", lang),
            "/pin [id]":         "📌 " + ("ปักหมุด" if lang == "th" else "Pin task"),
            "/unpin [id]":       "📌 " + ("เลิกปักหมุด" if lang == "th" else "Unpin task"),
            "/recurring [id]":   "🔄 " + ("ตั้งการทำซ้ำ" if lang == "th" else "Set recurring"),
            "/search [q]":       t("help_search", lang),
            "/stats":            t("help_stats", lang),
            "/export":           t("help_export", lang),
        }
        embed.add_field(
            name="📝 " + ("คำสั่ง Task" if lang == "th" else "Task Commands"),
            value="\n".join(f"`{k}` — {v}" for k, v in task_cmds.items()),
            inline=False,
        )

        # Settings commands
        setting_cmds = {
            "/setup [tz]":       t("help_setup", lang),
            "/lang":             t("help_lang", lang),
            "/category list":    "📂 " + ("รายการหมวดหมู่" if lang == "th" else "List categories"),
            "/category add":     "➕ " + ("เพิ่มหมวดหมู่" if lang == "th" else "Add category"),
            "/category remove":  "🗑️ " + ("ลบหมวดหมู่" if lang == "th" else "Remove category"),
            "/help":             t("help_commands", lang),
        }
        embed.add_field(
            name="⚙️ " + ("การตั้งค่า" if lang == "th" else "Settings"),
            value="\n".join(f"`{k}` — {v}" for k, v in setting_cmds.items()),
            inline=False,
        )

        embed.set_footer(text=t("footer_text", lang))
        await interaction.response.send_message(embed=embed)  # public — ทุกคนในช่องเห็นได้

    # ── /category group ───────────────────────────────────────────────────────

    category_group = app_commands.Group(
        name="category",
        description="🏷️ จัดการหมวดหมู่ / Manage categories",
    )

    @category_group.command(name="list", description="📂 รายการหมวดหมู่ / List categories")
    @rate_limit_check("command")
    async def category_list(self, interaction: discord.Interaction) -> None:
        uid  = str(interaction.user.id)
        lang = get_user_lang(uid)
        ensure_user(uid, lang)

        cats = await db.afetchall(
            "SELECT * FROM categories WHERE owner_id=? OR owner_id='system' ORDER BY name",
            (uid,),
        )
        embed = discord.Embed(title=t("cat_list_title", lang), color=0x3498DB)
        if not cats:
            embed.description = t("cat_empty", lang)
        else:
            lines = []
            for row in cats:
                owner_tag = " *(default)*" if row["owner_id"] == "system" else ""
                lines.append(f"{row['emoji']} **{row['name']}**  `#{row['category_id']}`{owner_tag}")
            embed.description = "\n".join(lines)
        embed.set_footer(text=t("footer_text", lang))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @category_group.command(name="add", description="➕ เพิ่มหมวดหมู่ / Add category")
    @rate_limit_check("command")
    async def category_add(self, interaction: discord.Interaction) -> None:
        uid  = str(interaction.user.id)
        lang = get_user_lang(uid)
        await interaction.response.send_modal(AddCategoryModal(lang))

    @category_group.command(name="remove", description="🗑️ ลบหมวดหมู่ / Remove category")
    @app_commands.describe(category_id="Category ID to remove")
    @rate_limit_check("command")
    async def category_remove(self, interaction: discord.Interaction, category_id: int) -> None:
        uid  = str(interaction.user.id)
        lang = get_user_lang(uid)
        row  = await db.afetchone(
            "SELECT name, owner_id FROM categories WHERE category_id=?", (category_id,)
        )
        if not row:
            await interaction.response.send_message(t("cat_not_found", lang), ephemeral=True)
            return
        if row["owner_id"] not in (uid, "system") and not _is_owner(interaction.user.id):
            await interaction.response.send_message(t("permission_denied", lang), ephemeral=True)
            return
        if row["owner_id"] == "system":
            msg = "❌ Cannot remove default categories." if lang == "en" else "❌ ไม่สามารถลบหมวดหมู่เริ่มต้นได้"
            await interaction.response.send_message(msg, ephemeral=True)
            return
        # Nullify tasks referencing this category
        await db.aexecute(
            "UPDATE tasks SET category_id=NULL WHERE category_id=? AND owner_id=?",
            (category_id, uid),
        )
        await db.aexecute(
            "DELETE FROM categories WHERE category_id=? AND owner_id=?", (category_id, uid)
        )
        await db.alog_action(uid, "category_deleted", str(category_id), row["name"])
        await interaction.response.send_message(
            f"🗑️ Category **{row['name']}** removed.", ephemeral=True
        )

    # ── /admin group (owner-only) ─────────────────────────────────────────────

    admin_group = app_commands.Group(
        name="admin",
        description="🔐 Admin commands (owner only)",
    )

    @admin_group.command(name="stats", description="📊 Bot-wide statistics")
    async def admin_stats(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message(
                "❌ Owner-only command.", ephemeral=True
            )
            return

        total_users = (await db.afetchone("SELECT COUNT(*) AS c FROM users"))["c"]
        total_tasks = (await db.afetchone("SELECT COUNT(*) AS c FROM tasks"))["c"]
        done_tasks  = (await db.afetchone("SELECT COUNT(*) AS c FROM tasks WHERE status='Completed'"))["c"]
        pending     = (await db.afetchone("SELECT COUNT(*) AS c FROM tasks WHERE status='Pending'"))["c"]
        cache_sz    = db.user_cache.size
        rl_stats    = __import__("core.security", fromlist=["rate_limiter"]).rate_limiter.stats

        embed = discord.Embed(title="🔐 Admin — Bot Statistics", color=0xE74C3C)
        embed.add_field(name="👤 Total Users",      value=str(total_users), inline=True)
        embed.add_field(name="📝 Total Tasks",       value=str(total_tasks), inline=True)
        embed.add_field(name="✅ Completed",          value=str(done_tasks),  inline=True)
        embed.add_field(name="⏳ Pending",            value=str(pending),     inline=True)
        embed.add_field(name="🗄️ User Cache Size",   value=str(cache_sz),    inline=True)
        embed.add_field(name="🛡️ RL Total Requests", value=str(rl_stats.get("total", 0)), inline=True)
        embed.add_field(name="🚫 RL Blocked",         value=str(rl_stats.get("blocked", 0)), inline=True)
        embed.set_footer(text=t("footer_text", "en"))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @admin_group.command(name="backup", description="💾 Trigger manual DB backup")
    async def admin_backup(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message("❌ Owner-only command.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        import asyncio
        path = await asyncio.to_thread(db.backup)
        if path:
            await interaction.followup.send(f"✅ Backup saved: `{path}`", ephemeral=True)
        else:
            await interaction.followup.send("❌ Backup failed — check logs.", ephemeral=True)

    @admin_group.command(name="cache_purge", description="🗑️ Purge expired user cache entries")
    async def admin_cache_purge(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction.user.id):
            await interaction.response.send_message("❌ Owner-only command.", ephemeral=True)
            return
        removed = db.user_cache.purge_expired()
        await interaction.response.send_message(
            f"✅ Purged {removed} expired cache entries.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SettingsCog(bot))
