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
# Help UI Components
# ─────────────────────────────────────────────────────────────────────────────

def build_help_embed(category: str, lang: str) -> discord.Embed:
    if category == "tasks":
        embed = discord.Embed(
            title=f"📝 {t('help_cat_tasks', lang)}",
            description="All slash commands for creating, tracking, and completing tasks:" if lang != "th" else "คำสั่งทั้งหมดสำหรับสร้าง ติดตาม และจัดการงานของคุณ:",
            color=0x5865F2,
        )
        task_cmds = [
            ("➕ `/add`", t("help_add", lang)),
            ("📋 `/list`", t("help_list", lang)),
            ("📅 `/today`", "View tasks due today with urgency markers" if lang != "th" else "ดู Task ที่ต้องส่งวันนี้พร้อมตัวบอกความเร่งด่วน"),
            ("🚨 `/overdue`", "View overdue tasks needing immediate action" if lang != "th" else "ดูรายการ Task ที่เกินกำหนดส่ง"),
            ("📌 `/task [id]`", "Inspect task details, subtasks, tags, and actions" if lang != "th" else "ดูรายละเอียด Task งานย่อย แท็ก และปุ่มจัดการ"),
            ("✅ `/done [id]`", t("help_done", lang)),
            ("🗑️ `/delete [id]`", t("help_delete", lang)),
            ("📌 `/pin [id]` / `/unpin [id]`", "Pin/unpin important tasks to top of list" if lang != "th" else "ปักหมุด/เลิกปักหมุด Task สำคัญให้อยู่บนสุด"),
            ("🔄 `/recurring [id]`", "Set recurrence interval (daily, weekly, monthly)" if lang != "th" else "ตั้งการทำซ้ำอัตโนมัติ (รายวัน, รายสัปดาห์, รายเดือน)"),
            ("🔍 `/search [query]`", t("help_search", lang)),
            ("📊 `/stats`", t("help_stats", lang)),
            ("📥 `/export`", t("help_export", lang)),
        ]
        for cmd, desc in task_cmds:
            embed.add_field(name=cmd, value=f"> {desc}", inline=False)

    elif category == "settings":
        embed = discord.Embed(
            title=f"⚙️ {t('help_cat_settings', lang)}",
            description="Configure your preferences and organize tasks into categories:" if lang != "th" else "ตั้งค่าการใช้งานและจัดระเบียบงานด้วยหมวดหมู่:",
            color=0x5865F2,
        )
        setting_cmds = [
            ("🕒 `/setup [timezone]`", t("help_setup", lang)),
            ("🌐 `/lang`", t("help_lang", lang)),
            ("📂 `/category list`", "List all default and custom categories" if lang != "th" else "แสดงรายการหมวดหมู่ทั้งหมดทั้งระบบและที่คุณสร้าง"),
            ("➕ `/category add`", "Create a new custom category with emoji" if lang != "th" else "สร้างหมวดหมู่ใหม่พร้อมอิโมจิ"),
            ("🗑️ `/category remove [id]`", "Delete a custom category" if lang != "th" else "ลบหมวดหมู่ที่คุณสร้าง"),
        ]
        for cmd, desc in setting_cmds:
            embed.add_field(name=cmd, value=f"> {desc}", inline=False)

    elif category == "tips":
        embed = discord.Embed(
            title=f"💡 {t('help_cat_tips', lang)}",
            description="Helpful tips to make the most of your To-Do bot:" if lang != "th" else "เคล็ดลับและฟีเจอร์เด็ดเพื่อการทำงานที่มีประสิทธิภาพยิ่งขึ้น:",
            color=0x5865F2,
        )
        tips = [
            ("⚡ Inline Actions", "When viewing a task with `/task [id]`, you can edit priority, mark done, pin, snooze, or add subtasks using buttons!" if lang != "th" else "เมื่อดู Task ด้วย `/task [id]` สามารถกดปุ่มปรับ Priority, ปักหมุด, เลื่อนกำหนดส่ง หรือเพิ่ม Subtask ได้ทันที!"),
            ("⏰ Snooze (+1 Day)", "Easily push back deadlines by 1 day right from the task action view with a single confirmation." if lang != "th" else "เลื่อนกำหนดส่งออกไป 1 วันได้ง่ายๆ ผ่านปุ่ม Snooze พร้อมหน้าต่างยืนยัน"),
            ("📌 Pins & Priority", "Pinned tasks and high-priority tasks always float to the top of your `/list`." if lang != "th" else "Task ที่ปักหมุดและ Task ที่มี Priority สูงจะลอยขึ้นมาอยู่อันดับแรกๆ ใน `/list` เสมอ"),
            ("🔔 DM Reminders", "The bot automatically notifies you via DM 24h, 3h, and 1h before deadlines!" if lang != "th" else "Bot จะส่ง DM เตือนคุณล่วงหน้า 24 ชม., 3 ชม., และ 1 ชม. ก่อนถึงกำหนดส่งโดยอัตโนมัติ!"),
        ]
        for title, desc in tips:
            embed.add_field(name=title, value=f"> {desc}", inline=False)

    else:  # overview
        embed = discord.Embed(
            title=t("help_title", lang),
            description=t("help_desc", lang),
            color=0x5865F2,
        )
        embed.add_field(
            name="🚀 Getting Started",
            value=t("help_quickstart", lang),
            inline=False,
        )
        embed.add_field(
            name="📚 Browse Categories",
            value=(
                "Use the dropdown menu below to view specific command guides:\n"
                "• **📝 Task Commands**: Adding, editing, completing, and organizing\n"
                "• **⚙️ Settings & Categories**: Timezone, language, categories\n"
                "• **💡 Tips & Shortcuts**: Best practices and smart features"
                if lang != "th" else
                "ใช้เมนูด้านล่างเพื่อเลือกดูคำสั่งตามหมวดหมู่:\n"
                "• **📝 คำสั่งจัดการ Task**: การสร้าง, แก้ไข, ทำเสร็จ, และจัดระเบียบ\n"
                "• **⚙️ ตั้งค่า & หมวดหมู่**: Timezone, ภาษา, และหมวดหมู่\n"
                "• **💡 เคล็ดลับ & ทางลัด**: ฟีเจอร์เด็ดและการใช้งานให้คุ้มค่า"
            ),
            inline=False,
        )

    embed.set_footer(text=t("help_version_footer", lang))
    return embed


class HelpCategorySelect(ui.Select):
    def __init__(self, lang: str) -> None:
        self.lang = lang
        options = [
            discord.SelectOption(
                label=t("help_cat_overview", lang),
                value="overview",
                emoji="🚀",
                default=True,
            ),
            discord.SelectOption(
                label=t("help_cat_tasks", lang),
                value="tasks",
                emoji="📝",
            ),
            discord.SelectOption(
                label=t("help_cat_settings", lang),
                value="settings",
                emoji="⚙️",
            ),
            discord.SelectOption(
                label=t("help_cat_tips", lang),
                value="tips",
                emoji="💡",
            ),
        ]
        super().__init__(placeholder="📖 Select help category...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        val = self.values[0]
        for opt in self.options:
            opt.default = (opt.value == val)

        embed = build_help_embed(val, self.lang)
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(ui.View):
    def __init__(self, lang: str) -> None:
        super().__init__(timeout=300)
        self.lang = lang
        self.add_item(HelpCategorySelect(lang))


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
            name="🌐 Language / ภาษา",
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

    @app_commands.command(name="help", description="📖 ดูวิธีใช้ / View help")
    @rate_limit_check("command")
    async def help_cmd(self, interaction: discord.Interaction) -> None:
        uid  = str(interaction.user.id)
        lang = await get_user_lang(uid)

        view = HelpView(lang)
        embed = build_help_embed("overview", lang)
        await interaction.response.send_message(embed=embed, view=view)

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
            msg = "❌ Cannot remove default categories." if lang == "en" else "❌ ไม่สามารถลบหมวดหมู่เริ่มต้นได้"
            await interaction.response.send_message(msg, ephemeral=True)
            return
        # Nullify tasks referencing this category
        await db.aexecute(
            "UPDATE tasks SET category_id=NULL WHERE category_id=$1 AND owner_id=$2",
            (category_id, uid),
        )
        await db.aexecute(
            "DELETE FROM categories WHERE category_id=$1 AND owner_id=$2", (category_id, uid)
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
            await interaction.response.send_message("❌ Owner-only command.", ephemeral=True)
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
            await interaction.response.send_message("❌ Owner-only command.", ephemeral=True)
            return
        removed = db.user_cache.purge_expired()
        await interaction.response.send_message(
            f"✅ Purged {removed} expired cache entries.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SettingsCog(bot))
