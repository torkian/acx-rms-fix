"""
Core logic — measurement, mastering, and result dataclasses.

This module is pure: no `print`, no color, no `sys.exit`, no argparse.
It raises exceptions on failure and returns dataclasses on success.
`cli.py` and `gui.py` are the only modules that touch the user.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# ---------------- ACX spec ----------------

# ACX audiobook upload requirements. These are the numbers the tool
# targets and the thresholds the verification step checks against.
#
# Source: https://help.acx.com/s/article/what-are-acx-s-audio-submission-requirements
RMS_MIN = -23.0  # dBFS
RMS_MAX = -18.0  # dBFS
PEAK_MAX = -3.0  # dBFS
NOISE_MAX = -60.0  # dBFS
SAMPLE_RATE = 44100  # Hz
CHANNELS = 1  # mono
BITRATE = "192k"  # MP3 CBR

# ---------------- mastering parameters ----------------

# Loudnorm (EBU R128) targets. Integrated loudness centered in the
# ACX RMS window; true-peak ceiling sits a fraction below ACX's -3 dB
# rule for safety margin.
TARGET_I = -20.0
TARGET_TP = -3.2
TARGET_LRA = 7.0

# Brick-wall limiter ceiling in linear amplitude. 10**(-3/20) ≈ 0.708.
LIMITER_CEILING = 0.708

# Band filter — nothing useful in the human voice lives outside 80 Hz – 16 kHz.
HIPASS_HZ = 80
LOPASS_HZ = 16000

# afftdn denoise — conservative enough to leave voice natural.
DENOISE_NR = 12
DENOISE_NF = -50


# ---------------- dataclasses ----------------


@dataclass
class Measurement:
    rms_db: float | None = None
    peak_db: float | None = None
    noise_floor_ok: bool = False

    @property
    def rms_ok(self) -> bool:
        return self.rms_db is not None and RMS_MIN <= self.rms_db <= RMS_MAX

    @property
    def peak_ok(self) -> bool:
        return self.peak_db is not None and self.peak_db <= PEAK_MAX

    @property
    def passes(self) -> bool:
        return self.rms_ok and self.peak_ok and self.noise_floor_ok


@dataclass
class FileResult:
    input_path: str
    output_path: str | None
    action: str  # "fix" | "check" | "replace"
    before: Measurement | None = None
    after: Measurement | None = None
    passed: bool = False
    error: str | None = None
    duration_seconds: float | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        for key in ("before", "after"):
            m = d.get(key)
            if m is not None:
                orig = getattr(self, key)
                m["rms_ok"] = orig.rms_ok
                m["peak_ok"] = orig.peak_ok
        return d


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _platform_string() -> str:
    return f"{platform.system()} {platform.release()}"


def _spec_dict() -> dict:
    return {
        "rms_db": [RMS_MIN, RMS_MAX],
        "peak_db_max": PEAK_MAX,
        "noise_floor_db_max": NOISE_MAX,
        "sample_rate_hz": SAMPLE_RATE,
        "channels": "mono" if CHANNELS == 1 else f"{CHANNELS}ch",
        "codec": "libmp3lame",
        "bitrate_kbps": int(BITRATE.rstrip("k")),
    }


@dataclass
class RunReport:
    version: str = ""
    generated_at: str = field(default_factory=_iso_now)
    platform: str = field(default_factory=_platform_string)
    ffmpeg_version: str = ""
    spec: dict = field(default_factory=_spec_dict)
    results: list[FileResult] = field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)


# ---------------- ffmpeg helpers ----------------


class FfmpegMissingError(RuntimeError):
    """Raised when `ffmpeg` cannot be located (bundled or on PATH)."""


def _resolve_ffmpeg() -> str:
    """
    Return an absolute path to a usable ffmpeg executable, or "" if none.

    Resolution order:
      1. A binary bundled next to the frozen executable (PyInstaller's
         sys._MEIPASS). This is how the downloadable .exe / .app ship
         ffmpeg without the user installing anything.
      2. `shutil.which("ffmpeg")` — the system PATH fallback used by
         `pipx` installs and developer environments.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundle_dir = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        exe_name = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
        candidate = bundle_dir / exe_name
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("ffmpeg")
    return found or ""


def require_ffmpeg() -> str:
    """Return the first line of `ffmpeg -version`, or raise FfmpegMissingError."""
    exe = _resolve_ffmpeg()
    if not exe:
        raise FfmpegMissingError(
            "ffmpeg not found.\n"
            "  macOS:   brew install ffmpeg\n"
            "  Windows: winget install Gyan.FFmpeg  (or https://www.gyan.dev/ffmpeg/builds/)\n"
            "  Debian:  sudo apt install ffmpeg\n"
            "Or download the acx-rms-fix-gui bundle from the releases page,\n"
            "which ships ffmpeg inside the app."
        )
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, text=True, check=True).stdout
        return out.splitlines()[0] if out else ""
    except Exception:
        return ""


def _devnull() -> str:
    return "NUL" if platform.system() == "Windows" else "/dev/null"


def _run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    """Run ffmpeg capturing combined stderr/stdout. Never raises on non-zero."""
    exe = _resolve_ffmpeg() or "ffmpeg"
    return subprocess.run(
        [exe, "-hide_banner", "-nostats", *args],
        capture_output=True,
        text=True,
    )


def measure_volume(path: Path) -> tuple[float, float]:
    """Return (mean_volume_db, max_volume_db) from ffmpeg volumedetect."""
    cp = _run_ffmpeg(
        [
            "-i",
            str(path),
            "-filter:a",
            "volumedetect",
            "-f",
            "null",
            _devnull(),
        ]
    )
    out = cp.stderr + cp.stdout
    mean_m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", out)
    max_m = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", out)
    if not mean_m or not max_m:
        raise RuntimeError(f"could not measure volume of {path}")
    return float(mean_m.group(1)), float(max_m.group(1))


def noise_floor_ok(path: Path) -> bool:
    """True if any ≥0.2 s passage sits below -60 dB."""
    cp = _run_ffmpeg(
        [
            "-i",
            str(path),
            "-af",
            "silencedetect=noise=-60dB:d=0.2",
            "-f",
            "null",
            _devnull(),
        ]
    )
    out = cp.stderr + cp.stdout
    return "silence_start" in out


def measure(path: Path) -> Measurement:
    mean, peak = measure_volume(path)
    return Measurement(rms_db=mean, peak_db=peak, noise_floor_ok=noise_floor_ok(path))


# ---------------- mastering ----------------

FILTER_CHAIN_P1 = (
    f"afftdn=nr={DENOISE_NR}:nf={DENOISE_NF},"
    f"highpass=f={HIPASS_HZ},"
    f"lowpass=f={LOPASS_HZ},"
    f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json"
)


def build_filter_chain_p2(
    measured_i: str,
    measured_tp: str,
    measured_lra: str,
    measured_thresh: str,
    offset: str,
) -> str:
    return (
        f"afftdn=nr={DENOISE_NR}:nf={DENOISE_NF},"
        f"highpass=f={HIPASS_HZ},"
        f"lowpass=f={LOPASS_HZ},"
        f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"
        f":measured_I={measured_i}:measured_TP={measured_tp}:measured_LRA={measured_lra}"
        f":measured_thresh={measured_thresh}:offset={offset}:linear=true,"
        f"aresample={SAMPLE_RATE},"
        f"alimiter=limit={LIMITER_CEILING}:level=disabled"
    )


def master(input_path: Path, output_path: Path) -> None:
    """Run two-pass loudnorm + encode output at ACX spec."""
    if not input_path.is_file():
        raise FileNotFoundError(input_path)

    cp1 = _run_ffmpeg(
        [
            "-y",
            "-i",
            str(input_path),
            "-af",
            FILTER_CHAIN_P1,
            "-f",
            "null",
            _devnull(),
        ]
    )
    if cp1.returncode != 0:
        last = cp1.stderr.strip().splitlines()[-1] if cp1.stderr else "unknown"
        raise RuntimeError(f"loudnorm pass 1 failed: {last}")

    stats_text = cp1.stderr + cp1.stdout
    json_match = re.search(r"\{\s*\"input_i\".*?\}", stats_text, re.DOTALL)
    if not json_match:
        raise RuntimeError("could not parse loudnorm pass-1 JSON stats")
    stats = json.loads(json_match.group(0))
    required = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    missing = [k for k in required if k not in stats]
    if missing:
        raise RuntimeError(f"loudnorm pass-1 missing keys: {missing}")

    cp2 = _run_ffmpeg(
        [
            "-y",
            "-i",
            str(input_path),
            "-af",
            build_filter_chain_p2(
                stats["input_i"],
                stats["input_tp"],
                stats["input_lra"],
                stats["input_thresh"],
                stats["target_offset"],
            ),
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            str(CHANNELS),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            BITRATE,
            str(output_path),
        ]
    )
    if cp2.returncode != 0:
        last = cp2.stderr.strip().splitlines()[-1] if cp2.stderr else "unknown"
        raise RuntimeError(f"loudnorm pass 2 encode failed: {last}")


# ---------------- per-file orchestration ----------------

ProgressFn = Callable[[str], None]


def process_one(
    input_path: Path,
    *,
    out_dir: Path | None = None,
    replace: bool = False,
    check_only: bool = False,
    on_progress: ProgressFn | None = None,
) -> FileResult:
    """
    Run the full check-or-fix pipeline on a single file.

    `on_progress` receives short human-readable status strings
    ("pass 1: analyzing loudness...", "wrote: foo.mp3"). If None,
    the function runs silently.
    """

    def emit(msg: str) -> None:
        if on_progress is not None:
            on_progress(msg)

    t0 = datetime.now(timezone.utc)
    result = FileResult(
        input_path=str(input_path),
        output_path=None,
        action="check" if check_only else ("replace" if replace else "fix"),
    )

    if not input_path.is_file():
        result.error = "input not found"
        result.duration_seconds = (datetime.now(timezone.utc) - t0).total_seconds()
        return result

    try:
        if check_only:
            emit(f"check: {input_path}")
            m = measure(input_path)
            result.before = m
            result.after = m
            result.output_path = str(input_path)
            result.passed = m.passes
            result.duration_seconds = (datetime.now(timezone.utc) - t0).total_seconds()
            return result

        result.before = measure(input_path)
        emit(f"fix:   {input_path}")
        emit("  pass 1: analyzing loudness...")

        if replace:
            backup = input_path.with_suffix(f".orig{input_path.suffix}")
            if not backup.exists():
                shutil.copy2(input_path, backup)
            tmp_fd, tmp_name = tempfile.mkstemp(
                prefix="acxrmsfix_", suffix=".mp3", dir=str(input_path.parent)
            )
            os.close(tmp_fd)
            tmp_out = Path(tmp_name)
            try:
                emit("  pass 2: normalizing + limiting + encoding...")
                master(input_path, tmp_out)
                shutil.move(str(tmp_out), str(input_path))
            finally:
                if tmp_out.exists():
                    try:
                        tmp_out.unlink()
                    except OSError:
                        pass
            result.output_path = str(input_path)
            emit(f"  replaced in place (backup: {backup.name})")
        else:
            if out_dir is not None:
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{input_path.stem}_ACX.mp3"
            else:
                out_path = input_path.parent / f"{input_path.stem}_ACX.mp3"
            emit("  pass 2: normalizing + limiting + encoding...")
            master(input_path, out_path)
            result.output_path = str(out_path)
            emit(f"  wrote: {out_path}")

        result.after = measure(Path(result.output_path))
        result.passed = result.after.passes

    except Exception as exc:
        result.error = str(exc)
        result.passed = False
        emit(f"  error: {exc}")

    result.duration_seconds = (datetime.now(timezone.utc) - t0).total_seconds()
    return result
