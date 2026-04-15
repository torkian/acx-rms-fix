"""Report writers — JSON and Markdown serializers for RunReport."""

from __future__ import annotations

import json
from pathlib import Path

from .core import (
    NOISE_MAX,
    PEAK_MAX,
    RMS_MAX,
    RMS_MIN,
    RunReport,
)


def to_json(report: RunReport) -> str:
    return json.dumps(
        {
            "version": report.version,
            "generated_at": report.generated_at,
            "platform": report.platform,
            "ffmpeg_version": report.ffmpeg_version,
            "spec": report.spec,
            "summary": {
                "total": len(report.results),
                "passed": report.pass_count,
                "failed": report.fail_count,
            },
            "results": [r.to_dict() for r in report.results],
        },
        indent=2,
    )


def to_markdown(report: RunReport) -> str:
    lines: list[str] = []
    lines.append("# acx-rms-fix report")
    lines.append("")
    lines.append(f"- **Generated:** {report.generated_at}")
    lines.append(f"- **Platform:** {report.platform}")
    lines.append(f"- **acx-rms-fix version:** {report.version}")
    lines.append(f"- **ffmpeg:** {report.ffmpeg_version or 'unknown'}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total files: **{len(report.results)}**")
    lines.append(f"- Passed: **{report.pass_count}**")
    lines.append(f"- Failed: **{report.fail_count}**")
    lines.append("")
    lines.append("## ACX spec enforced")
    lines.append("")
    lines.append("| Metric | Target |")
    lines.append("|---|---|")
    lines.append(f"| RMS | {RMS_MIN} to {RMS_MAX} dBFS |")
    lines.append(f"| Peak | ≤ {PEAK_MAX} dBFS |")
    lines.append(f"| Noise floor | ≤ {NOISE_MAX} dBFS |")
    lines.append("| Format | 44.1 kHz mono MP3 192 kbps CBR |")
    lines.append("")
    lines.append("## Per-file results")
    lines.append("")
    lines.append("| File | Action | RMS before | RMS after | Peak after | Noise floor | Result |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in report.results:
        rms_before = (
            f"{r.before.rms_db:.1f} dB" if r.before and r.before.rms_db is not None else "—"
        )
        rms_after = f"{r.after.rms_db:.1f} dB" if r.after and r.after.rms_db is not None else "—"
        peak_after = f"{r.after.peak_db:.1f} dB" if r.after and r.after.peak_db is not None else "—"
        if r.after is None:
            nf_cell = "—"
        else:
            nf_cell = "✓" if r.after.noise_floor_ok else "✗"
        status = "✅ PASS" if r.passed else "❌ FAIL"
        if r.error:
            status = f"❌ ERROR: {r.error}"
        lines.append(
            f"| `{Path(r.input_path).name}` | {r.action} "
            f"| {rms_before} | {rms_after} | {peak_after} | {nf_cell} | {status} |"
        )
    lines.append("")
    if report.fail_count == 0 and report.results:
        lines.append("**All files meet ACX upload requirements.**")
    elif report.fail_count > 0:
        lines.append(f"**{report.fail_count} file(s) still outside spec — see table above.**")
    return "\n".join(lines) + "\n"


def write_report(report: RunReport, path: Path) -> None:
    """Pick format from extension (.md/.markdown → Markdown, else JSON)."""
    ext = path.suffix.lower()
    content = to_markdown(report) if ext in (".md", ".markdown") else to_json(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
