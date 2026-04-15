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
