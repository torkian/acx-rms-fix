# PyInstaller spec for the bundled acx-rms-fix GUI.
#
# Build with:
#
#     cd packaging
#     ./fetch-ffmpeg.sh                        # downloads vendor/ffmpeg[.exe]
#     pyinstaller acx_rms_fix.spec             # produces dist/acx-rms-fix-gui[.exe | .app]
#
# The spec bundles the vendored ffmpeg binary as a binary resource.
# At runtime, `core._resolve_ffmpeg()` looks for it next to the frozen
# executable (sys._MEIPASS) before falling back to the PATH.
#
# Single entry point: src/acx_rms_fix/__main__.py — which calls into
# cli.main by default, but PyInstaller overrides that below so the
# frozen bundle launches the GUI instead.

import os
import sys
from pathlib import Path

# PyInstaller executes the spec with `SPEC` set to the spec file path
# and `workpath` / `distpath` configured, so we can use plain __file__.
SPEC_DIR = Path(os.path.abspath(SPEC)).parent
PROJECT_ROOT = SPEC_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"
VENDOR_DIR = SPEC_DIR / "vendor"

is_windows = sys.platform.startswith("win")
is_macos = sys.platform == "darwin"
ffmpeg_name = "ffmpeg.exe" if is_windows else "ffmpeg"
ffmpeg_path = VENDOR_DIR / ffmpeg_name

if not ffmpeg_path.is_file():
    raise SystemExit(
        f"vendored ffmpeg not found at {ffmpeg_path}\n"
        "run `packaging/fetch-ffmpeg.sh` first"
    )

# Platform-native icons produced by packaging/icons/generate_icon.py.
# Missing icons are not fatal — the build falls back to PyInstaller's
# default so CI keeps working even if someone forgets to regenerate.
ICON_DIR = SPEC_DIR / "icons"
if is_windows:
    icon_candidate = ICON_DIR / "acx-rms-fix.ico"
elif is_macos:
    icon_candidate = ICON_DIR / "acx-rms-fix.icns"
else:
    icon_candidate = ICON_DIR / "acx-rms-fix.png"
icon_arg = str(icon_candidate) if icon_candidate.is_file() else None

# Entry point: a one-line shim that calls gui.main, written next to
# the spec so we don't pollute src/ with a second __main__.
GUI_ENTRY = SPEC_DIR / "_gui_entry.py"
GUI_ENTRY.write_text(
    "from acx_rms_fix.gui import main\n"
    "import sys\n"
    "sys.exit(main())\n",
    encoding="utf-8",
)

block_cipher = None

# Package resources (window icon PNG used by gui.py iconphoto).
resources_dir = SRC_DIR / "acx_rms_fix" / "resources"
datas: list[tuple[str, str]] = []
if resources_dir.is_dir():
    for res in sorted(resources_dir.glob("*.png")):
        datas.append((str(res), "acx_rms_fix/resources"))

a = Analysis(
    [str(GUI_ENTRY)],
    pathex=[str(SRC_DIR)],
    binaries=[(str(ffmpeg_path), ".")],
    datas=datas,
    hiddenimports=[
        "acx_rms_fix",
        "acx_rms_fix.core",
        "acx_rms_fix.report",
        "acx_rms_fix.gui",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="acx-rms-fix-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # GUI app — hide the console window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_arg,
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="acx-rms-fix-gui.app",
        icon=icon_arg,
        bundle_identifier="net.torkian.acx-rms-fix",
        info_plist={
            "CFBundleName": "acx-rms-fix",
            "CFBundleDisplayName": "acx-rms-fix",
            "CFBundleShortVersionString": "0.1.3",
            "CFBundleVersion": "0.1.3",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
