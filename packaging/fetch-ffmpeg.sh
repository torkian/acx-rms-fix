#!/usr/bin/env bash
#
# fetch-ffmpeg.sh — download a statically-built ffmpeg binary into
# packaging/vendor/ so PyInstaller can bundle it with the frozen app.
#
# Runs on macOS, Linux, and MSYS2 / Git-Bash on Windows. Detects the
# host OS + architecture and picks the right source:
#
#   macOS  arm64  -> https://www.osxexperts.net/ffmpeg81arm.zip       (static, arm64)
#   macOS  x86_64 -> https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip  (static, x86_64)
#   Linux  x86_64 -> BtbN FFmpeg-Builds linux64 lgpl                   (static, x86_64)
#   Windows x64  -> BtbN FFmpeg-Builds win64 lgpl                      (static, x86_64)
#
# The result is always packaging/vendor/ffmpeg (or ffmpeg.exe on
# Windows). PyInstaller's spec file copies this single file into the
# frozen bundle — no dylib chasing, no user-installed dependencies.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENDOR_DIR="${SCRIPT_DIR}/vendor"
mkdir -p "${VENDOR_DIR}"

OS_NAME="$(uname -s)"
ARCH_NAME="$(uname -m)"

case "${OS_NAME}" in
    Darwin)
        OS="macos"
        case "${ARCH_NAME}" in
            arm64)  ARCH="arm64"  ;;
            x86_64) ARCH="x86_64" ;;
            *) echo "unsupported macOS arch: ${ARCH_NAME}" >&2; exit 1 ;;
        esac
        ;;
    Linux)
        OS="linux"
        ARCH="x86_64"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        OS="windows"
        ARCH="x86_64"
        ;;
    *)
        echo "unsupported OS: ${OS_NAME}" >&2
        exit 1
        ;;
esac

OUT_NAME="ffmpeg"
[[ "${OS}" == "windows" ]] && OUT_NAME="ffmpeg.exe"
OUT="${VENDOR_DIR}/${OUT_NAME}"

if [[ -f "${OUT}" ]]; then
    echo "already fetched: ${OUT}"
    exit 0
fi

WORK="$(mktemp -d -t acxrmsfix-ffmpeg.XXXXXX)"
trap 'rm -rf "${WORK}"' EXIT

fetch_macos_arm64() {
    local url="https://www.osxexperts.net/ffmpeg81arm.zip"
    echo "fetching ${url}"
    curl -sSL -o "${WORK}/ffmpeg.zip" "${url}"
    unzip -q "${WORK}/ffmpeg.zip" -d "${WORK}"
    install -m 0755 "${WORK}/ffmpeg" "${OUT}"
}

fetch_macos_x86_64() {
    local url="https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip"
    echo "fetching ${url}"
    curl -sSL -o "${WORK}/ffmpeg.zip" "${url}"
    unzip -q "${WORK}/ffmpeg.zip" -d "${WORK}"
    install -m 0755 "${WORK}/ffmpeg" "${OUT}"
}

fetch_linux_x86_64() {
    local url="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-lgpl.tar.xz"
    echo "fetching ${url}"
    curl -sSL -o "${WORK}/ffmpeg.tar.xz" "${url}"
    tar -xJf "${WORK}/ffmpeg.tar.xz" -C "${WORK}"
    local inner
    inner="$(find "${WORK}" -type f -name 'ffmpeg' -perm -u+x | head -1)"
    install -m 0755 "${inner}" "${OUT}"
}

fetch_windows_x86_64() {
    local url="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-lgpl.zip"
    echo "fetching ${url}"
    curl -sSL -o "${WORK}/ffmpeg.zip" "${url}"
    unzip -q "${WORK}/ffmpeg.zip" -d "${WORK}"
    local inner
    inner="$(find "${WORK}" -type f -name 'ffmpeg.exe' | head -1)"
    cp "${inner}" "${OUT}"
}

case "${OS}-${ARCH}" in
    macos-arm64)   fetch_macos_arm64 ;;
    macos-x86_64)  fetch_macos_x86_64 ;;
    linux-x86_64)  fetch_linux_x86_64 ;;
    windows-x86_64) fetch_windows_x86_64 ;;
    *) echo "no fetch recipe for ${OS}-${ARCH}" >&2; exit 1 ;;
esac

if [[ ! -s "${OUT}" ]]; then
    echo "fetch produced an empty file: ${OUT}" >&2
    exit 1
fi

echo "ok: ${OUT}"
"${OUT}" -version 2>&1 | head -1
