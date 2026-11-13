"""Open a workbench window on Windows without inheriting a tiny browser window."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path


def find_edge() -> Path | None:
    configured = os.environ.get("DBA_EDGE_PATH", "").strip().strip('"')
    if configured:
        candidate = Path(configured)
        return candidate if candidate.is_file() else None
    discovered = shutil.which("msedge")
    if discovered:
        return Path(discovered)
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(variable)
        if base:
            candidate = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if candidate.is_file():
                return candidate
    return None


def _browser_windows() -> dict[int, str]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    windows = {}

    @callback
    def collect(hwnd, _):
        window_class = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(wintypes.HWND(hwnd), window_class, len(window_class))
        if window_class.value in ("Chrome_WidgetWin_1", "MozillaWindowClass"):
            title = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(wintypes.HWND(hwnd), title, len(title))
            windows[hwnd] = title.value
        return True

    user32.EnumWindows(collect, 0)
    return windows


def _maximize_new_workbench(existing: set[int]) -> None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        for hwnd, title in _browser_windows().items():
            if hwnd in existing or not (title == "DBA 工作台" or title.startswith("DBA 工作台 - ")):
                continue
            window = wintypes.HWND(hwnd)
            if user32.IsWindowVisible(window):
                if not user32.IsZoomed(window):
                    user32.ShowWindowAsync(window, 3)  # SW_MAXIMIZE
                return
        time.sleep(0.1)


def open_workbench(url: str, browser: Path | None) -> bool:
    windows = os.name == "nt"
    existing = set(_browser_windows()) if windows else set()
    if windows and browser and browser.is_file():
        subprocess.Popen(
            [str(browser), "--new-window", "--start-maximized", url],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        opened = True
    else:
        opened = webbrowser.open(url, new=1)
    if opened and windows:
        # Edge can forward the URL to a running process and ignore window flags.
        _maximize_new_workbench(existing)
    return opened
