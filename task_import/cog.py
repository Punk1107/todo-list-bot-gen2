from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.security import rate_limit_check
from locales.i18n import t
from task_import.service import ImportValidationError, parse_import_file
from utils.helpers import ensure_user, get_user_lang, get_user_timezone


class TaskImportCog(commands.Cog, name="Task Import"):
    @app_commands.command(name="import", description="📥 Import tasks from a CSV or JSON file")
    @app_commands.describe(
        file="A UTF-8 CSV or JSON file containing tasks",
        missing_deadline="What to do when an imported task has no deadline",
    )
    @app_commands.choices(missing_deadline=[
        app_commands.Choice(name="Set deadline to tomorrow (+1 day)", value="default_1_day"),
        app_commands.Choice(name="Leave deadline empty", value="no_deadline"),
    ])
    @rate_limit_check("command")
    async def import_tasks(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        missing_deadline: app_commands.Choice[str],
    ) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        await interaction.response.defer(ephemeral=True, thinking=True)
        if file.size > 1_000_000:
            await interaction.followup.send(t("import_file_too_large", lang), ephemeral=True)
            return
        try:
            data = await file.read()
            tasks = parse_import_file(
                data, file.filename, await get_user_timezone(uid), missing_deadline.value
            )
        except ImportValidationError as exc:
            await interaction.followup.send(
                t("import_validation_error", lang, error=str(exc)[:1800]), ephemeral=True
            )
            return
        except (discord.HTTPException, OSError) as exc:
            await interaction.followup.send(
                t("import_read_error", lang, error=str(exc)[:500]), ephemeral=True
            )
            return

        await ensure_user(uid, lang)
        statements = [
            (
                """INSERT INTO tasks
                   (task, deadline, priority, status, recurring, tags, description, is_pinned, owner_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                (
                    task.task, task.deadline, task.priority, task.status, task.recurring,
                    task.tags, task.description, task.is_pinned, uid,
                ),
            )
            for task in tasks
        ]
        try:
            await db.aexecute_batch(statements)
        except Exception:
            await interaction.followup.send(t("import_database_error", lang), ephemeral=True)
            raise
        db.invalidate_stats(uid)
        await db.alog_action(uid, "tasks_imported", detail=f"count={len(tasks)}")
        await interaction.followup.send(
            t("import_success", lang, count=len(tasks)), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TaskImportCog())
