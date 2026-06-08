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


def test_parser_accepts_all_flags():
    ns = cli.build_parser().parse_args(
        ["-o", "out/", "-r", "-c", "--report", "r.md", "-q", "a.mp3", "b.mp3"]
    )
    assert ns.out_dir is not None
    assert ns.replace is True
    assert ns.check is True
    assert ns.report is not None
    assert ns.quiet is True
    assert ns.inputs == ["a.mp3", "b.mp3"]


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
        before=Measurement(rms_db=-20.5, peak_db=-4.0, noise_floor_ok=True),
        after=Measurement(rms_db=-20.5, peak_db=-4.0, noise_floor_ok=True),
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
        before=Measurement(rms_db=-20.5, peak_db=-4.0, noise_floor_ok=True),
        after=Measurement(rms_db=-20.5, peak_db=-4.0, noise_floor_ok=True),
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


# ---- --dry-run tests ----


def test_parser_accepts_dry_run_flag():
    ns = cli.build_parser().parse_args(["--dry-run", "a.mp3"])
    assert ns.dry_run is True


def test_dry_run_exits_zero_without_ffmpeg(monkeypatch, tmp_path, capsys):
    """--dry-run must not invoke ffmpeg even when it is absent."""
    from acx_rms_fix.core import FfmpegMissingError

    def no_ffmpeg():
        raise FfmpegMissingError("absent")

    monkeypatch.setattr(cli, "require_ffmpeg", no_ffmpeg)
    rc = cli.main(["--dry-run", str(tmp_path / "ch.mp3")])
    assert rc == 0


def test_dry_run_does_not_call_process_one(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(cli, "process_one", lambda *a, **kw: calls.append(1))
    rc = cli.main(["--dry-run", str(tmp_path / "ch.mp3")])
    assert rc == 0
    assert calls == []


def test_dry_run_fix_prints_acx_output_path(tmp_path, capsys):
    rc = cli.main(["--dry-run", str(tmp_path / "chapter01.mp3")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "fix" in out
    assert "chapter01_ACX.mp3" in out


def test_dry_run_check_mode_shows_check(tmp_path, capsys):
    rc = cli.main(["--dry-run", "--check", str(tmp_path / "chapter01.mp3")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "check" in out


def test_dry_run_replace_mode_shows_backup(tmp_path, capsys):
    rc = cli.main(["--dry-run", "--replace", str(tmp_path / "chapter01.mp3")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "replace" in out
    assert "orig" in out


def test_dry_run_respects_out_dir(tmp_path, capsys):
    out_dir = tmp_path / "mastered"
    rc = cli.main(["--dry-run", "-o", str(out_dir), str(tmp_path / "chapter01.mp3")])
    assert rc == 0
    out = capsys.readouterr().out
    assert str(out_dir) in out


def test_dry_run_multiple_files(tmp_path, capsys):
    rc = cli.main(["--dry-run", str(tmp_path / "ch01.mp3"), str(tmp_path / "ch02.mp3")])
    assert rc == 0
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 2
