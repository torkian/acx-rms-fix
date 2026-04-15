# Changelog

All notable changes to `acx-rms-fix` are documented here. Format loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning loosely on [SemVer](https://semver.org/).

## [Unreleased]

### Planned

- Standalone binaries via PyInstaller (single `.exe` / `.app` download, no Python required).
- Publish to PyPI so `pipx install acx-rms-fix` works without `git+`.
- Head / tail silence insertion (`--head 0.75 --tail 2.0`).
- WAV / FLAC output modes for narrators who keep masters in WAV.
- Drag-and-drop in the GUI.
- Homebrew tap.
- Real screenshots in `docs/`.

---

## [0.1.0] — initial release

First public release. Turns the known-good ffmpeg mastering chain into an installable, tested, cross-platform tool.

### Added

- **CLI** (`acx-rms-fix`):
  - Single-file or batch mastering to ACX spec (`-o out/ *.mp3`).
  - `--replace` mode with automatic `*.orig.<ext>` backup.
  - `--check` mode that measures without re-encoding (exit 0 / 2 for CI).
  - `--report` flag writing Markdown or JSON depending on extension.
  - Exit codes 0 / 1 / 2 for "all pass" / "usage or ffmpeg missing" / "one or more failed".
  - Colorized output on terminals that support it (Linux, macOS, Windows 10+).
- **GUI** (`acx-rms-fix-gui`):
  - Tkinter window with a file queue, output folder picker, progress bar, per-file status, and a report exporter.
  - Background worker thread so the UI stays responsive.
  - Friendly modal when ffmpeg is missing, with a button to open the install page.
- **Mastering pipeline** (`src/acx_rms_fix/core.py`):
  - Two-pass `loudnorm` (EBU R128) targeting -20 LUFS.
  - `afftdn` spectral denoise + 80 Hz highpass + 16 kHz lowpass.
  - `alimiter` brick-wall at -3 dBFS true-peak ceiling.
  - 44.1 kHz mono MP3 192 kbps CBR output (matches ACX spec).
  - `process_one()` returns dataclass results and accepts an `on_progress` callback for CLI or GUI.
- **Reporting** (`src/acx_rms_fix/report.py`):
  - Markdown and JSON serializers.
  - Includes platform, ffmpeg version, per-file before/after metrics.
- **Test suite** (`tests/`):
  - 38 tests across unit, integration, and GUI smoke.
  - Synthetic WAV fixtures generated at runtime from the stdlib (`wave` + `struct` + `math` + `random`) — no binary audio committed to the repo.
  - Integration tests cover both WAV-input and MP3-input paths.
  - Auto-skips integration tests when ffmpeg isn't on PATH.
- **CI** (`.github/workflows/`):
  - Test matrix: Linux, macOS, Windows × Python 3.9, 3.10, 3.11, 3.12.
  - Ruff lint + format check on every push.
- **Documentation** (`docs/`):
  - `getting-started.md` — non-technical narrator walkthrough.
  - `gui-guide.md` — step-by-step GUI reference.
  - `cli-reference.md` — every flag and exit code.
  - `acx-spec-explained.md` — why each ACX rule exists and what the tool does about it.
  - `troubleshooting.md` — common failures and their fixes.
- **Project hygiene**:
  - `pyproject.toml` with console entry points.
  - `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue and PR templates.
  - MIT license.
