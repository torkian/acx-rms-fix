"""Command-line entry point."""

from __future__ import annotations

import argparse
import ctypes
import platform
import sys
from pathlib import Path

from . import __version__
from .core import (
    NOISE_MAX,
    FfmpegMissingError,
    Measurement,
    RunReport,
    process_one,
    require_ffmpeg,
)
from .report import to_jsonl_line, write_report

# ---------------- ANSI colors ----------------


def _supports_color() -> bool:
    if not sys.stdout.isatty():
        return False
    if platform.system() == "Windows":
        try:
            kernel32 = ctypes.windll.kernel32
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            hstdout = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if not kernel32.GetConsoleMode(hstdout, ctypes.byref(mode)):
                return False
            kernel32.SetConsoleMode(hstdout, mode.value | 0x0004)
            return True
        except Exception:
            return False
    return True


_COLOR = _supports_color()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def red(t: str) -> str:
    return _c("31", t)


def green(t: str) -> str:
    return _c("32", t)


def yellow(t: str) -> str:
    return _c("33", t)


def dim(t: str) -> str:
    return _c("2", t)


# ---------------- formatting ----------------


def format_measurement_line(m: Measurement) -> str:
    if m.passes:
        return green(
            f"  PASS  RMS={m.rms_db:.1f} dB  peak={m.peak_db:.1f} dB  "
            f"noise-floor<{NOISE_MAX:.0f} dB"
        )
    return yellow(
        f"  FAIL  RMS={m.rms_db:.1f} dB [{'ok' if m.rms_ok else 'no'}]  "
        f"peak={m.peak_db:.1f} dB [{'ok' if m.peak_ok else 'no'}]  "
        f"noise-floor [{'ok' if m.noise_floor_ok else 'no'}]"
    )


def make_printer(quiet: bool):
    """Return an on_progress callback for core.process_one."""

    def emit(msg: str) -> None:
        if quiet:
            return
        if msg.startswith("  pass ") or msg.startswith("  wrote") or msg.startswith("  replaced"):
            print(dim(msg))
        elif msg.startswith("  error"):
            print(red(msg))
        else:
            print(msg)

    return emit


# ---------------- argparse ----------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="acx-rms-fix",
        description=(
            "Fix ACX audiobook rejection errors — RMS too low, peak too high, "
            "noise floor too high — in one command."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  acx-rms-fix chapter01.mp3\n"
            "  acx-rms-fix -o mastered/ chapter*.mp3\n"
            "  acx-rms-fix --replace chapter01.mp3\n"
            "  acx-rms-fix --check already_processed.mp3\n"
            "  acx-rms-fix -o out/ --report out/report.md chapter*.mp3\n"
        ),
    )
    p.add_argument("inputs", nargs="+", help="input audio files (mp3/wav/flac/m4a)")
    p.add_argument(
        "-o",
        "--out-dir",
        type=Path,
        default=None,
        help="write outputs to this directory (default: alongside input)",
    )
    p.add_argument(
        "-r",
        "--replace",
        action="store_true",
        help="replace input in place; original is saved as *.orig.<ext>",
    )
    p.add_argument(
        "-c",
        "--check",
        action="store_true",
        help="only verify the input, do not re-encode",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=None,
        help="write report file (.json or .md — format picked from extension)",
    )
    p.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="only print errors and summary",
    )
    p.add_argument(
        "--json-lines",
        action="store_true",
        help=(
            "print each file result as a JSON line to stdout as it completes "
            "(implies --quiet; pipe to jq for easy scripting)"
        ),
    )
    p.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return p


# ---------------- main ----------------


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        ffmpeg_version = require_ffmpeg()
    except FfmpegMissingError as exc:
        print(red(f"error: {exc}"), file=sys.stderr)
        return 1

    json_lines = args.json_lines
    report = RunReport(version=__version__, ffmpeg_version=ffmpeg_version)
    emit = make_printer(quiet=args.quiet or json_lines)

    for raw in args.inputs:
        path = Path(raw)
        result = process_one(
            path,
            out_dir=args.out_dir,
            replace=args.replace,
            check_only=args.check,
            on_progress=emit,
        )
        report.results.append(result)
        if json_lines:
            print(to_jsonl_line(result))
        else:
            m = result.after or result.before
            if result.error and not result.after:
                print(red(f"  error: {result.error}"))
            elif m is not None:
                print(format_measurement_line(m))

    if report.results and not json_lines:
        if report.fail_count == 0:
            print(green(f"all {report.pass_count} file(s) ACX-compliant"))
        else:
            print(red(f"{report.fail_count} file(s) did not meet ACX spec"))

    if args.report:
        write_report(report, args.report)
        print(dim(f"report written: {args.report}"))

    return 0 if report.fail_count == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
