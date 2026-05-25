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


# --------------- --dry-run tests ---------------


def test_parser_accepts_dry_run_flag():
    ns = cli.build_parser().parse_args(["--dry-run", "a.mp3"])
    assert ns.dry_run is True


def test_dry_run_does_not_call_ffmpeg(monkeypatch, tmp_path, capsys):
    """--dry-run must exit without ever calling require_ffmpeg or process_one."""
    called = {"ffmpeg": False, "process": False}

    def fake_require():
        called["ffmpeg"] = True
        return "fake"

    def fake_process(*a, **kw):
        called["process"] = True

    monkeypatch.setattr(cli, "require_ffmpeg", fake_require)
    monkeypatch.setattr(cli, "process_one", fake_process)

    f = tmp_path / "chapter01.mp3"
    f.write_bytes(b"fake")

    rc = cli.main(["--dry-run", str(f)])
    assert rc == 0
    assert not called["ffmpeg"], "require_ffmpeg should not be called in dry-run mode"
    assert not called["process"], "process_one should not be called in dry-run mode"


def test_dry_run_shows_fix_action_and_output_path(tmp_path, capsys):
    """Default (fix) mode should show 'fix' and the _ACX.mp3 would-be output."""
    f = tmp_path / "chapter01.mp3"
    f.write_bytes(b"fake")

    rc = cli.main(["--dry-run", str(f)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "fix" in out
    assert "chapter01_ACX.mp3" in out


def test_dry_run_with_out_dir_shows_correct_output_path(tmp_path, capsys):
    """With -o, the would-be output path should include the out_dir."""
    f = tmp_path / "chapter02.mp3"
    f.write_bytes(b"fake")
    out_dir = tmp_path / "mastered"

    rc = cli.main(["--dry-run", "-o", str(out_dir), str(f)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "chapter02_ACX.mp3" in out
    assert str(out_dir) in out


def test_dry_run_with_check_flag_shows_check_action(tmp_path, capsys):
    """--dry-run --check should show 'check' (no output path line)."""
    f = tmp_path / "already_good.mp3"
    f.write_bytes(b"fake")

    rc = cli.main(["--dry-run", "--check", str(f)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "check" in out
    assert "_ACX.mp3" not in out


def test_dry_run_with_replace_flag_shows_replace_and_backup(tmp_path, capsys):
    """--dry-run --replace should show 'replace' and the backup filename."""
    f = tmp_path / "chapter03.mp3"
    f.write_bytes(b"fake")

    rc = cli.main(["--dry-run", "--replace", str(f)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "replace" in out
    assert "chapter03.orig.mp3" in out


def test_dry_run_missing_file_shows_missing(tmp_path, capsys):
    """Missing files should be reported (not crash) and found count reflects only existing."""
    rc = cli.main(["--dry-run", str(tmp_path / "ghost.mp3")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "missing" in out
    assert "0/1" in out


def test_dry_run_summary_line_shows_found_count(tmp_path, capsys):
    """Summary line should show N/total count."""
    f1 = tmp_path / "a.mp3"
    f1.write_bytes(b"fake")
    f2 = tmp_path / "b.mp3"
    f2.write_bytes(b"fake")

    rc = cli.main(["--dry-run", str(f1), str(f2), str(tmp_path / "missing.mp3")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "2/3" in out
