"""
tests/test_community_ecosystem.py — Unit tests for Pillar 3:
Discord-Native Voice, Community & Event Ecosystem.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import wave

from focus.audio_synth import (
    ChimeAudioSource,
    synthesize_chime_pcm,
    synthesize_chime_wav,
)
from standup.models import DailyStandupEntry, StandupConfig
from standup.service import format_standup_text_with_tasks
from standup.views import build_standup_digest_embed


def test_synthesize_chime_pcm():
    """Verify in-memory chime PCM synthesis generates expected length and structure."""
    duration = 0.5
    sample_rate = 48000
    channels = 2
    bytes_per_sample = 2

    pcm_data = synthesize_chime_pcm(duration=duration, freqs=(880.0,), volume=0.3)
    expected_length = int(duration * sample_rate) * channels * bytes_per_sample
    assert len(pcm_data) == expected_length
    assert any(b != 0 for b in pcm_data), "PCM output should not be silence"


def test_synthesize_chime_wav():
    """Verify synthesized WAV is a valid RIFF file with 48kHz stereo 16-bit audio."""
    buf = synthesize_chime_wav(duration=0.25, freqs=(528.0,))
    wav_bytes = buf.getvalue()
    assert wav_bytes.startswith(b"RIFF")
    assert b"WAVE" in wav_bytes[:12]

    buf.seek(0)
    with wave.open(buf, "rb") as wf:
        assert wf.getnchannels() == 2
        assert wf.getsampwidth() == 2  # 16-bit
        assert wf.getframerate() == 48000
        assert wf.getnframes() > 0


def test_chime_audio_source_streaming():
    """Verify ChimeAudioSource streams 3840-byte (20ms) frames and exhausts cleanly."""
    pcm = synthesize_chime_pcm(duration=0.1, freqs=(440.0,))
    source = ChimeAudioSource(pcm)
    assert not source.is_opus()

    total_read = 0
    while True:
        frame = source.read()
        if not frame:
            break
        assert len(frame) == 3840
        total_read += len(frame)

    assert total_read >= len(pcm)
    assert source.read() == b""


def test_standup_models_from_row():
    """Verify StandupConfig and DailyStandupEntry parse database rows correctly."""
    config_row = {
        "guild_id": "123456789",
        "channel_id": "987654321",
        "standup_time": "09:30",
        "is_active": True,
        "created_by": "111222333",
        "created_at": datetime(2026, 11, 9, 9, 0, 0, tzinfo=timezone.utc),
    }
    cfg = StandupConfig.from_row(config_row)
    assert cfg.guild_id == "123456789"
    assert cfg.channel_id == "987654321"
    assert cfg.standup_time == "09:30"
    assert cfg.is_active is True

    entry_row = {
        "standup_id": 42,
        "guild_id": "123456789",
        "user_id": "555666777",
        "standup_date": date(2026, 11, 9),
        "yesterday_text": "Completed task #101",
        "today_text": "Working on task #102",
        "blockers_text": "None! All clear.",
        "submitted_at": datetime(2026, 11, 9, 9, 35, 0, tzinfo=timezone.utc),
    }
    entry = DailyStandupEntry.from_row(entry_row)
    assert entry.standup_id == 42
    assert entry.user_id == "555666777"
    assert entry.yesterday_text == "Completed task #101"
    assert entry.today_text == "Working on task #102"
    assert entry.blockers_text == "None! All clear."


def test_format_standup_text_with_tasks():
    """Verify format_standup_text_with_tasks wraps #123 mentions in markdown code blocks."""
    plain_text = "Refactored the payment gateway and updated docs."
    assert format_standup_text_with_tasks(plain_text) == plain_text

    text_with_tasks = "Fixed bug in #101 and deployed #42 to staging"
    expected = "Fixed bug in `#101` and deployed `#42` to staging"
    assert format_standup_text_with_tasks(text_with_tasks) == expected


def test_build_standup_digest_embed():
    """Verify build_standup_digest_embed creates properly structured Discord embed."""
    entries = [
        DailyStandupEntry(
            standup_id=1,
            guild_id="123",
            user_id="999",
            standup_date=date(2026, 11, 9),
            yesterday_text="Implemented sprint retros",
            today_text="Building Discord voice sync",
            blockers_text=None,
            submitted_at=datetime.now(timezone.utc),
        )
    ]
    embed = build_standup_digest_embed("Test Guild", date(2026, 11, 9), entries)
    assert embed.title is not None
    assert "Daily Standup Digest" in embed.title
    assert "Test Guild" in embed.title
    assert len(embed.fields) == 1
    field = embed.fields[0]
    assert "<@999>" in field.name
    assert "Implemented sprint retros" in field.value
    assert "Building Discord voice sync" in field.value
