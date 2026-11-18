"""Set the Windows Shell identity of the workbench window."""
from __future__ import annotations

import ctypes
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

from backend.windows_dialog import GUID, _guid, _release


APP_USER_MODEL_ID = "DBAWorkbench.Desktop"


class _PropertyKey(ctypes.Structure):
    _fields_ = [("format_id", GUID), ("property_id", wintypes.DWORD)]


class _StringPropVariant(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ushort),
        ("reserved", ctypes.c_ushort * 3),
        ("text", wintypes.LPCWSTR),
        ("padding", ctypes.c_void_p),
    ]


def _relaunch_command(icon_path: Path) -> str:
    exe = Path(sys.executable)
    launcher = icon_path.parents[1] / "tools" / "windows" / "launch_dba_workbench.py"
    if launcher.is_file():
        pythonw = exe.with_name("pythonw.exe")
        return subprocess.list2cmdline([str(pythonw if pythonw.is_file() else exe), str(launcher)])
    return subprocess.list2cmdline([str(exe)])


def set_window_identity(hwnd: int, title: str, icon_path: Path) -> None:
    get_store = ctypes.windll.shell32.SHGetPropertyStoreForWindow
    get_store.argtypes = [wintypes.HWND, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    get_store.restype = ctypes.HRESULT
    store = ctypes.c_void_p()
    iid = _guid("{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}")  # IPropertyStore
    get_store(hwnd, ctypes.byref(iid), ctypes.byref(store))
    try:
        table = ctypes.cast(
            ctypes.cast(store, ctypes.POINTER(ctypes.c_void_p))[0],
            ctypes.POINTER(ctypes.c_void_p * 7),
        ).contents
        set_value = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(_PropertyKey), ctypes.POINTER(_StringPropVariant),
        )(table[6])
        app_model = _guid("{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}")
        # The Shell reads the relaunch metadata as soon as the AppUserModelID is set.
        for property_id, value in (
            (2, _relaunch_command(icon_path)),
            (3, f"{icon_path},0"),
            (4, title),
            (5, APP_USER_MODEL_ID),
        ):
            key = _PropertyKey(app_model, property_id)
            variant = _StringPropVariant(type=31, text=value)  # VT_LPWSTR
            set_value(store, ctypes.byref(key), ctypes.byref(variant))
    finally:
        _release(store)
