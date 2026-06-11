"""Tests for CLI argparse and exit codes."""

from __future__ import annotations

import pytest

from acx_rms_fix import cli


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "acx-rms-fix" in out
    assert "Examples:" in out


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    from acx_rms_fix import __version__

    assert __version__ in out


def test_requires_at_least_one_input(capsys):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_parser_accepts_flags():
    ns = cli.build_parser().parse_args(
        ["-o", "out/", "-r", "--report", "r.md", "-q", "a.mp3", "b.mp3"]
    )
    assert ns.out_dir is not None
    assert ns.replace is True
    assert ns.check is False
    assert ns.report is not None
    assert ns.quiet is True
    assert ns.inputs == ["a.mp3", "b.mp3"]


def test_replace_and_check_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["-r", "-c", "a.mp3"])


def test_dry_run_flag_parses():
    ns = cli.build_parser().parse_args(["--dry-run", "a.mp3"])
    assert ns.dry_run is True


def test_dry_run_with_replace_is_allowed():
    ns = cli.build_parser().parse_args(["--dry-run", "-r", "a.mp3"])
    assert ns.dry_run is True and ns.replace is True


def test_parser_accepts_json_lines_flag():
    ns = cli.build_parser().parse_args(["--json-lines", "a.mp3"])
    assert ns.json_lines is True


def test_json_lines_output_is_valid_json_per_line(monkeypatch, tmp_path, capsys):
    """--json-lines prints one JSON object per file, one per line."""
    import json

    from acx_rms_fix.core import FileResult, Measurement

    fake_result = FileResult(
        input_path=str(tmp_path / "ch.mp3"),
        output_path=None,
        action="check",
        before=Measurement(
            rms_db=-20.5,
            peak_db=-4.0,
            noise_floor_db=-70.0,
            codec="mp3",
            sample_rate=44100,
            channels=1,
            bitrate_kbps=192,
        ),
        after=Measurement(
            rms_db=-20.5,
            peak_db=-4.0,
            noise_floor_db=-70.0,
            codec="mp3",
            sample_rate=44100,
            channels=1,
            bitrate_kbps=192,
        ),
        passed=True,
    )

    monkeypatch.setattr(cli, "require_ffmpeg", lambda: "fake ffmpeg")
    monkeypatch.setattr(cli, "process_one", lambda *a, **kw: fake_result)

    rc = cli.main(["--json-lines", "--check", str(tmp_path / "ch.mp3")])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["passed"] is True
    assert data["action"] == "check"


def test_json_lines_suppresses_coloured_summary(monkeypatch, tmp_path, capsys):
    """--json-lines should not print the 'all N file(s) ACX-compliant' summary."""
    from acx_rms_fix.core import FileResult, Measurement

    fake_result = FileResult(
        input_path=str(tmp_path / "ch.mp3"),
        output_path=None,
        action="check",
        before=Measurement(
            rms_db=-20.5,
            peak_db=-4.0,
            noise_floor_db=-70.0,
            codec="mp3",
            sample_rate=44100,
            channels=1,
            bitrate_kbps=192,
        ),
        after=Measurement(
            rms_db=-20.5,
            peak_db=-4.0,
            noise_floor_db=-70.0,
            codec="mp3",
            sample_rate=44100,
            channels=1,
            bitrate_kbps=192,
        ),
        passed=True,
    )

    monkeypatch.setattr(cli, "require_ffmpeg", lambda: "fake ffmpeg")
    monkeypatch.setattr(cli, "process_one", lambda *a, **kw: fake_result)

    cli.main(["--json-lines", "--check", str(tmp_path / "ch.mp3")])
    out = capsys.readouterr().out
    assert "ACX-compliant" not in out


def test_main_missing_file_returns_2(monkeypatch, tmp_path, capsys):
    # Make ffmpeg appear present so we don't bail before processing
    monkeypatch.setattr(cli, "require_ffmpeg", lambda: "fake ffmpeg")
    rc = cli.main(["--check", str(tmp_path / "nope.mp3")])
    assert rc == 2


def test_main_ffmpeg_missing_returns_1(monkeypatch, capsys):
    def fake_require():
        from acx_rms_fix.core import FfmpegMissingError

        raise FfmpegMissingError("no ffmpeg")

    monkeypatch.setattr(cli, "require_ffmpeg", fake_require)
    rc = cli.main(["--check", "whatever.mp3"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "no ffmpeg" in err


def test_dry_run_main_returns_0_and_prints_summary(monkeypatch, tmp_path, capsys):
    from acx_rms_fix.core import FileResult, Measurement

    monkeypatch.setattr(cli, "require_ffmpeg", lambda: "fake ffmpeg")

    def fake_process_one(path, **kw):
        assert kw.get("dry_run") is True
        return FileResult(
            input_path=str(path),
            output_path=f"{path}_ACX.mp3",
            action="dry-run",
            before=Measurement(
                rms_db=-30.0,
                peak_db=-4.0,
                noise_floor_db=-70.0,
                codec="mp3",
                sample_rate=44100,
                channels=1,
                bitrate_kbps=192,
            ),
            passed=False,
        )

    monkeypatch.setattr(cli, "process_one", fake_process_one)
    rc = cli.main(["--dry-run", str(tmp_path / "a.mp3")])
    assert rc == 0
    assert "dry-run:" in capsys.readouterr().out


def test_collision_guard_returns_1(monkeypatch, tmp_path, capsys):
    """Two inputs that map to the same output abort before any processing."""
    monkeypatch.setattr(cli, "require_ffmpeg", lambda: "fake ffmpeg")
    monkeypatch.setattr(cli, "process_one", lambda *a, **k: pytest.fail("should not process"))

    a = tmp_path / "x" / "ch1.wav"
    b = tmp_path / "y" / "ch1.wav"
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    rc = cli.main(["-o", str(tmp_path / "out"), str(a), str(b)])
    assert rc == 1
    assert "same output" in capsys.readouterr().err


def test_dry_run_with_check_is_rejected():
    with pytest.raises(SystemExit):
        cli.main(["--dry-run", "--check", "a.mp3"])


def test_dry_run_returns_2_on_error(monkeypatch, tmp_path):
    """A previewed file that errors (missing input) makes --dry-run exit non-zero."""
    monkeypatch.setattr(cli, "require_ffmpeg", lambda: "fake ffmpeg")
    rc = cli.main(["--dry-run", str(tmp_path / "missing.mp3")])
    assert rc == 2


def test_json_lines_report_status_goes_to_stderr(monkeypatch, tmp_path, capsys):
    """--json-lines --report must keep the 'report written' line off stdout."""
    import json

    from acx_rms_fix.core import FileResult, Measurement

    m = Measurement(
        rms_db=-20.5,
        peak_db=-4.0,
        noise_floor_db=-70.0,
        codec="mp3",
        sample_rate=44100,
        channels=1,
        bitrate_kbps=192,
    )
    fake = FileResult(
        input_path="ch.mp3",
        output_path=None,
        action="check",
        before=m,
        after=m,
        passed=True,
    )
    monkeypatch.setattr(cli, "require_ffmpeg", lambda: "fake ffmpeg")
    monkeypatch.setattr(cli, "process_one", lambda *a, **kw: fake)

    rp = tmp_path / "r.json"
    cli.main(["--json-lines", "--check", str(tmp_path / "ch.mp3"), "--report", str(rp)])
    out = capsys.readouterr()
    assert "report written" not in out.out
    assert "report written" in out.err
    lines = [ln for ln in out.out.splitlines() if ln.strip()]
    assert len(lines) == 1 and json.loads(lines[0])["passed"] is True
