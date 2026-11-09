"""
focus/audio_synth.py — In-Memory Harmonic Chime Audio Synthesizer for Discord Voice Channels.

100% Pure Python (math, struct, wave) with ZERO external dependencies or audio files:
- Synthesizes gentle harmonic bell chimes in memory (io.BytesIO)
- Emits standard 16-bit signed 48kHz Stereo PCM audio
- Provides ChimeAudioSource(discord.AudioSource) for streaming 20ms frames directly into Discord voice clients without FFmpeg.
"""
from __future__ import annotations

import io
import math
import struct
from typing import Sequence
import wave

import discord

SAMPLE_RATE = 48000     # Discord native audio sample rate
CHANNELS = 2            # Stereo (left, right)
SAMPLE_WIDTH = 2        # 16-bit signed integer (2 bytes per sample)
FRAME_DURATION_MS = 20  # Discord standard frame duration
SAMPLES_PER_FRAME = int(SAMPLE_RATE * (FRAME_DURATION_MS / 1000.0))  # 960 samples
FRAME_SIZE = SAMPLES_PER_FRAME * CHANNELS * SAMPLE_WIDTH             # 3840 bytes per 20ms frame

# Harmonic triad frequencies for meditation/focus bells
WORK_START_FREQS = (523.25, 659.25, 783.99)   # C5, E5, G5 (Ascending C-Major Triad — Focus Start)
BREAK_START_FREQS = (783.99, 659.25, 523.25)  # G5, E5, C5 (Descending Relaxing Triad — Break Start)


def synthesize_chime_pcm(
    duration: float = 1.6,
    sample_rate: int = SAMPLE_RATE,
    freqs: Sequence[float] = WORK_START_FREQS,
    volume: float = 0.7,
    decay_rate: float = 2.8,
) -> bytes:
    """
    Synthesize gentle harmonic bell chime into raw 16-bit signed stereo PCM bytes.
    Uses exponential decay envelope: A(t) = exp(-decay_rate * t).
    """
    num_samples = int(duration * sample_rate)
    frames = bytearray()
    max_amp = 32767.0 * max(0.0, min(1.0, volume))
    freq_count = max(1, len(freqs))

    for i in range(num_samples):
        t = float(i) / sample_rate
        # Exponential decay envelope for brass/singing-bowl chime
        envelope = math.exp(-decay_rate * t)
        # Synthesize harmonic sum
        val = sum(math.sin(2.0 * math.pi * f * t) for f in freqs) / freq_count
        sample_val = int(max(-32768, min(32767, int(val * envelope * max_amp))))
        # Pack little-endian 16-bit signed stereo (left, right)
        frames.extend(struct.pack("<hh", sample_val, sample_val))

    return bytes(frames)


def synthesize_chime_wav(
    duration: float = 1.6,
    sample_rate: int = SAMPLE_RATE,
    freqs: Sequence[float] = WORK_START_FREQS,
    volume: float = 0.7,
    decay_rate: float = 2.8,
) -> io.BytesIO:
    """
    Synthesize chime into a complete, valid WAV audio buffer in memory.
    """
    pcm_data = synthesize_chime_pcm(duration, sample_rate, freqs, volume, decay_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    buf.seek(0)
    return buf


class ChimeAudioSource(discord.AudioSource):
    """
    Pure Python Discord AudioSource that streams in-memory 16-bit 48kHz stereo PCM
    directly to Discord VoiceClient in 20ms (3840 byte) frames.
    Requires ZERO external processes (no FFmpeg needed).
    """

    def __init__(self, pcm_bytes: bytes) -> None:
        super().__init__()
        self.stream = io.BytesIO(pcm_bytes)

    def read(self) -> bytes:
        """Return exactly 20ms of audio (3840 bytes), or empty bytes when finished."""
        data = self.stream.read(FRAME_SIZE)
        if len(data) < FRAME_SIZE:
            # Pad with silence if partial frame remains, then EOF on next read
            if len(data) > 0:
                data += b"\x00" * (FRAME_SIZE - len(data))
                return data
            return b""
        return data

    def is_opus(self) -> bool:
        """Returns False because audio is raw PCM."""
        return False

