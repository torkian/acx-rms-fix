"""Tests for report.py serializers."""

from __future__ import annotations

import json

from acx_rms_fix.core import FileResult, Measurement, RunReport
from acx_rms_fix.report import to_json, to_jsonl_line, to_markdown, write_report


def _sample_report() -> RunReport:
    rep = RunReport(version="0.1.0", ffmpeg_version="ffmpeg version test")
    rep.results.append(
        FileResult(
            input_path="chapter01.mp3",
            output_path="out/chapter01_ACX.mp3",
            action="fix",
            before=Measurement(rms_db=-27.2, peak_db=-5.8, noise_floor_ok=False),
            after=Measurement(rms_db=-20.3, peak_db=-3.5, noise_floor_ok=True),
            passed=True,
            duration_seconds=1.2,
        )
    )
    rep.results.append(
        FileResult(
            input_path="chapter02.mp3",
            output_path=None,
            action="check",
            before=Measurement(rms_db=-26.0, peak_db=-4.0, noise_floor_ok=False),
            after=Measurement(rms_db=-26.0, peak_db=-4.0, noise_floor_ok=False),
            passed=False,
            duration_seconds=0.3,
        )
    )
    return rep


def test_json_has_required_top_level_keys():
    data = json.loads(to_json(_sample_report()))
    for key in (
        "version",
        "generated_at",
        "platform",
        "ffmpeg_version",
        "spec",
        "summary",
        "results",
    ):
        assert key in data


def test_json_summary_counts_match_results():
    data = json.loads(to_json(_sample_report()))
    assert data["summary"]["total"] == 2
    assert data["summary"]["passed"] == 1
    assert data["summary"]["failed"] == 1


def test_json_results_include_ok_flags():
    data = json.loads(to_json(_sample_report()))
    first = data["results"][0]
    assert first["before"]["rms_ok"] is False
    assert first["after"]["rms_ok"] is True
    assert first["after"]["peak_ok"] is True


def test_markdown_contains_header_and_table_rows():
    md = to_markdown(_sample_report())
    assert "# acx-rms-fix report" in md
    assert "## Summary" in md
    assert "chapter01.mp3" in md
    assert "chapter02.mp3" in md
    assert "✅ PASS" in md
    assert "❌ FAIL" in md


def test_markdown_all_pass_footer():
    rep = _sample_report()
    rep.results.pop()  # drop the failing one
    md = to_markdown(rep)
    assert "All files meet ACX upload requirements." in md


def test_jsonl_line_is_valid_single_line_json():
    rep = _sample_report()
    line = to_jsonl_line(rep.results[0])
    assert "\n" not in line
    data = json.loads(line)
    assert data["input_path"] == "chapter01.mp3"
    assert data["passed"] is True
    assert data["after"]["rms_ok"] is True


def test_jsonl_line_failed_result():
    rep = _sample_report()
    line = to_jsonl_line(rep.results[1])
    data = json.loads(line)
    assert data["passed"] is False
    assert data["action"] == "check"


def test_write_report_picks_format_from_extension(tmp_path):
    rep = _sample_report()
    md_path = tmp_path / "report.md"
    json_path = tmp_path / "report.json"
    write_report(rep, md_path)
    write_report(rep, json_path)
    # Read explicitly as UTF-8 so this works on Windows, whose default
    # codec (cp1252) can't decode the ✅ / ✗ glyphs in the report.
    assert md_path.read_text(encoding="utf-8").startswith("# acx-rms-fix report")
    assert json.loads(json_path.read_text(encoding="utf-8"))["version"] == "0.1.0"
