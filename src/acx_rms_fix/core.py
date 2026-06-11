"""
Core logic — measurement, mastering, and result dataclasses.

This module is pure: no `print`, no color, no `sys.exit`, no argparse.
It raises exceptions on failure and returns dataclasses on success.
`cli.py` and `gui.py` are the only modules that touch the user.
"""

from __future__ import annotations

import json
import math
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


# Tolerance (in kbps) around the 192 kbps target when verifying bitrate.
# ffmpeg reports our CBR output as exactly "192 kb/s"; the band leaves a
# little slack for containers that round the reported average.
BITRATE_TOLERANCE = 8


@dataclass
class Measurement:
    # `rms_db` is the integrated/overall RMS level (ffmpeg astats "RMS level"),
    # which is the quantity ACX's RMS check measures. `peak_db` is the TRUE
    # (inter-sample) peak from ffmpeg ebur128 — the value ACX's peak check uses —
    # not the decoded sample peak. `noise_floor_db` is the measured noise floor.
    rms_db: float | None = None
    peak_db: float | None = None
    noise_floor_db: float | None = None
    sample_peak_db: float | None = None  # informational: decoded sample peak
    codec: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    bitrate_kbps: int | None = None

    @property
    def rms_ok(self) -> bool:
        return self.rms_db is not None and RMS_MIN <= self.rms_db <= RMS_MAX

    @property
    def peak_ok(self) -> bool:
        return self.peak_db is not None and self.peak_db <= PEAK_MAX

    @property
    def noise_ok(self) -> bool:
        return self.noise_floor_db is not None and self.noise_floor_db <= NOISE_MAX

    @property
    def format_ok(self) -> bool:
        """True only if codec/sample-rate/channels/bitrate all match ACX spec."""
        return (
            self.codec is not None
            and self.codec.startswith("mp3")
            and self.sample_rate == SAMPLE_RATE
            and self.channels == CHANNELS
            and self.bitrate_kbps is not None
            and abs(self.bitrate_kbps - int(BITRATE.rstrip("k"))) <= BITRATE_TOLERANCE
        )

    @property
    def passes(self) -> bool:
        return self.rms_ok and self.peak_ok and self.noise_ok and self.format_ok


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
                m["noise_ok"] = orig.noise_ok
                m["format_ok"] = orig.format_ok
                # JSON has no Infinity/NaN. Digital silence yields -inf; null it
                # so the report stays valid JSON for strict parsers (jq, etc.).
                for k, v in m.items():
                    if isinstance(v, float) and not math.isfinite(v):
                        m[k] = None
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


# ffmpeg prints dB metrics as a signed number, or "inf"/"-inf"/"nan" for
# digital silence and degenerate input.
_DB_NUM = r"(-?(?:\d+(?:\.\d+)?|inf|nan))"


def _to_db(token: str) -> float:
    t = token.strip().lower()
    if t in ("inf", "+inf"):
        return float("inf")
    if t == "-inf" or "nan" in t:
        # Digital silence / undefined — treat as "infinitely quiet" so a silent
        # passage never trips the noise-floor or RMS thresholds.
        return float("-inf")
    return float(t)


def _parse_stream_info(text: str) -> dict:
    """Pull codec / sample-rate / channels / bitrate from an ffmpeg input banner."""
    info: dict = {"codec": None, "sample_rate": None, "channels": None, "bitrate_kbps": None}
    line_m = re.search(r"Stream #[^\n]*Audio:[^\n]*", text)
    if not line_m:
        return info
    line = line_m.group(0)
    codec_m = re.search(r"Audio:\s*([A-Za-z0-9_]+)", line)
    if codec_m:
        info["codec"] = codec_m.group(1)
    sr_m = re.search(r"(\d+)\s*Hz", line)
    if sr_m:
        info["sample_rate"] = int(sr_m.group(1))
    if re.search(r"\bmono\b", line):
        info["channels"] = 1
    elif re.search(r"\bstereo\b", line):
        info["channels"] = 2
    else:
        ch_m = re.search(r"(\d+)\s*channels", line)
        if ch_m:
            info["channels"] = int(ch_m.group(1))
    br_m = re.search(r"(\d+)\s*kb/s", line)
    if br_m:
        info["bitrate_kbps"] = int(br_m.group(1))
    return info


def _measure_astats(path: Path) -> tuple[float, float, float, dict]:
    """
    Return (rms_db, sample_peak_db, noise_floor_db, stream_info) via ffmpeg
    `astats`. Each metric is taken from the *last* occurrence in the output,
    which is the "Overall" block — correct for both mono and multi-channel input.

    Unlike the old `silencedetect` heuristic (which only proved a quiet gap
    existed), `astats` reports the file's actual measured noise floor.
    """
    cp = _run_ffmpeg(["-i", str(path), "-af", "astats=metadata=0", "-f", "null", _devnull()])
    out = cp.stderr + cp.stdout
    if cp.returncode != 0:
        last = cp.stderr.strip().splitlines()[-1] if cp.stderr.strip() else "unknown"
        raise RuntimeError(f"could not measure {path}: {last}")
    rms = re.findall(rf"RMS level dB:\s*{_DB_NUM}", out)
    peak = re.findall(rf"Peak level dB:\s*{_DB_NUM}", out)
    floor = re.findall(rf"Noise floor dB:\s*{_DB_NUM}", out)
    if not rms or not peak or not floor:
        raise RuntimeError(f"could not parse astats output for {path}")
    return _to_db(rms[-1]), _to_db(peak[-1]), _to_db(floor[-1]), _parse_stream_info(out)


def _measure_true_peak(path: Path) -> float:
    """Return the true (inter-sample) peak in dBFS via ffmpeg `ebur128`.

    ACX's peak check is true-peak aware; the decoded sample peak (astats
    "Peak level") can read several dB lower than the real reconstructed peak.
    """
    cp = _run_ffmpeg(["-i", str(path), "-af", "ebur128=peak=true", "-f", "null", _devnull()])
    out = cp.stderr + cp.stdout
    if cp.returncode != 0:
        last = cp.stderr.strip().splitlines()[-1] if cp.stderr.strip() else "unknown"
        raise RuntimeError(f"could not measure true peak of {path}: {last}")
    m = re.search(rf"True peak:\s*Peak:\s*{_DB_NUM}\s*dBFS", out)
    if not m:
        raise RuntimeError(f"could not parse ebur128 true-peak output for {path}")
    return _to_db(m.group(1))


def measure(path: Path) -> Measurement:
    """Measure all ACX-relevant metrics: RMS, true peak, noise floor, and format."""
    rms_db, sample_peak_db, noise_floor_db, info = _measure_astats(path)
    true_peak_db = _measure_true_peak(path)
    return Measurement(
        rms_db=rms_db,
        peak_db=true_peak_db,
        noise_floor_db=noise_floor_db,
        sample_peak_db=sample_peak_db,
        codec=info["codec"],
        sample_rate=info["sample_rate"],
        channels=info["channels"],
        bitrate_kbps=info["bitrate_kbps"],
    )


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


def _master_atomic(input_path: Path, output_path: Path) -> None:
    """
    Master `input_path` to `output_path`, writing through a temp file in the
    destination directory and renaming on success. An interrupted or failed
    encode therefore never leaves a truncated MP3 at `output_path` (and never
    clobbers a good file already there).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix="acxrmsfix_", suffix=".mp3", dir=str(output_path.parent)
    )
    os.close(tmp_fd)
    tmp_out = Path(tmp_name)
    try:
        master(input_path, tmp_out)
        os.replace(str(tmp_out), str(output_path))  # atomic within one filesystem
    finally:
        if tmp_out.exists():
            try:
                tmp_out.unlink()
            except OSError:
                pass


def planned_output(input_path: Path, out_dir: Path | None, replace: bool) -> Path:
    """Where process_one would write the mastered MP3 for these options.

    Output is always an MP3. Replace is only truly in-place for MP3 input;
    other formats fall back to the standard `<stem>_ACX.mp3` sibling so MP3
    bytes never overwrite a `.wav`/`.flac` container or an unrelated file.
    """
    if replace and input_path.suffix.lower() == ".mp3":
        return input_path
    base = out_dir if out_dir is not None else input_path.parent
    return base / f"{input_path.stem}_ACX.mp3"


def find_output_collisions(
    input_paths: list[Path], out_dir: Path | None, replace: bool
) -> dict[str, list[Path]]:
    """
    Map each output path that more than one input would write to -> those inputs.

    Empty dict means every input has a distinct destination. Shared by the CLI
    and the GUI so both refuse to silently overwrite outputs in a batch run.
    """
    seen: dict[str, list[Path]] = {}
    for p in input_paths:
        target = str(planned_output(p, out_dir, replace).resolve())
        seen.setdefault(target, []).append(p)
    return {t: ps for t, ps in seen.items() if len(ps) > 1}


# ---------------- per-file orchestration ----------------

ProgressFn = Callable[[str], None]


def process_one(
    input_path: Path,
    *,
    out_dir: Path | None = None,
    replace: bool = False,
    check_only: bool = False,
    dry_run: bool = False,
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
    action = (
        "check" if check_only else ("dry-run" if dry_run else ("replace" if replace else "fix"))
    )
    result = FileResult(input_path=str(input_path), output_path=None, action=action)

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

        if dry_run:
            emit(f"dry-run: {input_path}")
            m = measure(input_path)
            result.before = m
            result.passed = m.passes
            planned = planned_output(input_path, out_dir, replace)
            result.output_path = str(planned)
            # A real run always re-masters; it never skips compliant files. Say so.
            note = " (already compliant)" if m.passes else ""
            emit(f"  would write: {planned}{note}")
            result.duration_seconds = (datetime.now(timezone.utc) - t0).total_seconds()
            return result

        result.before = measure(input_path)
        emit(f"fix:   {input_path}")
        emit("  pass 1: analyzing loudness...")

        if replace and input_path.suffix.lower() == ".mp3":
            backup = input_path.with_suffix(".orig.mp3")
            if not backup.exists():
                shutil.copy2(input_path, backup)
            emit("  pass 2: normalizing + limiting + encoding...")
            _master_atomic(input_path, input_path)
            result.output_path = str(input_path)
            emit(f"  replaced in place (backup: {backup.name})")
        elif replace:
            # Replace is meaningful only for MP3 input. For other formats, fall
            # back to the standard <stem>_ACX.mp3 sibling — never overwrite the
            # original container or an unrelated file — and keep the original.
            out_path = planned_output(input_path, out_dir, replace=True)
            emit("  pass 2: normalizing + limiting + encoding...")
            _master_atomic(input_path, out_path)
            result.output_path = str(out_path)
            emit(f"  --replace applies to MP3 only; wrote {out_path.name} (original kept)")
        else:
            out_path = planned_output(input_path, out_dir, replace=False)
            emit("  pass 2: normalizing + limiting + encoding...")
            _master_atomic(input_path, out_path)
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
