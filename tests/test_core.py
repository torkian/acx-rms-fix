"""Unit tests for core.py — no ffmpeg required."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from acx_rms_fix import core

# ---------------- Measurement ----------------


def test_measurement_passes_when_all_metrics_ok():
    m = core.Measurement(rms_db=-20.3, peak_db=-3.5, noise_floor_ok=True)
    assert m.rms_ok
    assert m.peak_ok
    assert m.passes


def test_measurement_fails_rms_too_low():
    m = core.Measurement(rms_db=-25.0, peak_db=-3.5, noise_floor_ok=True)
    assert not m.rms_ok
    assert m.peak_ok
    assert not m.passes


def test_measurement_fails_rms_too_high():
    m = core.Measurement(rms_db=-17.0, peak_db=-3.5, noise_floor_ok=True)
    assert not m.rms_ok
    assert not m.passes


def test_measurement_fails_peak_too_high():
    m = core.Measurement(rms_db=-20.3, peak_db=-2.0, noise_floor_ok=True)
    assert m.rms_ok
    assert not m.peak_ok
    assert not m.passes


def test_measurement_fails_noise_floor():
    m = core.Measurement(rms_db=-20.3, peak_db=-3.5, noise_floor_ok=False)
    assert m.rms_ok
    assert m.peak_ok
    assert not m.passes


def test_measurement_rms_ok_at_exact_boundaries():
    assert core.Measurement(rms_db=core.RMS_MIN, peak_db=-5, noise_floor_ok=True).rms_ok
    assert core.Measurement(rms_db=core.RMS_MAX, peak_db=-5, noise_floor_ok=True).rms_ok


def test_measurement_none_values_fail():
    m = core.Measurement()
    assert not m.rms_ok
    assert not m.peak_ok
    assert not m.passes


# ---------------- volume detect regex ----------------

_FAKE_VOLUMEDETECT_OUTPUT = """
[Parsed_volumedetect_0 @ 0x7f...] n_samples: 1023366
[Parsed_volumedetect_0 @ 0x7f...] mean_volume: -20.4 dB
[Parsed_volumedetect_0 @ 0x7f...] max_volume: -3.5 dB
[Parsed_volumedetect_0 @ 0x7f...] histogram_0db: 1
""".strip()


def test_measure_volume_regex(monkeypatch, tmp_path):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="",
            stderr=_FAKE_VOLUMEDETECT_OUTPUT,
        )

    monkeypatch.setattr(core.subprocess, "run", fake_run)
    wav = tmp_path / "fake.wav"
    wav.write_bytes(b"fake")
    mean, peak = core.measure_volume(wav)
    assert mean == -20.4
    assert peak == -3.5


def test_measure_volume_raises_when_output_has_no_numbers(monkeypatch, tmp_path):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="",
            stderr="oops no data",
        )

    monkeypatch.setattr(core.subprocess, "run", fake_run)
    wav = tmp_path / "fake.wav"
    wav.write_bytes(b"fake")
    with pytest.raises(RuntimeError, match="could not measure volume"):
        core.measure_volume(wav)


# ---------------- noise_floor_ok ----------------


def test_noise_floor_ok_true_when_silence_detected(monkeypatch, tmp_path):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="",
            stderr="silence_start: 0.5\nsilence_end: 1.2",
        )

    monkeypatch.setattr(core.subprocess, "run", fake_run)
    wav = tmp_path / "fake.wav"
    wav.write_bytes(b"fake")
    assert core.noise_floor_ok(wav) is True


def test_noise_floor_ok_false_when_no_silence(monkeypatch, tmp_path):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="",
            stderr="no silence here",
        )

    monkeypatch.setattr(core.subprocess, "run", fake_run)
    wav = tmp_path / "fake.wav"
    wav.write_bytes(b"fake")
    assert core.noise_floor_ok(wav) is False


# ---------------- filter chain strings ----------------


def test_filter_chain_p1_contains_all_stages():
    chain = core.FILTER_CHAIN_P1
    assert "afftdn" in chain
    assert f"highpass=f={core.HIPASS_HZ}" in chain
    assert f"lowpass=f={core.LOPASS_HZ}" in chain
    assert f"loudnorm=I={core.TARGET_I}" in chain
    assert "print_format=json" in chain


def test_filter_chain_p2_includes_measured_values_and_limiter():
    chain = core.build_filter_chain_p2("-26.2", "-0.2", "4.8", "-36.9", "0.95")
    assert "measured_I=-26.2" in chain
    assert "measured_TP=-0.2" in chain
    assert "measured_LRA=4.8" in chain
    assert "measured_thresh=-36.9" in chain
    assert "offset=0.95" in chain
    assert f"aresample={core.SAMPLE_RATE}" in chain
    assert f"alimiter=limit={core.LIMITER_CEILING}" in chain


def test_limiter_ceiling_is_approximately_minus_3_db():
    expected = 10 ** (-3 / 20)
    assert abs(core.LIMITER_CEILING - expected) < 0.01


# ---------------- require_ffmpeg ----------------


def test_require_ffmpeg_raises_when_missing(monkeypatch):
    monkeypatch.setattr(core.shutil, "which", lambda _: None)
    with pytest.raises(core.FfmpegMissingError):
        core.require_ffmpeg()


def test_require_ffmpeg_returns_version_line_when_present(monkeypatch):
    monkeypatch.setattr(core.shutil, "which", lambda _: "/fake/ffmpeg")

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="ffmpeg version 8.1 Copyright line\nnext line",
            stderr="",
        )

    monkeypatch.setattr(core.subprocess, "run", fake_run)
    assert core.require_ffmpeg().startswith("ffmpeg version 8.1")


# ---------------- process_one error paths ----------------


def test_process_one_missing_file(tmp_path: Path):
    missing = tmp_path / "nope.mp3"
    r = core.process_one(missing, check_only=True)
    assert r.error == "input not found"
    assert r.passed is False
    assert r.duration_seconds is not None


def test_process_one_invokes_progress_callback(monkeypatch, tmp_path):
    # Build a fake that looks like a file but measure() is monkeypatched
    fake = tmp_path / "fake.mp3"
    fake.write_bytes(b"fake")

    def fake_measure(path):
        return core.Measurement(rms_db=-20.0, peak_db=-3.5, noise_floor_ok=True)

    monkeypatch.setattr(core, "measure", fake_measure)

    messages: list[str] = []
    r = core.process_one(fake, check_only=True, on_progress=messages.append)
    assert r.passed
    assert any("check:" in m for m in messages)
