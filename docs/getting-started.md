# Getting started — for narrators

This guide gets you from *"ACX rejected my chapter"* to *"my file passes ACX"* in five steps. **No terminal experience required.** If any step trips you up, open an [issue](https://github.com/torkian/acx-rms-fix/issues) and we'll fix the guide.

---

## What you need

- A computer running Windows 10/11, macOS, or Linux.
- About 15 minutes for first-time setup. After that it's seconds per file.
- Your rejected audiobook file(s). Any of MP3, WAV, FLAC, or M4A will work.

---

## Step 1 — Install Python

Python is a free programming language. `acx-rms-fix` runs on top of it, but you won't have to write any Python code yourself.

### Windows

1. Go to [python.org/downloads](https://www.python.org/downloads/).
2. Click the big yellow **Download Python** button.
3. Run the installer. **Very important:** tick the box that says **"Add Python to PATH"** at the bottom of the first screen.
4. Click *Install Now*. When it finishes, click *Close*.

### macOS

1. Open the Terminal app (press ⌘-Space, type "Terminal", press Enter).
2. Paste this, press Enter: `brew install python`
3. If it says *"brew: command not found"*, install Homebrew first from [brew.sh](https://brew.sh), then repeat.

### Linux

Open a terminal and run `sudo apt install python3 python3-pip` (Debian/Ubuntu) or your distro's equivalent.

**Verify:** open a new terminal and type `python --version` (Windows) or `python3 --version` (macOS/Linux). You should see `Python 3.9` or higher.

---

## Step 2 — Install ffmpeg

`ffmpeg` is a free audio/video tool that does the actual audio processing. `acx-rms-fix` drives it for you, but ffmpeg has to be installed separately.

### Windows

Open PowerShell (right-click the Start button → *Terminal* or *Windows PowerShell*) and paste:

```powershell
winget install Gyan.FFmpeg
```

If `winget` isn't available (older Windows 10), download the **release-essentials** ZIP from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/), extract it to `C:\ffmpeg`, and add `C:\ffmpeg\bin` to your PATH. [Instructions](https://www.wikihow.com/Install-FFmpeg-on-Windows).

### macOS

```sh
brew install ffmpeg
```

### Linux

```sh
sudo apt install ffmpeg
```

**Verify:** in a new terminal, type `ffmpeg -version`. It should print a few lines starting with `ffmpeg version`.

---

## Step 3 — Install acx-rms-fix

In a terminal, run:

```sh
pipx install git+https://github.com/torkian/acx-rms-fix
```

Don't have `pipx`? Run this first:

```sh
python -m pip install --user pipx
python -m pipx ensurepath
```

Then **close and reopen the terminal** and try the `pipx install` line again.

**Verify:** `acx-rms-fix --version` should print `acx-rms-fix 0.1.0` (or newer).

---

## Step 4 — Open the GUI and drop in your files

```sh
acx-rms-fix-gui
```

A window opens. It looks like this:

![GUI screenshot placeholder](img/gui.png)

1. Click **+ Add files**. Select all the chapter files ACX rejected. You can pick many at once.
2. The files appear in the list with status *queued*.
3. Pick an **Output folder** (or leave the default — it creates `acx-rms-fix-output/` in your home folder).
4. Click **Fix all files**. Each row turns green as it finishes.
5. When the status bar says *"All N file(s) ACX-compliant ✅"*, you're done.

Optional: click **Save report…** to export a Markdown or JSON report of what changed — handy for handing to a producer or archiving with the project.

---

## Step 5 — Upload to ACX

Go to your ACX project and upload the **`*_ACX.mp3`** files from your output folder. These are the mastered versions.

**Do not upload the originals.** If you get the *"RMS is too low"* error again, double-check which file you uploaded — the one with `_ACX` in the name is the mastered one.

If ACX still rejects the mastered file for any reason, see [Troubleshooting](troubleshooting.md).

---

## Going further

- **Command line users:** see [CLI reference](cli-reference.md).
- **Want to know what the tool is actually doing to your audio?** See [ACX spec explained](acx-spec-explained.md).
- **Something went wrong?** See [Troubleshooting](troubleshooting.md).
- **Found a bug?** Please [open an issue](https://github.com/torkian/acx-rms-fix/issues/new/choose) — a real failing file is the most valuable thing we can test against.
