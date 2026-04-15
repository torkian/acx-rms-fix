# CLI reference

Complete reference for the `acx-rms-fix` command. For a walkthrough, see [Getting started](getting-started.md).

---

## Synopsis

```
acx-rms-fix [-h] [-V] [-o OUT_DIR] [-r] [-c] [--report REPORT] [-q]
            inputs [inputs ...]
```

---

## Positional arguments

### `inputs`

One or more audio files. Supported extensions: `.mp3`, `.wav`, `.flac`, `.m4a`, `.aac`. Glob patterns expand in your shell (`chapter*.mp3`), not inside the tool.

---

## Options

### `-o DIR`, `--out-dir DIR`

Write outputs to `DIR` as `<stem>_ACX.mp3`. Directory is created if it doesn't exist.

Default: write alongside each input file.

```sh
acx-rms-fix -o mastered/ chapter01.mp3 chapter02.mp3
# → mastered/chapter01_ACX.mp3
# → mastered/chapter02_ACX.mp3
```

### `-r`, `--replace`

Replace each input in place. The original is saved next to it as `<stem>.orig.<ext>` — **never** deleted. Safe to re-run: the backup is only created the first time.

```sh
acx-rms-fix --replace chapter01.mp3
# → chapter01.mp3      (mastered)
# → chapter01.orig.mp3 (original, preserved)
```

Mutually exclusive with `--out-dir`.

### `-c`, `--check`

Measure each input against the ACX spec and print PASS/FAIL. **No re-encoding.** Useful for verifying files mastered elsewhere, or for a CI gate.

```sh
acx-rms-fix --check chapter*.mp3
```

Exit code **0** if all inputs pass, **2** if any fail.

### `--report PATH`

Write a full report to `PATH`. Format is picked from the extension:

- `.md` or `.markdown` → human-readable Markdown table
- anything else → JSON

Both formats contain: per-file before/after RMS and peak, noise-floor status, pass/fail, error messages, platform info, and ffmpeg version.

```sh
acx-rms-fix -o out/ --report out/report.md chapter*.mp3
```

### `-q`, `--quiet`

Suppress per-file progress lines. Final summary and errors still print.

### `-V`, `--version`

Print version and exit.

### `-h`, `--help`

Print help and exit.

---

## Exit codes

| Code | Meaning                                         |
|------|--------------------------------------------------|
| **0** | All files processed successfully and pass ACX  |
| **1** | Usage error or `ffmpeg` not found on PATH      |
| **2** | One or more files failed the ACX verification  |

Safe to use as a gate in scripts:

```sh
acx-rms-fix --check chapters/*.mp3 || exit 1
```

---

## Examples

### Master a single chapter

```sh
acx-rms-fix chapter01.mp3
```

### Master every chapter in a folder

```sh
acx-rms-fix -o mastered/ chapters/*.mp3
```

### Master and overwrite in place, keeping backups

```sh
acx-rms-fix --replace chapters/*.mp3
```

### Verify a folder without re-encoding

```sh
acx-rms-fix --check chapters/*.mp3
```

### Full pipeline with report

```sh
acx-rms-fix -o mastered/ --report mastered/report.md chapters/*.mp3
```

### Use in a Makefile

```makefile
mastered/%.mp3: chapters/%.mp3
    acx-rms-fix -o mastered/ --quiet $<
    @mv mastered/$*_ACX.mp3 mastered/$*.mp3

verify: mastered/*.mp3
    acx-rms-fix --check $^
```

### Use in a GitHub Action

```yaml
- run: pipx install git+https://github.com/torkian/acx-rms-fix
- run: acx-rms-fix --check audiobook/*.mp3
```
