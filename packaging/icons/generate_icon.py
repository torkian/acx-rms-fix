"""
Generate the acx-rms-fix application icon as platform-native bundles.

Design: deep-navy rounded square background with a centered vertical
level meter in gold — seven bars of varying height, the middle band
brighter, with a thin target line across the center. The meter
visually encodes what the tool does (raise RMS level into the ACX
window) and reads cleanly at sizes from 16 px up to 1024 px.

Outputs (relative to this file):
    src/icon_1024.png      master 1024 px PNG
    src/icon_{16..1024}.png individual sizes
    acx-rms-fix.iconset/   macOS iconset (used by iconutil)
    acx-rms-fix.icns       macOS bundle icon (via iconutil)
    acx-rms-fix.ico        Windows multi-resolution .ico
    acx-rms-fix.png        512 px PNG (repo logo, social preview)

Requires Pillow 10+. `iconutil` comes with macOS; if it's missing,
the .icns step is skipped with a warning.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
SRC_DIR = HERE / "src"
ICONSET_DIR = HERE / "acx-rms-fix.iconset"

# ---------------- design tokens ----------------

# Canvas we draw on, then downsample. Oversampling = cleaner anti-aliasing
# at every output size, especially below 64 px where integer rounding bites.
MASTER = 1024
SUPER = MASTER * 4  # 4096 — downsample by 4 for final 1024

BG_TOP = (12, 22, 40, 255)  # #0c1628 — deep navy
BG_BOTTOM = (25, 42, 74, 255)  # #192a4a — slightly lighter navy
CORNER_RATIO = 0.225  # macOS/iOS squircle-ish

BAR_COLOR_TOP = (255, 214, 102, 255)  # #ffd666 — warm gold
BAR_COLOR_BOTTOM = (255, 157, 72, 255)  # #ff9d48 — amber
TARGET_LINE = (255, 255, 255, 58)  # translucent white
SHADOW = (0, 0, 0, 90)

BAR_COUNT = 7
BAR_RELATIVE_HEIGHTS = [0.42, 0.66, 0.82, 1.00, 0.82, 0.66, 0.42]


def _vertical_gradient(size: tuple[int, int], top: tuple, bottom: tuple) -> Image.Image:
    """Simple top-to-bottom RGBA gradient."""
    w, h = size
    base = Image.new("RGBA", size, top)
    overlay = Image.new("RGBA", size, bottom)
    mask = Image.linear_gradient("L").resize(size)
    base.paste(overlay, (0, 0), mask)
    return base


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def _draw_level_meter(draw: ImageDraw.ImageDraw, size: int) -> None:
    """Centered vertical bar meter — the only glyph on the icon."""
    # Meter occupies the central 60% of the canvas width and 60% of the height.
    margin_x = int(size * 0.22)
    margin_y = int(size * 0.22)
    meter_w = size - margin_x * 2
    meter_h = size - margin_y * 2
    cx = size // 2
    cy = size // 2

    gap = int(meter_w / (BAR_COUNT * 3.4))  # ~1/4 of a bar width
    bar_w = (meter_w - gap * (BAR_COUNT - 1)) // BAR_COUNT
    radius = bar_w // 2

    # Bar x positions
    total_w = bar_w * BAR_COUNT + gap * (BAR_COUNT - 1)
    start_x = cx - total_w // 2

    # Draw each bar. Top color = gold, bottom color = amber — apply a
    # vertical gradient within each bar via a masked gradient fill.
    for i, rel_h in enumerate(BAR_RELATIVE_HEIGHTS):
        bar_h = int(meter_h * rel_h)
        x0 = start_x + i * (bar_w + gap)
        y0 = cy - bar_h // 2

        # Gradient fill: composite a pre-made gradient strip then mask to bar shape.
        strip = _vertical_gradient((bar_w, bar_h), BAR_COLOR_TOP, BAR_COLOR_BOTTOM)
        bar_mask = Image.new("L", (bar_w, bar_h), 0)
        ImageDraw.Draw(bar_mask).rounded_rectangle(
            (0, 0, bar_w - 1, bar_h - 1), radius=radius, fill=255
        )
        # Paste the gradient onto the parent image via the draw's image.
        draw._image.paste(strip, (x0, y0), bar_mask)

    # Thin horizontal target line across the whole meter width —
    # suggests "the level you should hit". Soft so it reads as a hint
    # rather than as a hard separator.
    line_top = cy - int(size * 0.006)
    line_bot = cy + int(size * 0.006)
    draw.rounded_rectangle(
        (margin_x, line_top, size - margin_x, line_bot),
        radius=int(size * 0.004),
        fill=TARGET_LINE,
    )


def render_master() -> Image.Image:
    """Render the 4x master canvas, then downsample to MASTER."""
    canvas = Image.new("RGBA", (SUPER, SUPER), (0, 0, 0, 0))

    # 1. Background: rounded-square navy gradient with a soft inner shadow.
    radius = int(SUPER * CORNER_RATIO)
    bg = _vertical_gradient((SUPER, SUPER), BG_TOP, BG_BOTTOM)
    mask = _rounded_mask(SUPER, radius)
    canvas.paste(bg, (0, 0), mask)

    # Subtle inset shadow to add depth — draw a slightly smaller rounded
    # rectangle in semi-transparent black, blur it, and composite.
    shadow_layer = Image.new("RGBA", (SUPER, SUPER), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow_layer)
    inset = int(SUPER * 0.012)
    sd.rounded_rectangle(
        (inset, inset, SUPER - inset, SUPER - inset),
        radius=radius - inset,
        outline=SHADOW,
        width=int(SUPER * 0.006),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=int(SUPER * 0.012)))
    canvas = Image.alpha_composite(canvas, shadow_layer)

    # 2. Level meter glyph.
    draw = ImageDraw.Draw(canvas)
    _draw_level_meter(draw, SUPER)

    # 3. Downsample to the master resolution with high-quality resampling.
    canvas = canvas.resize((MASTER, MASTER), Image.LANCZOS)
    return canvas


def export_pngs(master: Image.Image) -> dict[int, Path]:
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    out: dict[int, Path] = {}
    for s in sizes:
        img = master.resize((s, s), Image.LANCZOS) if s != MASTER else master
        p = SRC_DIR / f"icon_{s}.png"
        img.save(p, "PNG")
        out[s] = p
    return out


def export_iconset_and_icns(pngs: dict[int, Path]) -> None:
    if ICONSET_DIR.exists():
        shutil.rmtree(ICONSET_DIR)
    ICONSET_DIR.mkdir()
    # Apple iconutil naming: icon_16x16.png, icon_16x16@2x.png, ... up to 512@2x (=1024)
    mapping = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for size, name in mapping:
        shutil.copy(pngs[size], ICONSET_DIR / name)

    if shutil.which("iconutil"):
        icns_path = HERE / "acx-rms-fix.icns"
        subprocess.run(
            ["iconutil", "-c", "icns", str(ICONSET_DIR), "-o", str(icns_path)],
            check=True,
        )
        print(f"wrote {icns_path}")
    else:
        print("warning: iconutil not found; skipping .icns (macOS-only tool)")


def export_ico(pngs: dict[int, Path]) -> None:
    """
    Multi-resolution Windows .ico.

    Pillow's ICO writer takes a single base image and the `sizes` kwarg,
    then downsamples the base to each requested size and packs them all
    into one .ico. Pass the 256 px master so it has enough pixels to
    downsample cleanly to 16 / 24 / 32 / 48 / 64 / 128 / 256.
    """
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    base = Image.open(pngs[256]).convert("RGBA")
    ico_path = HERE / "acx-rms-fix.ico"
    base.save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in ico_sizes],
    )
    print(f"wrote {ico_path}")


def export_logo_png(master: Image.Image) -> None:
    logo = master.resize((512, 512), Image.LANCZOS)
    logo_path = HERE / "acx-rms-fix.png"
    logo.save(logo_path, "PNG")
    print(f"wrote {logo_path}")


def main() -> int:
    master = render_master()
    master.save(SRC_DIR / "icon_master_1024.png", "PNG")
    pngs = export_pngs(master)
    export_iconset_and_icns(pngs)
    export_ico(pngs)
    export_logo_png(master)
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
