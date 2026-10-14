from __future__ import annotations

from urllib.parse import urlsplit

import discord
from discord import app_commands
from discord.ext import commands

from core.config import config
from core.database import db
from calendar_feed.service import create_feed_token, hash_feed_token
from locales.i18n import t
from utils.helpers import ensure_user, get_user_lang


class CalendarFeedCog(commands.Cog, name="Calendar Feed"):
    calendar_group = app_commands.Group(
        name="calendar",
        description="📅 Manage your private calendar subscription",
    )

    async def _replace_token(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        public_url = config.webserver.public_url
        parts = urlsplit(public_url or "")
        if (
            not public_url
            or parts.scheme != "https"
            or not parts.netloc
            or parts.path not in ("", "/")
            or parts.query
            or parts.fragment
        ):
            await interaction.response.send_message(
                t("calendar_public_url_missing", lang), ephemeral=True
            )
            return
        await ensure_user(uid, lang)
        token = create_feed_token()
        await db.aexecute(
            """INSERT INTO calendar_feed_tokens (user_id, token_hash)
               VALUES ($1, $2)
               ON CONFLICT (user_id) DO UPDATE
               SET token_hash=EXCLUDED.token_hash, created_at=NOW()""",
            (uid, hash_feed_token(token)),
        )
        url = f"{public_url}/calendar/{token}.ics"
        await interaction.response.send_message(
            t("calendar_link_created", lang, url=url), ephemeral=True
        )

    @calendar_group.command(name="link", description="Create your calendar subscription link")
    async def calendar_link(self, interaction: discord.Interaction) -> None:
        await self._replace_token(interaction)

    @calendar_group.command(name="rotate", description="Replace a compromised calendar link")
    async def calendar_rotate(self, interaction: discord.Interaction) -> None:
        await self._replace_token(interaction)

    @calendar_group.command(name="revoke", description="Disable your calendar subscription link")
    async def calendar_revoke(self, interaction: discord.Interaction) -> None:
        uid = str(interaction.user.id)
        lang = await get_user_lang(uid)
        result = await db.aexecute(
            "DELETE FROM calendar_feed_tokens WHERE user_id=$1", (uid,)
        )
        revoked = not result.endswith(" 0")
        await interaction.response.send_message(
            t("calendar_revoked" if revoked else "calendar_no_link", lang),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CalendarFeedCog())
