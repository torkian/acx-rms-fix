"""
Smoke test for the Tkinter GUI.

We don't automate a full GUI interaction (clicking buttons, opening
file dialogs) — that's out of scope for v0.1. But we do want CI to
catch any import-time or construction-time regression in `gui.py`,
so this test imports the module and constructs the main window with
`withdraw()` so nothing actually appears on screen.

The construction test skips on any `TclError` (which covers headless
runners, Linux VMs without X, and broken Tcl installs like the
windows-py3.12 runner image whose `init.tcl` file is missing).
"""

from __future__ import annotations

import importlib.util
import re

import pytest


def test_report_default_filename_format():
    """Default report filename must embed an ISO-8601-ish timestamp."""
    try:
        from acx_rms_fix.gui import _report_default_filename
    except ImportError as exc:
        pytest.skip(f"tkinter not available: {exc}")

    name = _report_default_filename()
    assert name.startswith("acx-rms-fix-report-")
    assert name.endswith(".md")
    ts_part = name[len("acx-rms-fix-report-") : -len(".md")]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}", ts_part), ts_part

    name_json = _report_default_filename(ext=".json")
    assert name_json.endswith(".json")


def test_gui_module_imports():
    """Module must at least be importable — catches syntax / import errors."""
    try:
        import tkinter  # noqa: F401
    except ImportError as exc:
        pytest.skip(f"tkinter not available: {exc}")
    spec = importlib.util.find_spec("acx_rms_fix.gui")
    assert spec is not None
    try:
        module = importlib.import_module("acx_rms_fix.gui")
    except ImportError as exc:
        pytest.skip(f"tkinter not available: {exc}")
    assert callable(module.main)


def test_gui_app_constructs(monkeypatch):
    """Construct AcxRmsFixApp with a withdrawn root — catches widget wiring bugs."""
    try:
        import tkinter as tk
    except ImportError as exc:
        pytest.skip(f"tkinter not available: {exc}")

    from acx_rms_fix import gui

    # Prevent the ffmpeg-missing modal from popping a real dialog during test.
    def fake_require_ffmpeg():
        return "fake ffmpeg 0.0"

    monkeypatch.setattr(gui, "require_ffmpeg", fake_require_ffmpeg)

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not usable on this runner: {exc}")

    root.withdraw()
    try:
        try:
            app = gui.AcxRmsFixApp(root)
        except tk.TclError as exc:
            pytest.skip(f"Tk widget construction failed on this runner: {exc}")
        assert app.fix_btn is not None
        assert app.save_btn is not None
        assert app.tree is not None
        assert "fake ffmpeg" in app.report.ffmpeg_version
    finally:
        root.destroy()


def test_gui_collision_guard_blocks_start(monkeypatch, tmp_path):
    """Two queued files with the same stem must trigger an error and not start work."""
    try:
        import tkinter as tk
    except ImportError as exc:
        pytest.skip(f"tkinter not available: {exc}")

    from acx_rms_fix import gui

    monkeypatch.setattr(gui, "require_ffmpeg", lambda: "fake ffmpeg 0.0")

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not usable on this runner: {exc}")

    root.withdraw()
    try:
        try:
            app = gui.AcxRmsFixApp(root)
        except tk.TclError as exc:
            pytest.skip(f"Tk widget construction failed on this runner: {exc}")

        a = tmp_path / "x" / "ch1.wav"
        b = tmp_path / "y" / "ch1.wav"
        a.parent.mkdir()
        b.parent.mkdir()
        a.write_bytes(b"a")
        b.write_bytes(b"b")
        app.queue_files = [a, b]
        app.out_var.set(str(tmp_path / "out"))
        app.replace_var.set(False)

        errors = []
        monkeypatch.setattr(gui.messagebox, "showerror", lambda *a, **k: errors.append(a))
        app._on_fix_all()

        assert errors, "expected a collision error dialog"
        assert app.worker is None, "worker must not start when outputs collide"
    finally:
        root.destroy()
