"""
focus/voice_service.py — Virtual Focus Room Voice Channel Sync & Pomodoro State Manager.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

import discord

from core.database import db
from focus import audio_synth

log = logging.getLogger(__name__)


async def bind_voice_room(
    guild_id: str,
    channel_id: str,
    user_id: str,
    work_minutes: int = 25,
    break_minutes: int = 5,
) -> Dict[str, Any]:
    """Bind a Discord voice channel to the Pomodoro Virtual Focus Room system."""
    row = await db.fetchone(
        """
        INSERT INTO voice_focus_rooms
            (guild_id, channel_id, bound_by, is_active, work_minutes, break_minutes, current_phase, current_round)
        VALUES ($1, $2, $3, TRUE, $4, $5, 'idle', 1)
        ON CONFLICT (channel_id) DO UPDATE SET
            guild_id = EXCLUDED.guild_id,
            bound_by = EXCLUDED.bound_by,
            is_active = TRUE,
            work_minutes = EXCLUDED.work_minutes,
            break_minutes = EXCLUDED.break_minutes,
            current_phase = 'idle'
        RETURNING *
        """,
        (guild_id, channel_id, user_id, work_minutes, break_minutes),
    )
    db.query_cache.invalidate_table("voice_focus_rooms")
    return dict(row) if row else {}


async def unbind_voice_room(channel_id: str) -> bool:
    """Unbind and deactivate a voice focus room."""
    res = await db.execute(
        "UPDATE voice_focus_rooms SET is_active = FALSE WHERE channel_id = $1",
        (channel_id,),
    )
    db.query_cache.invalidate_table("voice_focus_rooms")
    return bool(res and "UPDATE 1" in res)


async def get_voice_room(channel_id: str) -> Optional[Dict[str, Any]]:
    """Fetch active configuration for a voice focus room."""
    row = await db.fetchone(
        "SELECT * FROM voice_focus_rooms WHERE channel_id = $1 AND is_active = TRUE",
        (channel_id,),
    )
    return dict(row) if row else None


async def get_all_active_voice_rooms() -> List[Dict[str, Any]]:
    """Fetch all active voice focus rooms across all guilds."""
    rows = await db.fetchall(
        "SELECT * FROM voice_focus_rooms WHERE is_active = TRUE"
    )
    return [dict(r) for r in rows]


async def update_room_phase(
    channel_id: str,
    phase: str,
    round_num: int,
    ends_at: datetime,
) -> None:
    """Advance room to a new phase ('work' or 'break')."""
    await db.execute(
        """
        UPDATE voice_focus_rooms
        SET current_phase = $1, current_round = $2, phase_ends_at = $3
        WHERE channel_id = $4
        """,
        (phase, round_num, ends_at, channel_id),
    )
    db.query_cache.invalidate_table("voice_focus_rooms")


async def reset_room_to_idle(channel_id: str) -> None:
    """Reset room status back to idle when empty."""
    await db.execute(
        """
        UPDATE voice_focus_rooms
        SET current_phase = 'idle', phase_ends_at = NULL
        WHERE channel_id = $1
        """,
        (channel_id,),
    )
    db.query_cache.invalidate_table("voice_focus_rooms")


async def toggle_user_chime(user_id: str) -> bool:
    """Toggle user-specific chime alerts on/off."""
    row = await db.fetchone(
        "SELECT chime_enabled FROM user_chime_settings WHERE user_id = $1",
        (user_id,),
    )
    new_val = False if row and row["chime_enabled"] else True
    await db.execute(
        """
        INSERT INTO user_chime_settings (user_id, chime_enabled)
        VALUES ($1, $2)
        ON CONFLICT (user_id) DO UPDATE SET chime_enabled = EXCLUDED.chime_enabled
        """,
        (user_id, new_val),
    )
    db.query_cache.invalidate_table("user_chime_settings")
    return new_val


async def get_user_chime_setting(user_id: str) -> bool:
    """Check if user has chime alerts enabled (defaults to True)."""
    row = await db.fetchone(
        "SELECT chime_enabled FROM user_chime_settings WHERE user_id = $1",
        (user_id,),
    )
    return bool(row["chime_enabled"]) if row else True


async def update_voice_channel_status(
    channel: discord.VoiceChannel,
    status_text: Optional[str],
) -> bool:
    """
    Set real-time Voice Channel Status via Discord Native API.
    Falls back gracefully if permission is denied or unsupported.
    """
    try:
        if hasattr(channel._state, "http") and hasattr(channel._state.http, "edit_voice_channel_status"):
            await channel._state.http.edit_voice_channel_status(
                status=status_text,
                channel_id=channel.id,
            )
            return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        log.debug("Could not edit voice channel status for %s: %s", channel.id, exc)
    except Exception as exc:
        log.warning("Unexpected error editing voice channel status for %s: %s", channel.id, exc)
    return False


async def play_chime_in_voice(
    voice_channel: discord.VoiceChannel,
    phase: str = "work",
) -> None:
    """
    Connect to voice channel and play in-memory synthesized chime without FFmpeg.
    """
    guild = voice_channel.guild
    # Check bot permissions in voice channel
    bot_member = guild.me
    perms = voice_channel.permissions_for(bot_member)
    if not (perms.connect and perms.speak):
        log.debug("Bot lacks CONNECT or SPEAK permissions in voice channel %s", voice_channel.id)
        return

    freqs = audio_synth.WORK_START_FREQS if phase == "work" else audio_synth.BREAK_START_FREQS
    pcm_bytes = audio_synth.synthesize_chime_pcm(
        duration=1.8 if phase == "work" else 2.2,
        freqs=freqs,
        volume=0.65,
    )
    source = audio_synth.ChimeAudioSource(pcm_bytes)

    vc: Optional[discord.VoiceClient] = guild.voice_client  # type: ignore[assignment]
    try:
        if vc is None:
            vc = await voice_channel.connect(timeout=5.0, reconnect=False)
        elif vc.channel != voice_channel:
            await vc.move_to(voice_channel)

        if vc and vc.is_connected() and not vc.is_playing():
            vc.play(source)
            # Wait for audio playback to finish
            await asyncio.sleep(2.0)
    except Exception as exc:
        log.debug("Could not play voice chime in channel %s: %s", voice_channel.id, exc)
    finally:
        # Disconnect cleanly after chime
        try:
            if vc and vc.is_connected():
                await vc.disconnect(force=True)
        except Exception:
            pass
