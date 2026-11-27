"""Small desktop conveniences for people running Sofia on their own computer.

keep_awake: stop the computer from idling to sleep while Sofia runs (closing a
laptop lid can still put it to sleep). Windows: SetThreadExecutionState.
macOS: `caffeinate` tied to this process.

disable_quick_edit: in the classic Windows console one stray mouse click puts
the window in "select" mode, which blocks all output — and with it Sofia —
until Esc is pressed. Turned off while the bot runs.
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


def disable_quick_edit() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.GetStdHandle.restype = wintypes.HANDLE
        handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = wintypes.DWORD()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            enable_quick_edit, enable_extended_flags = 0x0040, 0x0080
            kernel32.SetConsoleMode(handle, (mode.value & ~enable_quick_edit) | enable_extended_flags)
    except Exception:
        log.warning("could not disable QuickEdit", exc_info=True)
