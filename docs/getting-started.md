# Getting started — for narrators

This guide gets you from *"ACX rejected my chapter"* to *"my file passes ACX"*. **No terminal experience required.** If any step trips you up, open an [issue](https://github.com/torkian/acx-rms-fix/issues) and we'll fix the guide.

---

## What you need

- A computer running Windows 10/11 or macOS (Apple Silicon).
- Your rejected audiobook file(s). Any of MP3, WAV, FLAC, or M4A will work.

---

## The fast path (recommended)

**Step 1 — Download the app.** Go to [the releases page](https://github.com/torkian/acx-rms-fix/releases/latest) and pick the right one:

- **macOS M1/M2/M3/M4:** click `acx-rms-fix-gui-macos-arm64.dmg`
- **Windows 10/11 64-bit:** click `acx-rms-fix-gui-windows-x64.exe`

These are self-contained — they already include ffmpeg inside. You don't need to install Python, ffmpeg, or anything else.

**Step 2 — First launch (one-time only).**

The app isn't code-signed yet (code signing costs $99/year per OS and is on the v0.2 roadmap). Your OS will warn you the first time you open it. This is normal for small open-source tools.

**macOS:**

1. Double-click the `.dmg` file. A window appears with the app inside.
2. Drag `acx-rms-fix-gui.app` into your Applications folder.
3. Open Applications, find the app, **right-click → Open** (not double-click the first time).
4. A dialog says *"acx-rms-fix-gui.app can't be opened because Apple cannot check it for malicious software."* Click **Open**.
5. From now on, regular double-click works.

**Windows:**

1. Double-click `acx-rms-fix-gui-windows-x64.exe`.
2. SmartScreen shows *"Windows protected your PC."*
3. Click the small **More info** link (it's at the top of the dialog).
4. Click **Run anyway**.
5. From now on, Windows remembers and won't ask again.

If you want to confirm the app is healthy, open Terminal (macOS) or PowerShell (Windows) and run it with `--selftest`:

```sh
# macOS
/Applications/acx-rms-fix-gui.app/Contents/MacOS/acx-rms-fix-gui --selftest

# Windows
.\acx-rms-fix-gui-windows-x64.exe --selftest
```

You should see `PASS  self-test succeeded — install is healthy`.

**Step 3 — Drop in your files.** Open the app. Click **+ Add files**, select all the chapter files ACX rejected. Click **Fix all files**. Each row turns green. Click **Save report…** if your producer wants one.

**Step 4 — Upload to ACX.** Look in your output folder for the files ending in `_ACX.mp3`. Those are the mastered versions. Upload those, not the originals.

Done. Skip the rest of this page unless you prefer to install from source.

---

## Alternative — install from source (power users)

If you're on Linux, Intel Mac, or you just want the command-line version, follow these steps.

### Step 1 — Install Python

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
