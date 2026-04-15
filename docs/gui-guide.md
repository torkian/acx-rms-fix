# GUI guide

The `acx-rms-fix-gui` window has everything you need in a single screen. This page walks through it piece by piece.

---

## Launching

After you've installed the tool (see [Getting started](getting-started.md)), run:

```sh
acx-rms-fix-gui
```

On Windows you can also create a desktop shortcut pointing at
`C:\Users\<you>\.local\bin\acx-rms-fix-gui.exe` (or wherever `pipx` installed it).

---

## The window

![GUI layout placeholder](img/gui.png)

From top to bottom:

### 1. File queue

A list showing each audio file you've added, with a status column. Status values:

- **queued** — waiting to be processed
- **processing — pass 1** or **pass 2** — currently being mastered
- **✅ PASS  RMS -20.3 / peak -3.5 dB** — done, meets ACX
- **❌ FAIL  RMS -25.7 · peak -5.8** — done, does NOT meet ACX (rare for mastered output; usually means something unusual about the source)
- **❌ ERROR: …** — the pipeline crashed on this file. Expand the error and report it as an [issue](https://github.com/torkian/acx-rms-fix/issues).

### 2. `+ Add files` and `Clear`

- **Add files** opens a file picker. Hold Shift/Cmd/Ctrl to select multiple. Supported: `.mp3`, `.wav`, `.flac`, `.m4a`, `.aac`.
- **Clear** empties the queue (only works when nothing is currently being processed).

### 3. Output folder

Where the `*_ACX.mp3` files will be written. Default: a folder called `acx-rms-fix-output/` in your home directory. Click **Browse…** to pick a different one.

### 4. Replace files in place

Tick this if you want the mastered file to **overwrite** the original. The original is saved as `*.orig.mp3` next to it, so nothing is ever lost. Useful when your ACX project expects specific filenames that you don't want to rename.

### 5. Progress bar + status

Advances one step per file. The status text shows the current file and phase.

### 6. Fix all files / Save report… / Help

- **Fix all files** starts mastering. Grayed out while it's running so you don't double-start.
- **Save report…** exports a full report of the run — Markdown (`*.md`) for humans, JSON (`*.json`) for scripts. Includes before/after RMS, peak, noise-floor status, ffmpeg version, platform, and pass/fail per file.
- **Help** opens this repository's README in your browser.

---

## A typical run

1. **Add your chapters.** `+ Add files` → select `chapter01.mp3` through `chapter42.mp3`.
2. **Pick an output folder**, or use the default.
3. **Fix all files.** Each row turns green as it finishes. A 30-minute audiobook usually masters in 10-20 seconds.
4. **Save a report**, hand it to your producer, or file it with the project for your records.
5. **Upload the `_ACX.mp3` files to ACX.**

---

## Drag and drop

Native Tkinter doesn't support drag-and-drop without an extra dependency. In v0.1 you need to use **+ Add files**. Drag-and-drop is a v0.2 target — if it matters to you, [upvote the issue](https://github.com/torkian/acx-rms-fix/issues).

---

## Troubleshooting the GUI

**The window doesn't open.**
Run from a terminal so you can see any error: `acx-rms-fix-gui`. If it prints a Python traceback, paste it into a new issue.

**"ffmpeg not found" modal appears at startup.**
Install ffmpeg (see [Getting started Step 2](getting-started.md#step-2--install-ffmpeg)), close the GUI, reopen it.

**A file shows ❌ ERROR with a long message.**
That's a bug in the pipeline or an edge case in your source file. Please [open an issue](https://github.com/torkian/acx-rms-fix/issues/new/choose) with the error text and, if possible, a short sample of the file.
