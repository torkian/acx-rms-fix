# Contributing

Thanks for looking! `acx-rms-fix` exists to help audiobook narrators get past ACX rejection errors without learning audio engineering. Contributions that make it *more reliable*, *more discoverable*, or *easier to use* are the most welcome.

This document covers the practical bits: how to get the repo running on your machine, how to run the tests, and what we look for in a pull request.

---

## Ground rules

- **Small, scannable changes.** One concept per PR. Easier to review, easier to revert.
- **Tests for anything non-trivial.** If you add a feature or fix a bug, please add a test that would have caught it.
- **Don't break backwards compatibility without a reason.** People are already running this in their batch scripts.
- **Plain-English commit messages.** Describe *what* and *why*, not the tool or process.

---

## Setting up a dev environment

```sh
git clone https://github.com/torkian/acx-rms-fix
cd acx-rms-fix

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
```

The `[dev]` extra installs pytest and ruff. You also need **ffmpeg** on PATH for the integration tests — see the [Getting started guide](docs/getting-started.md#step-2--install-ffmpeg) for install instructions.

---

## Running the tests

```sh
pytest -v
```

- **Unit tests** monkeypatch ffmpeg so they run anywhere.
- **Integration tests** (`tests/test_integration.py`) actually shell out to ffmpeg. They auto-skip if ffmpeg isn't on PATH.
- **GUI smoke tests** (`tests/test_gui_smoke.py`) construct the main window with `withdraw()` so nothing appears on screen. They auto-skip in truly headless environments.

A full run should finish in a few seconds.

---

## Linting and formatting

```sh
ruff check .
ruff format .
```

CI runs both. Format-check failures block merges; lint errors block merges. Both are fixable with `ruff check --fix` and `ruff format`.

---

## Trying your changes end-to-end

```sh
# Fix a real file through the CLI
acx-rms-fix path/to/some_chapter.mp3

# Launch the GUI
acx-rms-fix-gui
```

If you touched `core.py`, please also re-run the integration tests to make sure a synthesized file still round-trips to an ACX-compliant output.

---

## Project layout

```
src/acx_rms_fix/
  core.py      — measurement, mastering, dataclasses. NO prints, NO sys.exit.
  report.py    — Markdown / JSON serializers.
  cli.py       — argparse, colors, the `acx-rms-fix` entry point.
  gui.py       — Tkinter window, the `acx-rms-fix-gui` entry point.

tests/
  fixtures.py          — synthetic WAV generators (stdlib only, no numpy).
  test_core.py         — unit tests, monkeypatched ffmpeg.
  test_report.py       — report schema tests.
  test_cli.py          — argparse and exit code tests.
  test_gui_smoke.py    — GUI import + construction smoke test.
  test_integration.py  — end-to-end tests that require ffmpeg.
```

**Hard rule:** `core.py` is pure logic. It never calls `print`, it never calls `sys.exit`, it never reads argparse, it never touches Tkinter. All user-facing I/O lives in `cli.py` and `gui.py`. The GUI works because `core.process_one` takes an `on_progress` callback — follow that pattern if you need to surface something new.

---

## Opening a pull request

1. Fork the repo and create a branch off `main`.
2. Make your change. Add tests. Run `ruff check . && ruff format . && pytest -v`.
3. Push and open a PR. The template will ask you a few questions — please fill them in.
4. CI runs on every push (Linux/macOS/Windows × Python 3.9–3.12). All 12 matrix cells must go green before a PR is merged.

---

## What's in scope

**Yes please:**

- Bug fixes, especially for real failing files users have reported.
- Better ffmpeg detection on unusual platforms.
- Documentation improvements — especially anything that helps a non-technical narrator.
- Small GUI polish (layout, accessibility, icons).
- Performance improvements as long as they don't change output audio.
- Additional report formats (CSV? HTML?) if they're genuinely useful.

**Maybe — talk to us first in an issue:**

- Changes to the default filter chain. We're *very* cautious here because any change is a regression risk for files that already work.
- New CLI flags. Ask first whether the new behavior is common enough to deserve a flag vs. a docs note.
- New dependencies. The stdlib-only policy is a design choice — it's why `pipx install` is instant.

**Not in scope:**

- Non-ACX mastering profiles (broadcast, podcast, music). A different project.
- Transcription, chaptering, cover-art generation. A different project.
- Turning this into a web service.

---

## Reporting a bug

[Open an issue](https://github.com/torkian/acx-rms-fix/issues/new/choose) with:

- Your OS, Python version, ffmpeg version, `acx-rms-fix --version`.
- The exact command you ran.
- The full output (copy/paste, don't screenshot).
- A short audio sample that reproduces the issue, if you can share one.

Real failing inputs are the most valuable thing you can give the project.

---

## License

By contributing, you agree your contribution will be licensed under the project's [MIT License](LICENSE).
