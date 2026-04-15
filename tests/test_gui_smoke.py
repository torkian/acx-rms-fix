"""
Smoke test for the Tkinter GUI.

We don't automate a full GUI interaction (clicking buttons, opening
file dialogs) — that's out of scope for v0.1. But we do want CI to
catch any import-time or construction-time regression in `gui.py`,
so this test imports the module and constructs the main window with
`withdraw()` so nothing actually appears on screen.

Skipped gracefully on CI runners that have no display at all.
"""

from __future__ import annotations

import importlib.util

import pytest


def _has_tkinter_display() -> bool:
    try:
        import tkinter
    except Exception:
        return False
    try:
        r = tkinter.Tk()
        r.withdraw()
        r.destroy()
    except Exception:
        return False
    return True


requires_display = pytest.mark.skipif(
    not _has_tkinter_display(),
    reason="no Tk display available (headless runner without virtual framebuffer)",
)


def test_gui_module_imports():
    """Module must at least be importable — catches syntax / import errors."""
    spec = importlib.util.find_spec("acx_rms_fix.gui")
    assert spec is not None
    module = importlib.import_module("acx_rms_fix.gui")
    assert callable(module.main)


@requires_display
def test_gui_app_constructs(monkeypatch):
    """Construct AcxRmsFixApp with a withdrawn root — catches widget wiring bugs."""
    import tkinter as tk

    from acx_rms_fix import gui

    # Prevent the ffmpeg-missing modal from popping a real dialog during test.
    def fake_require_ffmpeg():
        return "fake ffmpeg 0.0"

    monkeypatch.setattr(gui, "require_ffmpeg", fake_require_ffmpeg)

    root = tk.Tk()
    root.withdraw()
    try:
        app = gui.AcxRmsFixApp(root)
        assert app.fix_btn is not None
        assert app.save_btn is not None
        assert app.tree is not None
        assert "fake ffmpeg" in app.report.ffmpeg_version
    finally:
        root.destroy()
