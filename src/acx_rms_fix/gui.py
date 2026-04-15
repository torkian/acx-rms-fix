"""
Tkinter GUI — for narrators who would rather not open a terminal.

Single-window layout:

    ┌─ acx-rms-fix ─────────────────────────────────┐
    │  Click "Add files" to queue MP3/WAV/FLAC files│
    │  ┌───────────────────────────────────────────┐│
    │  │ chapter01.mp3   ✅ PASS  -20.3 / -3.5 dB  ││
    │  │ chapter02.mp3   ⏳ processing pass 2      ││
    │  │ chapter03.mp3   queued                    ││
    │  └───────────────────────────────────────────┘│
    │  [+ Add files]  [Clear]                       │
    │  Output: [ /path/mastered ]    [Browse…]      │
    │  [ ] Replace files in place (keep .orig)      │
    │  [━━━━━━ 66% ]   processing chapter02.mp3     │
    │  [ Fix all files ] [ Save report… ] [ Help ]  │
    └───────────────────────────────────────────────┘

Work runs in a background thread so the UI stays responsive. Thread
handoff is via `tk.after(0, fn)` on the main loop — no locks, no
shared state beyond the Treeview.
"""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .core import (
    FfmpegMissingError,
    FileResult,
    Measurement,
    RunReport,
    process_one,
    require_ffmpeg,
)
from .report import write_report

HELP_URL = "https://github.com/torkian/acx-rms-fix#readme"
FFMPEG_DOWNLOAD_URL_WINDOWS = "https://www.gyan.dev/ffmpeg/builds/"
FFMPEG_DOWNLOAD_URL_GENERIC = "https://ffmpeg.org/download.html"


def _status_for(result: FileResult, m: Measurement | None) -> str:
    if result.error:
        return f"❌ ERROR: {result.error}"
    if m is None:
        return "queued"
    if result.passed:
        return (
            f"✅ PASS  RMS {m.rms_db:.1f} / peak {m.peak_db:.1f} dB"
            if m.rms_db is not None and m.peak_db is not None
            else "✅ PASS"
        )
    reasons = []
    if not m.rms_ok:
        reasons.append(f"RMS {m.rms_db:.1f}" if m.rms_db is not None else "RMS ?")
    if not m.peak_ok:
        reasons.append(f"peak {m.peak_db:.1f}" if m.peak_db is not None else "peak ?")
    if not m.noise_floor_ok:
        reasons.append("noise floor")
    return "❌ FAIL " + " · ".join(reasons) if reasons else "❌ FAIL"


class AcxRmsFixApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"acx-rms-fix v{__version__}")
        self.root.geometry("780x520")
        self.root.minsize(640, 420)

        self.queue_files: list[Path] = []
        self.results: list[FileResult] = []
        self.report = RunReport(version=__version__)
        self.worker: threading.Thread | None = None
        self.msg_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self._build_widgets()
        self._schedule_msg_pump()
        self._check_ffmpeg_on_startup()

    # ---------------- widget construction ----------------

    def _build_widgets(self) -> None:
        pad = {"padx": 10, "pady": 6}

        header = ttk.Label(
            self.root,
            text=(
                "Fix ACX audiobook rejection errors — RMS too low, peak too high,\n"
                "noise floor too high — in one click."
            ),
            justify="left",
        )
        header.pack(anchor="w", **pad)

        # File queue
        tree_frame = ttk.Frame(self.root)
        tree_frame.pack(fill="both", expand=True, **pad)

        columns = ("file", "status")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=10)
        self.tree.heading("file", text="File")
        self.tree.heading("status", text="Status")
        self.tree.column("file", width=300, anchor="w")
        self.tree.column("status", width=420, anchor="w")

        vs = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")

        # Queue controls
        queue_bar = ttk.Frame(self.root)
        queue_bar.pack(fill="x", **pad)
        ttk.Button(queue_bar, text="+ Add files", command=self._on_add_files).pack(side="left")
        ttk.Button(queue_bar, text="Clear", command=self._on_clear).pack(side="left", padx=(6, 0))

        # Output folder
        out_bar = ttk.Frame(self.root)
        out_bar.pack(fill="x", **pad)
        ttk.Label(out_bar, text="Output folder:").pack(side="left")
        self.out_var = tk.StringVar(value=str(Path.home() / "acx-rms-fix-output"))
        out_entry = ttk.Entry(out_bar, textvariable=self.out_var)
        out_entry.pack(side="left", fill="x", expand=True, padx=(6, 6))
        ttk.Button(out_bar, text="Browse…", command=self._on_browse).pack(side="left")

        # Replace-in-place toggle
        self.replace_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.root,
            text="Replace files in place (original kept as *.orig.<ext>)",
            variable=self.replace_var,
        ).pack(anchor="w", **pad)

        # Progress + status
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill="x", **pad)
        self.progress = ttk.Progressbar(status_frame, mode="determinate", maximum=1)
        self.progress.pack(side="left", fill="x", expand=True)
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(status_frame, textvariable=self.status_var).pack(side="left", padx=(10, 0))

        # Action buttons
        action_bar = ttk.Frame(self.root)
        action_bar.pack(fill="x", **pad)
        self.fix_btn = ttk.Button(action_bar, text="Fix all files", command=self._on_fix_all)
        self.fix_btn.pack(side="left")
        self.save_btn = ttk.Button(
            action_bar, text="Save report…", command=self._on_save_report, state="disabled"
        )
        self.save_btn.pack(side="left", padx=(6, 0))
        ttk.Button(action_bar, text="Help", command=self._on_help).pack(side="right")

    # ---------------- ffmpeg check ----------------

    def _check_ffmpeg_on_startup(self) -> None:
        try:
            version = require_ffmpeg()
            self.report.ffmpeg_version = version
        except FfmpegMissingError as exc:
            url = (
                FFMPEG_DOWNLOAD_URL_WINDOWS
                if sys.platform.startswith("win")
                else FFMPEG_DOWNLOAD_URL_GENERIC
            )
            result = messagebox.askquestion(
                "ffmpeg not found",
                (
                    "acx-rms-fix needs ffmpeg to run, and it was not found on your "
                    "PATH.\n\n"
                    f"{exc}\n\n"
                    "Open the ffmpeg download page now?"
                ),
                icon="warning",
            )
            if result == "yes":
                webbrowser.open(url)
            self.fix_btn.state(["disabled"])
            self.status_var.set("ffmpeg missing — install it and restart.")

    # ---------------- queue management ----------------

    def _on_add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Add audio files",
            filetypes=[
                ("Audio files", "*.mp3 *.wav *.flac *.m4a *.aac"),
                ("All files", "*.*"),
            ],
        )
        for p in paths:
            path = Path(p)
            if path not in self.queue_files:
                self.queue_files.append(path)
                self.tree.insert("", "end", iid=str(path), values=(path.name, "queued"))

    def _on_clear(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.queue_files.clear()
        self.results.clear()
        self.report = RunReport(version=__version__, ffmpeg_version=self.report.ffmpeg_version)
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.progress["value"] = 0
        self.status_var.set("Ready.")
        self.save_btn.state(["disabled"])

    def _on_browse(self) -> None:
        initial = self.out_var.get() or str(Path.home())
        chosen = filedialog.askdirectory(title="Choose output folder", initialdir=initial)
        if chosen:
            self.out_var.set(chosen)

    # ---------------- main action: fix all ----------------

    def _on_fix_all(self) -> None:
        if not self.queue_files:
            messagebox.showinfo("Nothing to do", "Add some audio files first.")
            return
        if self.worker and self.worker.is_alive():
            return

        out_dir = None if self.replace_var.get() else Path(self.out_var.get())
        replace = self.replace_var.get()

        self.fix_btn.state(["disabled"])
        self.save_btn.state(["disabled"])
        self.progress["maximum"] = len(self.queue_files)
        self.progress["value"] = 0
        self.results.clear()
        self.report = RunReport(version=__version__, ffmpeg_version=self.report.ffmpeg_version)

        self.worker = threading.Thread(
            target=self._worker_run,
            args=(list(self.queue_files), out_dir, replace),
            daemon=True,
        )
        self.worker.start()

    def _worker_run(self, files: list[Path], out_dir: Path | None, replace: bool) -> None:
        for path in files:
            self.msg_queue.put(("start", path))

            def progress_cb(msg: str, path=path) -> None:
                self.msg_queue.put(("progress", (path, msg)))

            try:
                result = process_one(
                    path,
                    out_dir=out_dir,
                    replace=replace,
                    on_progress=progress_cb,
                )
            except Exception as exc:
                result = FileResult(
                    input_path=str(path),
                    output_path=None,
                    action="fix",
                    error=str(exc),
                )
            self.msg_queue.put(("done", result))
        self.msg_queue.put(("finished", None))

    # ---------------- main-thread message pump ----------------

    def _schedule_msg_pump(self) -> None:
        self._drain_msg_queue()
        self.root.after(100, self._schedule_msg_pump)

    def _drain_msg_queue(self) -> None:
        while True:
            try:
                tag, payload = self.msg_queue.get_nowait()
            except queue.Empty:
                return

            if tag == "start":
                path: Path = payload  # type: ignore[assignment]
                self.status_var.set(f"Processing {path.name}")
                if self.tree.exists(str(path)):
                    self.tree.item(str(path), values=(path.name, "processing…"))
            elif tag == "progress":
                path, msg = payload  # type: ignore[misc]
                if msg.strip().startswith("pass"):
                    short = msg.strip()
                    if self.tree.exists(str(path)):
                        self.tree.item(str(path), values=(path.name, f"processing — {short}"))
            elif tag == "done":
                result: FileResult = payload  # type: ignore[assignment]
                self.results.append(result)
                self.report.results.append(result)
                m = result.after or result.before
                status = _status_for(result, m)
                iid = result.input_path
                if self.tree.exists(iid):
                    self.tree.item(iid, values=(Path(iid).name, status))
                self.progress.step(1)
            elif tag == "finished":
                self._on_worker_finished()

    def _on_worker_finished(self) -> None:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        if failed == 0 and total > 0:
            self.status_var.set(f"All {passed} file(s) ACX-compliant ✅")
        elif total > 0:
            self.status_var.set(f"{passed}/{total} passed — {failed} need attention")
        self.fix_btn.state(["!disabled"])
        if self.results:
            self.save_btn.state(["!disabled"])

    # ---------------- report + help ----------------

    def _on_save_report(self) -> None:
        if not self.results:
            return
        path = filedialog.asksaveasfilename(
            title="Save report",
            defaultextension=".md",
            filetypes=[
                ("Markdown report", "*.md"),
                ("JSON report", "*.json"),
                ("All files", "*.*"),
            ],
            initialfile="acx-rms-fix-report.md",
        )
        if not path:
            return
        write_report(self.report, Path(path))
        messagebox.showinfo("Report saved", f"Wrote {path}")

    def _on_help(self) -> None:
        webbrowser.open(HELP_URL)


# ---------------- headless self-test ----------------


def _run_selftest() -> int:
    """
    Headless round-trip: synthesize a quiet WAV, master it, measure
    the output, print the result. Returns 0 on success, non-zero on
    any failure. Used by end users to validate an install without
    having to open the GUI, and by CI to smoke-test the frozen binary.
    """
    import math
    import struct
    import tempfile
    import wave
    from pathlib import Path as _Path

    from .core import (
        PEAK_MAX,
        RMS_MAX,
        RMS_MIN,
        _resolve_ffmpeg,
        master,
        measure,
        require_ffmpeg,
    )

    print("acx-rms-fix self-test")
    print("=" * 40)

    try:
        version = require_ffmpeg()
    except Exception as exc:
        print(f"FAIL  could not locate ffmpeg: {exc}")
        return 1

    print(f"ffmpeg: {_resolve_ffmpeg()}")
    print(f"version: {version or '(unknown)'}")

    with tempfile.TemporaryDirectory(prefix="acxrmsfix-selftest-") as d:
        src = _Path(d) / "source.wav"
        out = _Path(d) / "source_ACX.mp3"

        sr = 44100
        duration_s = 2.0
        rms_db = -28.0
        peak_amp = int(32767 * (10 ** (rms_db / 20)) * math.sqrt(2))
        silence_samples = int(sr * 0.3)
        tone_samples = int(sr * duration_s)

        samples: list[int] = []
        for _ in range(silence_samples):
            samples.append(0)
        for n in range(tone_samples):
            v = int(peak_amp * math.sin(2 * math.pi * 440.0 * n / sr))
            samples.append(max(-32768, min(32767, v)))
        for _ in range(silence_samples):
            samples.append(0)

        with wave.open(str(src), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(b"".join(struct.pack("<h", s) for s in samples))

        try:
            master(src, out)
        except Exception as exc:
            print(f"FAIL  master(): {exc}")
            return 1

        m = measure(out)
        print(f"output RMS:  {m.rms_db:.1f} dB  (target {RMS_MIN}..{RMS_MAX})")
        print(f"output peak: {m.peak_db:.1f} dB  (max {PEAK_MAX})")
        print(f"noise floor ok: {m.noise_floor_ok}")

        if not m.passes:
            print("FAIL  output did not meet ACX spec")
            return 1

        print("PASS  self-test succeeded — install is healthy")
        return 0


# ---------------- entry point ----------------


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="acx-rms-fix-gui",
        description="acx-rms-fix GUI (Tkinter).",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run a headless round-trip test against the bundled ffmpeg and exit",
    )
    args, _ = parser.parse_known_args()

    if args.selftest:
        return _run_selftest()

    root = tk.Tk()
    try:
        AcxRmsFixApp(root)
    except Exception as exc:  # pragma: no cover
        messagebox.showerror("acx-rms-fix failed to start", str(exc))
        return 1
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
