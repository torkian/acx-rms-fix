# The ACX spec, explained

ACX enforces a small, specific set of audio requirements on every audiobook upload. This page explains *why* each one exists and what `acx-rms-fix` does about it — so when the tool fails you have enough context to debug it, and so narrators who want to understand their own audio have a plain-English reference.

The authoritative source is the [ACX audio submission requirements page](https://help.acx.com/s/article/what-are-acx-s-audio-submission-requirements). This document restates those rules and adds the engineering rationale that ACX's own docs don't go into.

---

## The three loudness rules (the ones that reject most files)

### RMS: -23 to -18 dBFS

**What it is.** RMS is the average power of the audio file, measured in dBFS (decibels below full scale — `0 dBFS` is the loudest a digital file can physically be). ACX insists every chapter's integrated RMS land between -23 and -18 dB.

**Why ACX cares.** Audiobooks are usually consumed in long sessions (commute, chores, bed), often on cheap playback devices (phone speaker, car stereo with road noise). Chapter-to-chapter inconsistency is awful — listeners reach for the volume dial every chapter. Pegging every file at roughly the same average level means your listener sets the volume once and never touches it.

**The window, not a point.** Why -23 to -18 and not "exactly -20"? Because real speech has short-term variation — loud laughs, quiet confessions — that legitimately moves the long-term RMS a bit. The 5-dB window gives room for that variation without flagging files that are fine.

**What `acx-rms-fix` does.** The `loudnorm` filter (EBU R128 standard, used by the BBC and most broadcasters) computes the integrated loudness in *LUFS* — Loudness Units relative to Full Scale — and applies gain to hit a target of **-20 LUFS**, which sits almost exactly in the middle of ACX's RMS window. (LUFS and dB RMS are not mathematically identical, but for voice content they correlate within ~1 dB, which is why -20 LUFS consistently produces -20 dB RMS readings in ACX's checker.)

Two-pass mode is key: pass 1 measures the actual loudness of your file, pass 2 uses those measurements to hit the target deterministically. One-pass `loudnorm` estimates, two-pass measures. We use two-pass.

### Peak: ≤ -3 dBFS

**What it is.** The loudest single sample (or more precisely, the loudest reconstructed sample after the digital-to-analog converter in the listener's phone does its thing) must sit at or below -3 dBFS.

**Why ACX cares.** **Inter-sample peaks.** When an MP3 decoder reconstructs the waveform, the peaks between sample points can be higher than any individual sample. A signal whose sample-level peak reads -0.1 dB in a meter can reconstruct to +1.0 dB or higher on playback — which clips, audibly. The -3 dB ceiling gives enough headroom that even badly-behaved decoders on cheap DACs won't clip.

ACX's automated checker now specifically tests for this with a true-peak algorithm. A simple sample-peak measurement will let files through that ACX will then reject.

**What `acx-rms-fix` does.** Two things, belt-and-braces:

1. `loudnorm` is told `TP=-3.2` — it aims for a true-peak ceiling 0.2 dB below ACX's rule.
2. After `loudnorm`, a dedicated `alimiter` brick-walls anything that sneaks through at **0.708 linear amplitude**, which is exactly `10^(-3/20)` ≈ -3 dBFS.

If the input already has legitimate peaks under -3 dB, the limiter does nothing and you get back whatever `loudnorm` produced. If a resampling artefact or MP3 encoding quirk introduces a peak above -3 dB, the limiter catches it.

Why not rely on `loudnorm` alone? Because `loudnorm` is designed for broadcast, not for MP3 encoding, and the encoder downstream can introduce small peak lifts that `loudnorm` didn't see. The limiter is a cheap insurance policy.

### Noise floor: ≤ -60 dBFS

**What it is.** During silent passages — between words, between sentences, between chapters — the measured level must be below -60 dBFS. This is "digital whisper-quiet": barely above the file's mathematical floor.

**Why ACX cares.** **Consistency with the listening environment.** Headphones and decent speakers reveal background noise the narrator can't hear on their monitoring setup: fridge compressors, HVAC, computer fans, electrical hum, street traffic, even breath between takes. -60 dB is the threshold below which human hearing reliably does not notice any of it in a normal living room. Anything above -60 dB becomes *"the narrator was recording in a noisy room"* to the listener, which breaks immersion.

**What `acx-rms-fix` does.** Three layered defenses:

1. **`afftdn`** — fast Fourier transform denoise. Estimates the spectrum of the background noise and subtracts it from the whole file. More musical than a noise gate — no pumping or breathing artefacts on word tails.
2. **`highpass=80`** — removes rumble, room resonance, plosive thump, HVAC low-frequency hum, building vibration. Nothing useful in the human voice lives below 80 Hz; everything that does is a problem.
3. **`lowpass=16000`** — removes hiss, computer-fan whine, and high-frequency MP3 pre-echo without touching voice clarity.

`acx-rms-fix` uses moderate denoise settings (`nr=12` dB) so voice stays natural on clean sources. If your source has structural noise the chain can't handle — loud HVAC, a fan, a dimmer-switch buzz — the right fix is to re-record in a quieter room, or use a dedicated denoiser upstream ([rnnoise](https://github.com/xiph/rnnoise), iZotope RX, Adobe Audition). `acx-rms-fix` is a mastering tool, not a noise-removal miracle worker.

---

## The format rules (the ones that reject files you already mastered elsewhere)

### 44.1 kHz sample rate

Legacy — it's the Red Book CD standard. 48 kHz is more common in video but ACX sticks with 44.1 for historical consistency. `acx-rms-fix` forces the output with `aresample=44100` regardless of input.

### Mono

Audiobooks are voice — there's nothing to pan, so ACX dictates mono. Saves bandwidth, avoids stereo-phase issues on playback. `acx-rms-fix` forces `-ac 1`.

### MP3, 192 kbps, **CBR**

ACX specifically requires **constant bit rate** MP3. VBR files will be rejected even if they're high-quality, because the ACX infrastructure is tuned around predictable file sizes and time-index alignment. 192 kbps is the required rate. `acx-rms-fix` uses `libmp3lame -b:a 192k`, which produces CBR by default.

### Head silence 0.5 – 1.0 s, tail silence 1 – 5 s

Each chapter must start with a brief pause and end with a longer one. This lets ACX's players stitch chapters together smoothly and gives the listener auditory breathing room between chapters.

**`acx-rms-fix` does not currently handle this.** It preserves whatever head/tail silence your source file already has, and ACX's checker is lenient about it (the main thing ACX cares about is that files *don't* run all the way to the sample boundary). If you're getting flagged on silence, trim or extend in your audio editor before running the tool. A future version may add `--head 0.75 --tail 2.0`.

---

## Metrics vs rules

A subtlety: `acx-rms-fix` measures the output file with ffmpeg's `volumedetect` (RMS, peak) and `silencedetect` (noise floor). ACX uses its own (private) implementation. Measurements between the two usually agree within a few tenths of a dB for voice content. If `acx-rms-fix` says PASS but ACX says FAIL, the gap is almost always that you uploaded the wrong file — double-check the filename in ACX's error dialog. If both agree the file fails, see [Troubleshooting](troubleshooting.md).

---

## Further reading

- [ACX audio submission requirements (official)](https://help.acx.com/s/article/what-are-acx-s-audio-submission-requirements)
- [ffmpeg `loudnorm` filter docs](https://ffmpeg.org/ffmpeg-filters.html#loudnorm)
- [EBU R 128 loudness standard](https://tech.ebu.ch/publications/r128)
- [ITU-R BS.1770 loudness algorithm](https://www.itu.int/rec/R-REC-BS.1770)
