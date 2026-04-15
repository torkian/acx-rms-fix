# acx-rms-fix

**Fix ACX audiobook rejection errors — *RMS too low*, *peak too high*, *noise floor too high* — in one command.**

[![test](https://github.com/torkian/acx-rms-fix/actions/workflows/test.yml/badge.svg)](https://github.com/torkian/acx-rms-fix/actions/workflows/test.yml)
[![lint](https://github.com/torkian/acx-rms-fix/actions/workflows/lint.yml/badge.svg)](https://github.com/torkian/acx-rms-fix/actions/workflows/lint.yml)
[![python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

Cross-platform. Ships a **CLI** for power users and a **Tkinter GUI** for everyone else. No DAW, no paid plugins, no upload-your-audio cloud service.

---

## Does ACX keep saying this?

> *RMS is too low. Raise the level of this file 2.3 dB. Visit Guidance Section 1 – Adjusting Low RMS Files on our Audiobook Production RMS Guide for further guidance.*

> *Peak value is too high.*

> *Noise floor is too high.*

You're in the right place. This tool runs a single, known-good **ffmpeg** mastering chain (two-pass `loudnorm` + `afftdn` denoise + `alimiter` brick-wall) and produces an MP3 that passes ACX's upload checker. It works on existing MP3 files (from ElevenLabs, a DAW export, a previous session) as well as raw WAV / FLAC recordings.

---

## Install

### Option A — Download the app (recommended for narrators)

No Python, no terminal, no ffmpeg install. Just download and run.

| Platform | Download | Notes |
|---|---|---|
| **macOS (Apple Silicon, M1/M2/M3/M4)** | [`acx-rms-fix-gui-macos-arm64.dmg`](https://github.com/torkian/acx-rms-fix/releases/latest) | ~30 MB, ffmpeg bundled |
| **Windows 10 / 11 (64-bit)** | [`acx-rms-fix-gui-windows-x64.exe`](https://github.com/torkian/acx-rms-fix/releases/latest) | ~80 MB, ffmpeg bundled |
| **Linux** | build from source (Option B) | standalone binary is on the v0.2 roadmap |
| **macOS Intel** | build from source (Option B) | standalone binary is on the v0.2 roadmap |

**First launch:** because the binaries aren't code-signed (costs $99/yr per OS — deferred until the project has real traction), your OS will warn you the first time:

- **macOS:** right-click the .app → **Open** → *Open* in the confirmation dialog. Only needed once.
- **Windows:** SmartScreen shows *"Windows protected your PC"* → click **More info** → **Run anyway**. Only needed once.

**Verify it works:** open a terminal and run

```sh
# macOS
/Applications/acx-rms-fix-gui.app/Contents/MacOS/acx-rms-fix-gui --selftest

# Windows (PowerShell)
.\acx-rms-fix-gui-windows-x64.exe --selftest
```

You should see `PASS  self-test succeeded — install is healthy`. If not, see [Troubleshooting](docs/troubleshooting.md).

### Option B — Install from source (developers, Linux users, Intel Mac)

Requires Python 3.9+ and ffmpeg on your PATH.

**1. Install Python 3.9 or newer**

- **macOS:** already installed, or `brew install python`
- **Windows:** [python.org/downloads](https://www.python.org/downloads/) — check *"Add Python to PATH"* during install
- **Linux:** `sudo apt install python3 python3-pip` (or your distro's equivalent)

**2. Install ffmpeg**

```sh
# macOS
brew install ffmpeg

# Windows (PowerShell)
winget install Gyan.FFmpeg

# Debian / Ubuntu
sudo apt install ffmpeg
```

Verify: `ffmpeg -version`.

**3. Install acx-rms-fix**

```sh
pipx install git+https://github.com/torkian/acx-rms-fix
```

(Don't have `pipx`? `python -m pip install --user pipx && pipx ensurepath`, then open a new terminal.)

This gives you two commands on your PATH:

- `acx-rms-fix` — the CLI
- `acx-rms-fix-gui` — the GUI window

---

## Usage — GUI (recommended for narrators)

```sh
acx-rms-fix-gui
```

1. Click **+ Add files**, pick your chapter MP3s (you can select many at once).
2. Choose an **Output folder**, or tick **Replace in place** to overwrite (the original is backed up as `*.orig.mp3`).
3. Click **Fix all files**. Watch the list turn green.
4. Click **Save report…** to export a Markdown or JSON report for your producer.
5. Upload the resulting `*_ACX.mp3` files to ACX.

If you see *"ffmpeg not found"* at startup, click *Open the ffmpeg download page* — the GUI will take you straight to the right installer.

---

## Usage — CLI (one-liner)

```sh
acx-rms-fix chapter01.mp3
```

Writes `chapter01_ACX.mp3` next to the original and prints:

```
fix:   chapter01.mp3
  pass 1: analyzing loudness...
  pass 2: normalizing + limiting + encoding...
  wrote: chapter01_ACX.mp3
  PASS  RMS=-20.3 dB  peak=-3.5 dB  noise-floor<-60 dB
all 1 file(s) ACX-compliant
```

### Fix a whole audiobook at once

```sh
acx-rms-fix -o mastered/ chapters/*.mp3
```

### Replace files in place (keeps a backup)

```sh
acx-rms-fix --replace chapter01.mp3
# → chapter01.mp3 (new, mastered), chapter01.orig.mp3 (original)
```

### Check a file without re-encoding

```sh
acx-rms-fix --check chapter01.mp3
```

Returns exit code **0** if the file already passes ACX, **2** if it doesn't. Safe to drop in a Makefile or CI job.

### Generate a report

```sh
acx-rms-fix -o out/ --report out/report.md chapter*.mp3     # Markdown
acx-rms-fix -o out/ --report out/report.json chapter*.mp3   # JSON
```

The report contains one row per file with before/after RMS and peak, pass/fail status, platform info, and ffmpeg version — useful for handing to a producer or archiving with the audiobook project.

### Full flag reference

```
acx-rms-fix [-h] [-o OUT_DIR] [-r] [-c] [--report REPORT] [-q] [-V]
            inputs [inputs ...]

  -o, --out-dir DIR   write outputs to DIR (default: alongside input)
  -r, --replace       replace input in place; original kept as *.orig.<ext>
  -c, --check         only verify the input, do not re-encode
      --report FILE   write report (.md / .markdown → Markdown, else JSON)
  -q, --quiet         only print errors and the summary line
  -V, --version       print version and exit
```

---

## The ACX spec enforced by this tool

| Check         | Requirement              | What this tool does about it                                 |
|---------------|--------------------------|--------------------------------------------------------------|
| **RMS**       | -23 to -18 dBFS          | `loudnorm` normalizes to -20 LUFS (center of the window)      |
| **Peak**      | ≤ -3 dBFS                | `alimiter` brick-walls at -3 dBFS (true-peak aware)           |
| **Noise floor** | ≤ -60 dBFS             | `afftdn` spectral denoise + 80 Hz / 16 kHz band filter        |
| Sample rate   | 44.1 kHz                 | `aresample=44100`                                             |
| Channels      | mono                     | `-ac 1`                                                       |
| Codec         | MP3 192 kbps **CBR**     | `libmp3lame -b:a 192k`                                        |
| Head silence  | 0.5 – 1.0 s              | *not yet — add in your editor*                                |
| Tail silence  | 1 – 5 s                  | *not yet — add in your editor*                                |

See [docs/acx-spec-explained.md](docs/acx-spec-explained.md) for the *why* behind each number.

---

## How it works

The filter chain, in ffmpeg shorthand:

```
afftdn=nr=12:nf=-50            ← spectral noise reduction
→ highpass=f=80                ← remove rumble, plosive thump
→ lowpass=f=16000              ← remove hiss, MP3 pre-echo
→ loudnorm=I=-20:TP=-3.2:LRA=7 ← EBU R128 two-pass normalization
→ aresample=44100              ← 44.1 kHz for ACX
→ alimiter=limit=0.708         ← -3 dBFS brick-wall true-peak ceiling
→ libmp3lame -b:a 192k -ac 1   ← ACX MP3 192 kbps CBR mono
```

Two-pass `loudnorm` is the trick. Pass 1 measures the input's integrated loudness, true peak, loudness range, and threshold. Pass 2 plugs those measurements back in via `measured_I` / `measured_TP` / `measured_LRA` / `measured_thresh` / `offset` to get deterministic, single-encode normalization — the output's integrated loudness lands within ~0.1 LU of -20 LUFS every time.

A one-shot `volume=2.3dB` gain bump **does not** work for this use case: it ignores peaks, and the narrator who just got told *"RMS too low by 2.3 dB"* usually has peaks already sitting near -1 dB. Bumping gain drives them over 0 and the next ACX check fails on *"peak too high"* instead.

Deep dive: [docs/acx-spec-explained.md](docs/acx-spec-explained.md).

---

## Documentation

- [**Getting started**](docs/getting-started.md) — 5-minute walkthrough for narrators who have never used a terminal.
- [**GUI guide**](docs/gui-guide.md) — step-by-step with screenshots.
- [**CLI reference**](docs/cli-reference.md) — every flag, every exit code.
- [**ACX spec explained**](docs/acx-spec-explained.md) — why each rule exists and what it does for your listener.
- [**Troubleshooting**](docs/troubleshooting.md) — common failures and their fixes.

---

## Troubleshooting (quick)

**"ACX still says RMS is too low after I ran acx-rms-fix."**
You probably uploaded the original. Look for the file named `<name>_ACX.mp3` in your output folder — that's the mastered one. Or use `--replace` so both filenames end up mastered.

**"ffmpeg not found on PATH."**
Install it (see [Install](#install)). On Windows, open a new terminal after installing — the old one won't pick up the updated PATH.

**"The voice sounds over-processed / phasey."**
The default denoise is conservative, but clean source files sometimes don't need any. Open `src/acx_rms_fix/core.py`, drop `DENOISE_NR` from `12` to `6`, re-install (`pipx install --force …`), and re-run.

Full list: [docs/troubleshooting.md](docs/troubleshooting.md).

---

## Contributing

Pull requests welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

The project is intentionally small — one package, one test suite, one README — so the entire pipeline can be understood in a single sitting. Please keep it that way.

Good first issues: [good-first-issue label](https://github.com/torkian/acx-rms-fix/labels/good%20first%20issue).

---

## License

MIT — see [LICENSE](LICENSE).

---

## Credits

The filter chain is the standard EBU R128 + true-peak-limiter mastering approach used across the broadcast industry, adapted to ACX's specific RMS/peak window. Two-pass `loudnorm` for deterministic normalization is documented in the [ffmpeg loudnorm manual](https://ffmpeg.org/ffmpeg-filters.html#loudnorm) and is the approach the broadcast-audio community has settled on over years of forum threads and production notes.
