"""Shared pytest fixtures."""

from __future__ import annotations

import shutil

import pytest

HAS_FFMPEG = shutil.which("ffmpeg") is not None

requires_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed on PATH")
