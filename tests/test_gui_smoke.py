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

import pytest


def test_gui_module_imports():
    """Module must at least be importable — catches syntax / import errors."""
    spec = importlib.util.find_spec("acx_rms_fix.gui")
    assert spec is not None
    module = importlib.import_module("acx_rms_fix.gui")
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
