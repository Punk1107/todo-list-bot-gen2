"""Discord Cog for Task Templates and Routine Workflows (/template and /routine)."""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.security import rate_limit_check
from locales.i18n import t
from routine_workflows import service
from routine_workflows.views import TemplateCreateModal
from utils.helpers import ensure_user, get_user_lang, get_user_timezone

log = logging.getLogger(__name__)


class RoutineWorkflowsCog(commands.Cog, name="Routine Workflows"):
    """Cog handling Task Templates, DoD checklists, and Event-driven Routine automations."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    template_group = app_commands.Group(
        name="template",
        description="📋 Manage and use standard task templates",
    )

    routine_group = app_commands.Group(
        name="routine",
        description="🔔 Manage automated routine workflows and event-driven tasks",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Autocomplete for Template Names
    # ─────────────────────────────────────────────────────────────────────────

    async def _template_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        uid = str(interaction.user.id)
        gid = str(interaction.guild_id) if interaction.guild_id else None
        try:
            templates = await service.list_templates(owner_id=uid, guild_id=gid)
            curr_lower = current.strip().lower()
            matching = [
                app_commands.Choice(
                    name=f"{'⭐ ' if t.is_built_in else '📁 '}{t.name} — {t.description or t.name}"[:100],
                    value=t.name,
                )
                for t in templates
                if curr_lower in t.name.lower() or (t.description and curr_lower in t.description.lower())
            ]
            return matching[:25]
        except Exception as exc:
            log.warning("Template autocomplete failed: %s", exc)
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # /template Commands
    # ─────────────────────────────────────────────────────────────────────────

    @template_group.command(name="use", description="📋 Start a workflow: create parent task & subtasks from a template in 1 click")
    @app_commands.describe(name="Name of the template to apply")
    @app_commands.autocomplete(name=_template_autocomplete)
    @rate_limit_check("command")
    async def template_use(self, interaction: discord.Interaction, name: str) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        gid = str(interaction.guild_id) if interaction.guild_id else None
        await interaction.response.defer(ephemeral=True, thinking=True)

        await ensure_user(uid, lang)
        tz_name = await get_user_timezone(uid)

        try:
            result = await service.apply_template(
                template_name=name,
                user_id=uid,
                guild_id=gid,
                tz_name=tz_name,
            )
        except ValueError:
            await interaction.followup.send(
                t("template_not_found", lang, name=name), ephemeral=True
            )
            return
        except Exception as exc:
            log.error("Failed to apply template %s: %s", name, exc, exc_info=True)
            await interaction.followup.send(t("err_generic", lang), ephemeral=True)
            return

        embed = discord.Embed(
            title=t("template_applied_title", lang),
            description=t(
                "template_applied_desc",
                lang,
                task_id=result["parent_task_id"],
                task_name=result["task_name"],
                subtasks=result["subtask_count"],
                checklists=result["checklist_count"],
                deadline=result["deadline_iso"],
            ),
            color=0x57F287,
        )
        embed.set_footer(text=t("footer_text", lang))
        await interaction.followup.send(embed=embed, ephemeral=True)

    @template_group.command(name="create", description="➕ Create a new reusable task template")
    @rate_limit_check("command")
    async def template_create(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        gid = str(interaction.guild_id) if interaction.guild_id else None
        await interaction.response.send_modal(
            TemplateCreateModal(user_id=uid, lang=lang, guild_id=gid)
        )

    @template_group.command(name="from-task", description="📥 Convert an existing task and its subtasks into a template")
    @app_commands.describe(
        task_id="ID of the task to turn into a template",
        name="Name for the new template",
    )
    @rate_limit_check("command")
    async def template_from_task(
        self,
        interaction: discord.Interaction,
        task_id: int,
        name: str,
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        gid = str(interaction.guild_id) if interaction.guild_id else None
        await interaction.response.defer(ephemeral=True)

        tmpl = await service.create_template_from_task(
            task_id=task_id,
            name=name,
            owner_id=uid,
            guild_id=gid,
        )
        if not tmpl:
            await interaction.followup.send(
                t("task_not_found", lang, task_id=task_id), ephemeral=True
            )
            return

        await interaction.followup.send(
            t("template_create_success", lang, name=tmpl.name), ephemeral=True
        )

    @template_group.command(name="list", description="📋 List all available templates (built-in & custom)")
    @rate_limit_check("command")
    async def template_list(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        gid = str(interaction.guild_id) if interaction.guild_id else None
        await interaction.response.defer(ephemeral=True)

        templates = await service.list_templates(owner_id=uid, guild_id=gid)
        if not templates:
            await interaction.followup.send(t("template_list_empty", lang), ephemeral=True)
            return

        embed = discord.Embed(
            title=t("template_list_title", lang),
            color=0x5865F2,
        )

        for tmpl in templates[:25]:
            badge = "⭐ Built-in" if tmpl.is_built_in else ("🏛️ Server" if tmpl.guild_id else "👤 Personal")
            desc = tmpl.description or t("template_no_desc", lang)
            sub_count = len(tmpl.items.get("subtasks", [])) if tmpl.items else 0
            chk_count = len(tmpl.items.get("checklists", [])) if tmpl.items else 0
            val = f"`{badge}` · **{sub_count}** subtasks · **{chk_count}** checklists\n{desc}"
            embed.add_field(name=f"📋 {tmpl.name}", value=val, inline=False)

        embed.set_footer(text=t("template_list_footer", lang))
        await interaction.followup.send(embed=embed, ephemeral=True)

    @template_group.command(name="view", description="🔍 Inspect a template's workflow and checklist details")
    @app_commands.describe(name="Name of the template to inspect")
    @app_commands.autocomplete(name=_template_autocomplete)
    @rate_limit_check("command")
    async def template_view(self, interaction: discord.Interaction, name: str) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        gid = str(interaction.guild_id) if interaction.guild_id else None
        await interaction.response.defer(ephemeral=True)

        tmpl = await service.get_template(name, owner_id=uid, guild_id=gid)
        if not tmpl:
            await interaction.followup.send(t("template_not_found", lang, name=name), ephemeral=True)
            return

        items = tmpl.items or {}
        embed = discord.Embed(
            title=f"📋 Template: {tmpl.name}",
            description=tmpl.description or "",
            color=0x5865F2,
        )
        badge = "⭐ Built-in" if tmpl.is_built_in else ("🏛️ Server" if tmpl.guild_id else "👤 Personal")
        embed.add_field(name="Type", value=badge, inline=True)
        embed.add_field(name="Relative Days", value=f"+{items.get('relative_days', 3)} days", inline=True)
        embed.add_field(name="Priority", value=str(tmpl.priority), inline=True)

        subtasks = items.get("subtasks") or []
        if subtasks:
            sub_lines = [
                f"• `{'+' + str(s.get('relative_days', 1)) + 'd'}` **{s.get('task')}**"
                for s in subtasks[:10]
            ]
            embed.add_field(name="Subtasks", value="\n".join(sub_lines), inline=False)

        checklists = items.get("checklists") or []
        if checklists:
            chk_lines = [f"• ⬜ {c}" for c in checklists[:10]]
            embed.add_field(name="Definition of Done (Checklist)", value="\n".join(chk_lines), inline=False)

        embed.set_footer(text=t("template_view_footer", lang, name=tmpl.name))
        await interaction.followup.send(embed=embed, ephemeral=True)

    @template_group.command(name="delete", description="🗑️ Delete a custom task template")
    @app_commands.describe(name="Name of the custom template to delete")
    @app_commands.autocomplete(name=_template_autocomplete)
    @rate_limit_check("command")
    async def template_delete(self, interaction: discord.Interaction, name: str) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        gid = str(interaction.guild_id) if interaction.guild_id else None
        await interaction.response.defer(ephemeral=True)

        # Check if built-in
        if name.strip().lower() in service.BUILT_IN_TEMPLATES:
            await interaction.followup.send(t("template_cannot_delete_builtin", lang), ephemeral=True)
            return

        is_admin = interaction.user.guild_permissions.manage_guild if interaction.guild and isinstance(interaction.user, discord.Member) else False
        deleted = await service.delete_custom_template(
            name=name, owner_id=uid, is_admin=is_admin, guild_id=gid
        )
        if deleted:
            await interaction.followup.send(t("template_deleted_success", lang, name=name), ephemeral=True)
        else:
            await interaction.followup.send(t("template_not_found_or_denied", lang), ephemeral=True)

    # ─────────────────────────────────────────────────────────────────────────
    # /routine Commands (Event-driven Auto-Tasks)
    # ─────────────────────────────────────────────────────────────────────────

    @routine_group.command(name="rule-add", description="🔔 Set an auto-task rule when member joins or receives a role")
    @app_commands.describe(
        event="Trigger event",
        template="Template to assign automatically",
        role="Target role (required if event is 'When member receives role')",
    )
    @app_commands.choices(event=[
        app_commands.Choice(name="When member receives role", value="role_added"),
        app_commands.Choice(name="When member joins server", value="member_join"),
    ])
    @app_commands.autocomplete(template=_template_autocomplete)
    @rate_limit_check("command")
    async def routine_rule_add(
        self,
        interaction: discord.Interaction,
        event: app_commands.Choice[str],
        template: str,
        role: Optional[discord.Role] = None,
    ) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message(t("guild_only_command", "en"), ephemeral=True)
            return

        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        gid = str(interaction.guild_id)
        await interaction.response.defer(ephemeral=True)

        if event.value == "role_added" and not role:
            await interaction.followup.send(t("routine_role_required", lang), ephemeral=True)
            return

        tmpl = await service.get_template(template, owner_id=uid, guild_id=gid)
        if not tmpl:
            await interaction.followup.send(t("template_not_found", lang, name=template), ephemeral=True)
            return

        rule = await service.add_routine_rule(
            guild_id=gid,
            event_type=event.value,
            template_name=template,
            created_by=uid,
            trigger_role_id=role.id if role else None,
        )

        role_mention = role.mention if role else ""
        await interaction.followup.send(
            t("routine_rule_added_success", lang, rule_id=rule.rule_id, event=event.name, template=template, role=role_mention),
            ephemeral=True,
        )

    @routine_group.command(name="rule-list", description="📋 List all active auto-task rules for this server")
    @rate_limit_check("command")
    async def routine_rule_list(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message(t("guild_only_command", "en"), ephemeral=True)
            return

        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        gid = str(interaction.guild_id)
        await interaction.response.defer(ephemeral=True)

        rules = await service.get_routine_rules(gid)
        if not rules:
            await interaction.followup.send(t("routine_rules_empty", lang), ephemeral=True)
            return

        embed = discord.Embed(
            title=t("routine_rules_title", lang),
            description=t("routine_rules_desc", lang),
            color=0x5865F2,
        )

        for r in rules[:25]:
            trigger_str = f"Role <@&{r.trigger_role_id}>" if r.trigger_role_id else "Member Joined"
            val = f"Trigger: `{trigger_str}` ➔ Template: **{r.template_name}**"
            embed.add_field(name=f"Rule #{r.rule_id}", value=val, inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @routine_group.command(name="rule-remove", description="🗑️ Remove an auto-task routine rule")
    @app_commands.describe(rule_id="Rule ID to delete")
    @rate_limit_check("command")
    async def routine_rule_remove(self, interaction: discord.Interaction, rule_id: int) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message(t("guild_only_command", "en"), ephemeral=True)
            return

        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        gid = str(interaction.guild_id)
        await interaction.response.defer(ephemeral=True)

        deleted = await service.delete_routine_rule(rule_id=rule_id, guild_id=gid)
        if deleted:
            await interaction.followup.send(t("routine_rule_deleted", lang, rule_id=rule_id), ephemeral=True)
        else:
            await interaction.followup.send(t("routine_rule_not_found", lang), ephemeral=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Event Listeners: on_member_update & on_member_join
    # ─────────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Trigger auto-tasks when a member receives a new role."""
        if after.bot or before.roles == after.roles:
            return

        added_roles = set(after.roles) - set(before.roles)
        if not added_roles:
            return

        guild = after.guild
        gid = str(guild.id)
        uid = str(after.id)

        for role in added_roles:
            rules = await service.get_matching_rules(gid, "role_added", role_id=role.id)
            if not rules:
                continue

            lang = await get_user_lang(uid)
            tz_name = await get_user_timezone(uid)
            await ensure_user(uid, lang)

            for rule in rules:
                try:
                    result = await service.apply_template(
                        template_name=rule.template_name,
                        user_id=uid,
                        guild_id=gid,
                        tz_name=tz_name,
                    )
                    # Send onboarding DM
                    dm_embed = discord.Embed(
                        title=t("routine_dm_role_title", lang, role=role.name, guild=guild.name),
                        description=t(
                            "routine_dm_role_desc",
                            lang,
                            task_name=result["task_name"],
                            task_id=result["parent_task_id"],
                            subtasks=result["subtask_count"],
                            checklists=result["checklist_count"],
                        ),
                        color=0x5865F2,
                    )
                    dm_embed.set_footer(text=t("footer_text", lang))
                    try:
                        await after.send(embed=dm_embed)
                    except discord.Forbidden:
                        log.debug("Could not send routine DM to %s (DMs disabled)", after.id)
                except Exception as exc:
                    log.error("Failed to execute routine rule %s for member %s: %s", rule.rule_id, after.id, exc)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Trigger auto-tasks when a new member joins the server."""
        if member.bot:
            return

        guild = member.guild
        gid = str(guild.id)
        uid = str(member.id)

        rules = await service.get_matching_rules(gid, "member_join")
        if not rules:
            return

        lang = await get_user_lang(uid)
        tz_name = await get_user_timezone(uid)
        await ensure_user(uid, lang)

        for rule in rules:
            try:
                result = await service.apply_template(
                    template_name=rule.template_name,
                    user_id=uid,
                    guild_id=gid,
                    tz_name=tz_name,
                )
                dm_embed = discord.Embed(
                    title=t("routine_dm_join_title", lang, guild=guild.name),
                    description=t(
                        "routine_dm_join_desc",
                        lang,
                        task_name=result["task_name"],
                        task_id=result["parent_task_id"],
                        subtasks=result["subtask_count"],
                        checklists=result["checklist_count"],
                    ),
                    color=0x57F287,
                )
                dm_embed.set_footer(text=t("footer_text", lang))
                try:
                    await member.send(embed=dm_embed)
                except discord.Forbidden:
                    log.debug("Could not send welcome routine DM to %s (DMs disabled)", member.id)
            except Exception as exc:
                log.error("Failed to execute join routine rule %s for %s: %s", rule.rule_id, member.id, exc)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RoutineWorkflowsCog(bot))
