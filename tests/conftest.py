from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List

import pytest

REPO = Path(__file__).resolve().parent.parent

# Sample summary from docs/blue-raven-usb-guide.md, section 10.1 (trimmed).
SUMMARY_LINES = [
    "@ SUMMARY 706",
    "Rocket: Adrian's BRav",
    "Build: 02/14/2023 11:19:58000",
    "Launch: 02/14/2023 11:23:31920",
    "landing time: 11:24:14680",
    "apogee h_vel: 22",
    "pad_ASL: 6806",
    "max alt: 897 max vel: 228 CRC: 6FA7",
]

needs_pty = pytest.mark.skipif(
    sys.platform == "win32", reason="pseudo-terminals are POSIX only"
)


def run_cli(args: List[str], timeout: float) -> subprocess.CompletedProcess:
    """Run `braven` in a child process so a hang is caught by `timeout`.

    A hang raises `subprocess.TimeoutExpired`, which fails the test instead
    of stalling the suite.
    """
    return subprocess.run(
        [sys.executable, "-m", "braven.cli", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
