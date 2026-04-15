"""
Synthetic WAV generators for tests.

Stdlib-only (`wave` + `struct` + `math` + `random`), so there is no
numpy dependency and no binary audio is committed to the repo. Each
builder produces a 16-bit PCM mono WAV at 44.1 kHz with a known
characteristic the test can then assert against.

`wav_to_mp3` is a small helper that uses ffmpeg to transcode a WAV
fixture into an MP3 — useful for integration tests that need to
cover the MP3-in → MP3-out path that real narrator files take.
"""

from __future__ import annotations

import math
import random
import struct
import subprocess
import wave
from pathlib import Path

SAMPLE_RATE = 44100
INT16_MAX = 32767
INT16_MIN = -32768


def _clip16(x: float) -> int:
    return max(INT16_MIN, min(INT16_MAX, int(x)))


def _write_wav(path: Path, samples: list[int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(b"".join(struct.pack("<h", s) for s in samples))
    return path


def make_quiet_sine(
    path: Path,
    duration_s: float = 2.0,
    rms_db: float = -27.0,
    freq_hz: float = 440.0,
) -> Path:
    """
    A clean sine tone at a chosen RMS level. Use for RMS-too-low tests
    (e.g. rms_db=-27 → expect master() to raise output to ~-20 dB).

    Also inserts 0.3 s of near-silence (at -80 dB) at the start so that
    `silencedetect` has a passage to find — otherwise the noise floor
    check has no silent window to measure against.
    """
    peak_amp = INT16_MAX * (10 ** (rms_db / 20)) * math.sqrt(2)
    silence_samples = int(SAMPLE_RATE * 0.3)
    tone_samples = int(SAMPLE_RATE * duration_s)

    samples: list[int] = []
    for _ in range(silence_samples):
        samples.append(0)
    for n in range(tone_samples):
        v = peak_amp * math.sin(2 * math.pi * freq_hz * n / SAMPLE_RATE)
        samples.append(_clip16(v))
    for _ in range(silence_samples):
        samples.append(0)
    return _write_wav(path, samples)


def make_loud_sine(
    path: Path,
    duration_s: float = 2.0,
    peak_db: float = -1.0,
    freq_hz: float = 440.0,
) -> Path:
    """
    A sine with a chosen peak in dBFS. Use for peak-too-high tests.
    Also leads/trails with 0.3 s of silence for noise-floor detection.
    """
    peak_amp = INT16_MAX * (10 ** (peak_db / 20))
    silence_samples = int(SAMPLE_RATE * 0.3)
    tone_samples = int(SAMPLE_RATE * duration_s)

    samples: list[int] = []
    for _ in range(silence_samples):
        samples.append(0)
    for n in range(tone_samples):
        v = peak_amp * math.sin(2 * math.pi * freq_hz * n / SAMPLE_RATE)
        samples.append(_clip16(v))
    for _ in range(silence_samples):
        samples.append(0)
    return _write_wav(path, samples)


def make_noisy_speech_surrogate(
    path: Path,
    duration_s: float = 2.0,
    rms_db: float = -24.0,
    noise_db: float = -55.0,
    seed: int = 42,
) -> Path:
    """
    Realistic audiobook shape: 0.5 s of true digital silence, then
    `duration_s` of a sine tone at `rms_db` with a background noise
    layer at `noise_db`, then 0.5 s of true digital silence.

    This matches how a narrator records: silence at head and tail with
    speech content (and some room tone) in the middle. The `afftdn`
    stage cleans up the speech-section noise; the lead/trail stays
    silent and the output passes the ACX noise-floor check.
    """
    rng = random.Random(seed)
    tone_peak = INT16_MAX * (10 ** (rms_db / 20)) * math.sqrt(2)
    noise_peak = INT16_MAX * (10 ** (noise_db / 20)) * math.sqrt(2)

    def noise_sample() -> int:
        return _clip16(rng.uniform(-noise_peak, noise_peak))

    samples: list[int] = []
    lead_trail = int(SAMPLE_RATE * 0.5)
    tone_samples = int(SAMPLE_RATE * duration_s)
    for _ in range(lead_trail):
        samples.append(0)
    for n in range(tone_samples):
        v = tone_peak * math.sin(2 * math.pi * 220.0 * n / SAMPLE_RATE)
        samples.append(_clip16(v + noise_sample()))
    for _ in range(lead_trail):
        samples.append(0)
    return _write_wav(path, samples)


def wav_to_mp3(wav_path: Path, mp3_path: Path, bitrate: str = "192k") -> Path:
    """
    Transcode a WAV fixture to MP3 via ffmpeg. Used by integration
    tests that need to cover the "narrator gives us an existing MP3"
    input path. Requires ffmpeg on PATH.
    """
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    cp = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-y",
            "-i",
            str(wav_path),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            bitrate,
            "-ar",
            "44100",
            "-ac",
            "1",
            str(mp3_path),
        ],
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0:
        raise RuntimeError(f"fixture wav_to_mp3 failed: {cp.stderr.strip().splitlines()[-1]}")
    return mp3_path
