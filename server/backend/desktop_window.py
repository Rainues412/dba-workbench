"""Windows WebView2 window and activation from a desktop shortcut or tray."""
from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from pathlib import Path

from backend import windows_taskbar


def _window_property(port: int) -> str:
    return f"DBAWorkbench.DesktopWindow.{port}"


def _hide_title_bar(user32, hwnd: int):
    comctl32 = ctypes.windll.comctl32
    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
        wintypes.LPARAM, ctypes.c_size_t, ctypes.c_size_t,
    )
    comctl32.SetWindowSubclass.argtypes = [wintypes.HWND, callback_type, ctypes.c_size_t, ctypes.c_size_t]
    comctl32.RemoveWindowSubclass.argtypes = [wintypes.HWND, callback_type, ctypes.c_size_t]
    comctl32.DefSubclassProc.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    comctl32.DefSubclassProc.restype = ctypes.c_ssize_t
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.GetDpiForWindow.argtypes = [wintypes.HWND]
    user32.GetDpiForWindow.restype = wintypes.UINT
    user32.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]

    @callback_type
    def frame_proc(window_handle, message, wparam, lparam, subclass_id, _):
        if message == 0x0082:  # WM_NCDESTROY
            comctl32.RemoveWindowSubclass(window_handle, frame_proc, subclass_id)
        if message != 0x0083 or not lparam:  # WM_NCCALCSIZE
            return comctl32.DefSubclassProc(window_handle, message, wparam, lparam)

        client = ctypes.cast(lparam, ctypes.POINTER(wintypes.RECT)).contents
        top = client.top
        result = comctl32.DefSubclassProc(window_handle, message, wparam, lparam)
        if result == 0:
            # Keep the system's resizable frame and maximized work-area calculation.
            # A maximized window's top resize frame sits just outside the work area.
            if user32.IsZoomed(window_handle):
                dpi = user32.GetDpiForWindow(window_handle)
                top += user32.GetSystemMetricsForDpi(33, dpi) + user32.GetSystemMetricsForDpi(92, dpi)
            client.top = top
        return result

    if not comctl32.SetWindowSubclass(hwnd, frame_proc, 1, 0):
        logging.warning("无法为工作台替换系统标题栏。")
        return None
    user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0237)  # Refresh frame without moving or resizing.
    return frame_proc


def activate(port: int) -> bool:
    if sys.platform != "win32":
        return False

    user32 = ctypes.windll.user32
    user32.GetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    user32.GetPropW.restype = wintypes.HANDLE
    user32.SetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE]
    user32.SetPropW.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    prop = _window_property(port)
    found = False

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        nonlocal found
        if not user32.GetPropW(hwnd, prop):
            return True
        if user32.GetPropW(hwnd, "DBAWorkbench.WaitingForPaint"):
            # Ask the native host to show after rendering; recheck in case it just finished.
            if user32.SetPropW(hwnd, "DBAWorkbench.ShowAfterPaint", 1) and user32.GetPropW(hwnd, "DBAWorkbench.WaitingForPaint"):
                found = True
                return False
        # SW_RESTORE only for a minimized window, so a maximized window stays maximized.
        user32.ShowWindowAsync(hwnd, 9 if user32.IsIconic(hwnd) else 5)
        user32.SetForegroundWindow(hwnd)
        found = True
        return False

    user32.EnumWindows(visit, 0)
    return found


def create(title: str, port: int, icon_path: Path, is_exiting, should_close_to_tray=lambda: True, on_closed=lambda: None):
    if sys.platform != "win32":
        return None

    try:
        import webview
        from webview.platforms import winforms
        from System import Action
        from System.Drawing import Icon
    except Exception:
        logging.exception("WebView2 窗口组件无法加载，将使用浏览器打开。")
        return None
    if winforms.renderer != "edgechromium":
        logging.warning("未检测到 WebView2 Runtime，将使用浏览器打开。")
        return None

    webview.settings["ALLOW_DOWNLOADS"] = True
    window = webview.create_window(
        title,
        html="<!doctype html><title>DBA 工作台</title>",
        hidden=True,
        width=1320,
        height=820,
        min_size=(980, 640),
        easy_drag=False,
        text_select=True,
        zoomable=True,
    )

    # Keep the native callback alive for the lifetime of this window.
    native_frame = None

    def register_window():
        nonlocal native_frame
        form = window.native
        hwnd = form.Handle.ToInt64()
        user32 = ctypes.windll.user32
        user32.SetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE]
        if not user32.SetPropW(hwnd, _window_property(port), 1):
            logging.warning("无法注册桌面窗口，重复启动时将使用浏览器打开。")
        form.Icon = Icon(str(icon_path))
        try:
            windows_taskbar.set_window_identity(hwnd, title, icon_path)
        except OSError:
            logging.exception("无法设置工作台的任务栏标识。")

        native_frame = _hide_title_bar(user32, hwnd)

    def window_is_maximized() -> bool:
        return str(window.native.WindowState) == "Maximized"

    def toggle_window_size() -> bool:
        if window_is_maximized():
            window.restore()
            return False
        window.maximize()
        return True

    def start_window_drag() -> None:
        form = window.native
        user32 = ctypes.windll.user32
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = ctypes.c_ssize_t

        def begin_drag():
            position = wintypes.POINT()
            if user32.GetAsyncKeyState(1) & 0x8000 and user32.GetCursorPos(ctypes.byref(position)):
                coords = (position.x & 0xFFFF) | ((position.y & 0xFFFF) << 16)
                user32.ReleaseCapture()
                user32.SendMessageW(form.Handle.ToInt64(), 0x00A1, 2, coords)  # WM_NCLBUTTONDOWN, HTCAPTION

        form.BeginInvoke(Action(begin_drag))

    def close_to_tray():
        if is_exiting() or not should_close_to_tray():
            return True
        window.hide()
        # Release page memory (including unlocked vault keys) just as closing a tab does.
        window.native.browser.webview.Reload()
        return False

    window.events.before_show += register_window
    window.events.closing += close_to_tray
    window.events.closed += on_closed
    window.expose(window.minimize, window_is_maximized, toggle_window_size, start_window_drag, window.destroy)
    return window
