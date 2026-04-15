# Troubleshooting

Start here if something went wrong. The cases are in order of how often they trip people up.

---

## "ACX still says RMS is too low even after I ran acx-rms-fix"

**Almost always: you uploaded the original file, not the mastered one.**

The tool writes its output as `<name>_ACX.mp3` — the `_ACX` suffix is the key. If your input was `chapter01.mp3`, look for `chapter01_ACX.mp3` in your output folder. That's the one to upload.

If you want both filenames to point to the mastered version, re-run with `--replace`:

```sh
acx-rms-fix --replace chapter01.mp3
```

After this, `chapter01.mp3` is the mastered version and `chapter01.orig.mp3` is the preserved original.

**Verify with --check:** if you're not sure which file is which, run:

```sh
acx-rms-fix --check chapter01.mp3 chapter01_ACX.mp3
```

You'll see PASS next to the correct one and FAIL next to the other.

---

## "ffmpeg not found on PATH"

Install ffmpeg.

- **Windows:** `winget install Gyan.FFmpeg` in PowerShell, then **open a new terminal** (the existing one still has the old PATH). If `winget` isn't available, download from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/), extract, and add `bin\` to PATH manually.
- **macOS:** `brew install ffmpeg`. If Homebrew isn't installed, first run the install command from [brew.sh](https://brew.sh).
- **Linux:** `sudo apt install ffmpeg` (Debian/Ubuntu), `sudo dnf install ffmpeg` (Fedora), `sudo pacman -S ffmpeg` (Arch).

**Verify:** `ffmpeg -version` should print several lines.

---

## "acx-rms-fix: command not found"

The `pipx install` finished, but your PATH doesn't include pipx's bin directory.

Run:

```sh
python -m pipx ensurepath
```

Then **open a new terminal** and try again.

---

## ACX says "peak value is too high" after running the tool

This is very rare — the pipeline has two separate peak-limiting stages. If you see it:

1. **Run `acx-rms-fix --check`** on the output file. If the local check shows `peak` above -3, you hit an edge case we want to fix — please [open an issue](https://github.com/torkian/acx-rms-fix/issues/new/choose) with the file or a short sample.
2. If the local check passes but ACX still rejects, it's a measurement disagreement. As a workaround, lower the limiter ceiling: open `src/acx_rms_fix/core.py`, change `LIMITER_CEILING = 0.708` to `LIMITER_CEILING = 0.65` (about -3.7 dB), re-install with `pipx install --force git+https://github.com/torkian/acx-rms-fix`, and re-run.

---

## ACX says "noise floor is too high" after running the tool

Usually means your source file has structural noise (fan, HVAC, hum) that the default denoise settings can't fully remove. Try:

1. **Increase denoise strength.** Open `src/acx_rms_fix/core.py`, change `DENOISE_NR = 12` to `DENOISE_NR = 18`. Re-install and re-run. Higher values remove more noise but at some point make the voice sound "phasey" or "underwatery" — stop if you can hear artefacts on playback.
2. **Clean the source at the recording end.** Record in a quieter room, or use a dedicated denoiser upstream ([rnnoise](https://github.com/xiph/rnnoise) is free; iZotope RX and Adobe Audition are paid).
3. **Check that you're actually uploading the mastered file** (see first section).

---

## The voice sounds over-processed / phasey / underwatery

The default denoise (`nr=12`) is conservative, but very clean source files — good microphone, treated room, careful narrator — don't need any denoising, and any is too much.

Open `src/acx_rms_fix/core.py` and change `DENOISE_NR = 12` to `DENOISE_NR = 6`, or disable `afftdn` entirely by editing the filter chain to remove the `afftdn=nr=12:nf=-50,` prefix. Re-install and re-run.

---

## The tool runs but takes forever on one file

First run on a big file can be slow because ffmpeg is doing two passes. A 30-minute chapter usually masters in 10–20 seconds; a 5-hour audiobook in 1–2 minutes. If a single file takes minutes, something is off — please [open an issue](https://github.com/torkian/acx-rms-fix/issues/new/choose) with the file duration and your CPU.

---

## "Permission denied" when writing to the output folder

The folder you pointed `--out-dir` at isn't writable by your user account. Pick a folder inside your home directory (`~/acx-rms-fix-output/` or `C:\Users\<you>\Documents\mastered\`).

On macOS, if the folder is inside iCloud Drive / Documents and you hit permissions issues, try a local folder like `~/Desktop/mastered/` instead.

---

## Tests fail when I run `pytest` locally

- **Unit tests failing** — most likely a Python version mismatch. The project targets Python 3.9+. Check `python --version`.
- **Integration tests failing** — ffmpeg is either missing or a different version than the one we tested against. Run `ffmpeg -version` to confirm it's present; if it's ffmpeg 4.x or older, upgrade to ffmpeg 5+ and try again.
- **Everything failing with `ModuleNotFoundError: acx_rms_fix`** — you forgot `pip install -e .[test]`. Run it from the repo root.

---

## Something else

Open an [issue](https://github.com/torkian/acx-rms-fix/issues/new/choose). A real failing file — even a 5-second sample — is the most valuable thing we can test against. Include:

- Your OS + version
- `python --version`
- `ffmpeg -version | head -1`
- `acx-rms-fix --version`
- The exact command you ran
- The full output (copy/paste — don't screenshot)
- If possible, a short audio sample that reproduces the issue
