"""
End-to-end integration tests. These require ffmpeg on PATH.

Strategy: generate a synthetic WAV with known-bad characteristics,
run `core.master`, measure the output with `core.measure`, and assert
the output is ACX-compliant.
"""

from __future__ import annotations

from pathlib import Path

from acx_rms_fix import core

from .conftest import requires_ffmpeg
from .fixtures import (
    make_loud_sine,
    make_noisy_speech_surrogate,
    make_quiet_sine,
    wav_to_mp3,
)


@requires_ffmpeg
def test_quiet_input_is_raised_into_acx_rms_window(tmp_path: Path):
    src = make_quiet_sine(tmp_path / "quiet.wav", duration_s=2.0, rms_db=-30.0)
    out = tmp_path / "quiet_ACX.mp3"
    core.master(src, out)

    m = core.measure(out)
    assert m.rms_db is not None and m.peak_db is not None
    assert core.RMS_MIN <= m.rms_db <= core.RMS_MAX, (
        f"RMS {m.rms_db} outside ACX window {core.RMS_MIN}..{core.RMS_MAX}"
    )
    assert m.peak_db <= core.PEAK_MAX, f"peak {m.peak_db} exceeds {core.PEAK_MAX}"


@requires_ffmpeg
def test_loud_input_peak_is_tamed_below_three_db(tmp_path: Path):
    src = make_loud_sine(tmp_path / "loud.wav", duration_s=2.0, peak_db=-1.0)
    out = tmp_path / "loud_ACX.mp3"
    core.master(src, out)

    m = core.measure(out)
    assert m.peak_db is not None
    assert m.peak_db <= core.PEAK_MAX, f"peak {m.peak_db} exceeds ACX ceiling {core.PEAK_MAX}"


@requires_ffmpeg
def test_noisy_input_has_noise_floor_pushed_below_minus_60(tmp_path: Path):
    src = make_noisy_speech_surrogate(
        tmp_path / "noisy.wav", duration_s=2.0, rms_db=-24.0, noise_db=-50.0
    )
    out = tmp_path / "noisy_ACX.mp3"
    core.master(src, out)

    m = core.measure(out)
    assert m.noise_floor_ok, "noise floor should be pushed under -60 dB by afftdn"


@requires_ffmpeg
def test_process_one_end_to_end_passes_check_afterwards(tmp_path: Path):
    src = make_quiet_sine(tmp_path / "source.wav", duration_s=2.0, rms_db=-28.0)
    result = core.process_one(src, out_dir=tmp_path / "out")
    assert result.error is None
    assert result.output_path is not None
    assert Path(result.output_path).exists()
    assert result.after is not None
    assert result.after.passes, (
        f"process_one output did not pass ACX: "
        f"rms={result.after.rms_db} peak={result.after.peak_db} "
        f"nf_ok={result.after.noise_floor_ok}"
    )


@requires_ffmpeg
def test_mp3_input_round_trip_passes_acx(tmp_path: Path):
    """
    The most realistic failing case: a narrator has an existing MP3
    (from ElevenLabs, a DAW export, or a previous session) that was
    recorded too quietly. The pipeline must accept MP3 input and
    produce an ACX-compliant MP3 output.
    """
    wav = make_quiet_sine(tmp_path / "narrator.wav", duration_s=2.5, rms_db=-28.0)
    src_mp3 = wav_to_mp3(wav, tmp_path / "narrator.mp3")

    # Sanity: source MP3 should NOT already meet ACX — otherwise the
    # test proves nothing about the mastering step.
    before = core.measure(src_mp3)
    assert before.rms_db is not None and before.rms_db < core.RMS_MIN, (
        f"synthetic source MP3 already passes ACX RMS ({before.rms_db} dB) — fixture is wrong"
    )

    out = tmp_path / "narrator_ACX.mp3"
    core.master(src_mp3, out)

    after = core.measure(out)
    assert after.rms_db is not None and after.peak_db is not None
    assert core.RMS_MIN <= after.rms_db <= core.RMS_MAX, (
        f"MP3-in round trip RMS {after.rms_db} outside ACX window"
    )
    assert after.peak_db <= core.PEAK_MAX, (
        f"MP3-in round trip peak {after.peak_db} exceeds {core.PEAK_MAX}"
    )
    assert after.noise_floor_ok, "MP3-in round trip noise floor not below -60 dB"


@requires_ffmpeg
def test_mp3_input_via_process_one_writes_correct_output_name(tmp_path: Path):
    """process_one should write `<stem>_ACX.mp3` regardless of input extension."""
    wav = make_quiet_sine(tmp_path / "chapter42.wav", duration_s=2.0, rms_db=-27.0)
    mp3 = wav_to_mp3(wav, tmp_path / "chapter42.mp3")

    out_dir = tmp_path / "mastered"
    result = core.process_one(mp3, out_dir=out_dir)

    assert result.error is None
    assert result.output_path is not None
    assert result.output_path.endswith("chapter42_ACX.mp3")
    assert Path(result.output_path).exists()
    assert result.after is not None and result.after.passes
