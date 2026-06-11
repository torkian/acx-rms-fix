"""Unit tests for core.py — no ffmpeg required."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from acx_rms_fix import core

# ---------------- Measurement ----------------


def _ok_measurement(**over) -> core.Measurement:
    """A fully ACX-compliant Measurement; override one field to test a failure."""
    base = dict(
        rms_db=-20.3,
        peak_db=-3.5,
        noise_floor_db=-70.0,
        sample_peak_db=-3.6,
        codec="mp3",
        sample_rate=44100,
        channels=1,
        bitrate_kbps=192,
    )
    base.update(over)
    return core.Measurement(**base)


def test_measurement_passes_when_all_metrics_ok():
    m = _ok_measurement()
    assert m.rms_ok and m.peak_ok and m.noise_ok and m.format_ok
    assert m.passes


def test_measurement_fails_rms_too_low():
    m = _ok_measurement(rms_db=-25.0)
    assert not m.rms_ok
    assert m.peak_ok
    assert not m.passes


def test_measurement_fails_rms_too_high():
    m = _ok_measurement(rms_db=-17.0)
    assert not m.rms_ok
    assert not m.passes


def test_measurement_fails_peak_too_high():
    m = _ok_measurement(peak_db=-2.0)
    assert m.rms_ok
    assert not m.peak_ok
    assert not m.passes


def test_measurement_fails_noise_floor_too_high():
    m = _ok_measurement(noise_floor_db=-50.0)
    assert m.rms_ok and m.peak_ok
    assert not m.noise_ok
    assert not m.passes


def test_measurement_fails_wrong_sample_rate():
    assert not _ok_measurement(sample_rate=48000).format_ok
    assert not _ok_measurement(sample_rate=48000).passes


def test_measurement_fails_stereo():
    assert not _ok_measurement(channels=2).format_ok
    assert not _ok_measurement(channels=2).passes


def test_measurement_fails_non_mp3_codec():
    assert not _ok_measurement(codec="pcm_s16le").format_ok
    assert not _ok_measurement(codec="aac").passes


def test_measurement_fails_wrong_bitrate():
    assert not _ok_measurement(bitrate_kbps=128).format_ok
    assert _ok_measurement(bitrate_kbps=192).format_ok  # within tolerance


def test_measurement_rms_ok_at_exact_boundaries():
    assert _ok_measurement(rms_db=core.RMS_MIN).rms_ok
    assert _ok_measurement(rms_db=core.RMS_MAX).rms_ok


def test_measurement_none_values_fail():
    m = core.Measurement()
    assert not m.rms_ok
    assert not m.peak_ok
    assert not m.noise_ok
    assert not m.format_ok
    assert not m.passes


# ---------------- measurement parsing (astats / ebur128 / stream banner) ----------------

_FAKE_ASTATS_OUTPUT = """
  Stream #0:0: Audio: mp3 (mp3float), 44100 Hz, mono, fltp, 192 kb/s
[Parsed_astats_0 @ 0x] Channel: 1
[Parsed_astats_0 @ 0x] Peak level dB: -3.46
[Parsed_astats_0 @ 0x] RMS level dB: -20.27
[Parsed_astats_0 @ 0x] Noise floor dB: -91.97
[Parsed_astats_0 @ 0x] Overall
[Parsed_astats_0 @ 0x] Peak level dB: -3.46
[Parsed_astats_0 @ 0x] RMS level dB: -20.27
[Parsed_astats_0 @ 0x] Noise floor dB: -91.97
""".strip()

_FAKE_EBUR128_OUTPUT = """
  Integrated loudness:
    I:         -20.2 LUFS
  True peak:
    Peak:       -3.4 dBFS
""".strip()


def _fake_cp(stderr: str, returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)


def test_parse_stream_info_mp3():
    info = core._parse_stream_info(_FAKE_ASTATS_OUTPUT)
    assert info["codec"] == "mp3"
    assert info["sample_rate"] == 44100
    assert info["channels"] == 1
    assert info["bitrate_kbps"] == 192


def test_parse_stream_info_stereo_wav():
    line = (
        "  Stream #0:0: Audio: pcm_s16le ([1][0][0][0] / 0x0001), 48000 Hz, stereo, s16, 1536 kb/s"
    )
    info = core._parse_stream_info(line)
    assert info["codec"] == "pcm_s16le"
    assert info["sample_rate"] == 48000
    assert info["channels"] == 2
    assert info["bitrate_kbps"] == 1536


def test_measure_astats_parses_overall_block(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "_run_ffmpeg", lambda args: _fake_cp(_FAKE_ASTATS_OUTPUT))
    f = tmp_path / "x.mp3"
    f.write_bytes(b"x")
    rms, peak, floor, info = core._measure_astats(f)
    assert rms == -20.27
    assert peak == -3.46
    assert floor == -91.97
    assert info["sample_rate"] == 44100


def test_measure_astats_raises_on_unparseable(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "_run_ffmpeg", lambda args: _fake_cp("nothing useful here"))
    f = tmp_path / "x.mp3"
    f.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="could not parse astats"):
        core._measure_astats(f)


def test_measure_astats_raises_on_ffmpeg_error(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "_run_ffmpeg", lambda args: _fake_cp("boom", returncode=1))
    f = tmp_path / "x.mp3"
    f.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="could not measure"):
        core._measure_astats(f)


def test_measure_true_peak_parses_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "_run_ffmpeg", lambda args: _fake_cp(_FAKE_EBUR128_OUTPUT))
    f = tmp_path / "x.mp3"
    f.write_bytes(b"x")
    assert core._measure_true_peak(f) == -3.4


def test_to_db_handles_inf_and_nan():
    assert core._to_db("-20.27") == -20.27
    assert core._to_db("-inf") == float("-inf")
    assert core._to_db("nan") == float("-inf")
    assert core._to_db("inf") == float("inf")


# ---------------- planned_output ----------------


def test_planned_output_fix_default(tmp_path):
    p = tmp_path / "chapter.mp3"
    assert core.planned_output(p, None, replace=False) == tmp_path / "chapter_ACX.mp3"


def test_planned_output_fix_out_dir(tmp_path):
    p = tmp_path / "chapter.wav"
    out = tmp_path / "mastered"
    assert core.planned_output(p, out, replace=False) == out / "chapter_ACX.mp3"


def test_planned_output_replace_mp3_is_in_place(tmp_path):
    p = tmp_path / "chapter.mp3"
    assert core.planned_output(p, None, replace=True) == p


def test_planned_output_replace_non_mp3_falls_back_to_acx_sibling(tmp_path):
    # Replacing a non-MP3 must not overwrite the original or an unrelated file:
    # it falls back to the standard <stem>_ACX.mp3 sibling.
    p = tmp_path / "chapter.wav"
    assert core.planned_output(p, None, replace=True) == tmp_path / "chapter_ACX.mp3"


def test_to_dict_nulls_non_finite_floats():
    """Digital silence yields -inf; to_dict() must null it so JSON stays valid."""
    import json

    fr = core.FileResult(
        input_path="x.mp3",
        output_path="x.mp3",
        action="check",
        before=_ok_measurement(noise_floor_db=float("-inf")),
        after=_ok_measurement(noise_floor_db=float("-inf")),
        passed=True,
    )
    d = fr.to_dict()
    assert d["before"]["noise_floor_db"] is None
    # Round-trips through strict JSON (no Infinity/NaN tokens).
    text = json.dumps(d, allow_nan=False)
    assert "Infinity" not in text


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
    # Make sure frozen-mode check doesn't accidentally find something
    monkeypatch.setattr(core.sys, "frozen", False, raising=False)
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


def test_resolve_ffmpeg_prefers_bundled_over_path(monkeypatch, tmp_path):
    """When running under PyInstaller (sys.frozen / _MEIPASS) the bundled
    binary wins over whatever is on PATH."""
    bundled = tmp_path / "ffmpeg"
    bundled.write_bytes(b"#!/bin/sh\necho fake\n")
    bundled.chmod(0o755)

    monkeypatch.setattr(core.sys, "frozen", True, raising=False)
    monkeypatch.setattr(core.sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(core.shutil, "which", lambda _: "/usr/bin/should-not-be-used")

    if core.platform.system() == "Windows":
        # On Windows the lookup expects ffmpeg.exe
        (tmp_path / "ffmpeg.exe").write_bytes(b"x")
        assert core._resolve_ffmpeg() == str(tmp_path / "ffmpeg.exe")
    else:
        assert core._resolve_ffmpeg() == str(bundled)


def test_resolve_ffmpeg_falls_back_to_path_when_not_frozen(monkeypatch):
    monkeypatch.setattr(core.sys, "frozen", False, raising=False)
    monkeypatch.setattr(core.shutil, "which", lambda _: "/usr/local/bin/ffmpeg")
    assert core._resolve_ffmpeg() == "/usr/local/bin/ffmpeg"


def test_resolve_ffmpeg_returns_empty_when_nothing_found(monkeypatch):
    monkeypatch.setattr(core.sys, "frozen", False, raising=False)
    monkeypatch.setattr(core.shutil, "which", lambda _: None)
    assert core._resolve_ffmpeg() == ""


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
        return _ok_measurement()

    monkeypatch.setattr(core, "measure", fake_measure)

    messages: list[str] = []
    r = core.process_one(fake, check_only=True, on_progress=messages.append)
    assert r.passed
    assert any("check:" in m for m in messages)


def test_process_one_dry_run_does_not_encode(monkeypatch, tmp_path):
    """dry-run measures the input and reports the planned output without writing."""
    fake = tmp_path / "chapter.wav"
    fake.write_bytes(b"fake")

    monkeypatch.setattr(core, "measure", lambda path: _ok_measurement(rms_db=-30.0))
    # master() must never be called in a dry run.
    monkeypatch.setattr(
        core, "master", lambda *a, **k: pytest.fail("master() should not run during --dry-run")
    )

    messages: list[str] = []
    r = core.process_one(fake, out_dir=tmp_path / "out", dry_run=True, on_progress=messages.append)
    assert r.action == "dry-run"
    assert r.output_path.endswith("chapter_ACX.mp3")
    assert r.after is None
    assert not r.passed  # rms -30 is too low
    assert any("would write" in m for m in messages)
