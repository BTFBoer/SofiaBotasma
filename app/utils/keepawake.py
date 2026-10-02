"""Stop the computer from going to sleep on its own while Sofia runs.

Only prevents *idle* sleep; closing a laptop lid can still put it to sleep.
Windows: SetThreadExecutionState. macOS: `caffeinate` tied to this process.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from app.utils.logging import get_logger

log = get_logger(__name__)


def keep_awake() -> None:
    try:
        if sys.platform == "win32":
            import ctypes

            es_continuous, es_system_required = 0x80000000, 0x00000001
            ctypes.windll.kernel32.SetThreadExecutionState(es_continuous | es_system_required)  # type: ignore[attr-defined]
            log.info("keeping the computer awake while Sofia runs")
        elif sys.platform == "darwin" and shutil.which("caffeinate"):
            subprocess.Popen(
                ["caffeinate", "-i", "-w", str(os.getpid())],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log.info("keeping the computer awake while Sofia runs")
    except Exception:
        log.warning("could not prevent sleep", exc_info=True)
