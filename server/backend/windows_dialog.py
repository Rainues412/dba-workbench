"""Windows Common Item Dialog helpers with no GUI toolkit dependency."""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import queue
import threading
from collections.abc import Callable


_CANCELLED_HRESULT = 0x800704C7  # HRESULT_FROM_WIN32(ERROR_CANCELLED)


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(value: str) -> GUID:
    guid = GUID()
    function = ctypes.windll.ole32.CLSIDFromString
    function.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.POINTER(GUID)]
    function.restype = ctypes.HRESULT
    result = function(value, ctypes.byref(guid))
    if result != 0:
        raise OSError(f"Invalid COM GUID: 0x{result & 0xFFFFFFFF:08X}")
    return guid


def _release(pointer: ctypes.c_void_p) -> None:
    if not pointer:
        return
    table = ctypes.cast(
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))[0],
        ctypes.POINTER(ctypes.c_void_p * 3),
    ).contents
    ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[2])(pointer)


def _foreground_window() -> int:
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
    return int(user32.GetForegroundWindow() or 0)


def _show_dialog(dialog: ctypes.c_void_p, show_address: int, owner_hwnd: int) -> bool:
    # Read the raw HRESULT so ctypes does not turn cancellation into an exception.
    show = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.wintypes.HWND)(show_address)
    result = show(dialog, owner_hwnd or None)
    if (result & 0xFFFFFFFF) == _CANCELLED_HRESULT:
        return False
    if result != 0:
        raise ctypes.WinError(result)
    return True


class _Filter(ctypes.Structure):
    _fields_ = [("label", ctypes.wintypes.LPCWSTR), ("pattern", ctypes.wintypes.LPCWSTR)]


def _pick_folder_sta(title: str, initial_dir: str, owner_hwnd: int = 0) -> str:
    return _pick_item_sta(title, "", owner_hwnd)  # Let Windows remember the last directory.


def _pick_item_sta(title: str, initial_dir: str, owner_hwnd: int, pattern: str = "") -> str:
    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    ole32.CoInitializeEx.restype = ctypes.HRESULT
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(GUID), ctypes.c_void_p, ctypes.c_uint,
        ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.HRESULT
    initialized = ole32.CoInitializeEx(None, 2) in (0, 1)  # COINIT_APARTMENTTHREADED
    if not initialized:
        raise OSError("Unable to initialize the Windows folder picker")

    dialog = ctypes.c_void_p()
    result_item = ctypes.c_void_p()
    folder_item = ctypes.c_void_p()
    path_pointer = ctypes.wintypes.LPWSTR()
    try:
        clsid = _guid("{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}")
        iid_dialog = _guid("{D57C7288-D4AD-4768-BE02-9D969532D960}")
        result = ole32.CoCreateInstance(
            ctypes.byref(clsid), None, 1, ctypes.byref(iid_dialog), ctypes.byref(dialog)
        )
        if result != 0 or not dialog:
            raise OSError(f"Unable to create the Windows folder picker: 0x{result & 0xFFFFFFFF:08X}")

        table = ctypes.cast(
            ctypes.cast(dialog, ctypes.POINTER(ctypes.c_void_p))[0],
            ctypes.POINTER(ctypes.c_void_p * 27),
        ).contents
        get_options = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)
        )(table[10])
        set_options = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.c_uint
        )(table[9])
        options = ctypes.c_uint()
        if get_options(dialog, ctypes.byref(options)) != 0:
            raise OSError("Unable to read folder picker options")
        flags = 0x40 | 0x08 | (0x1000 | 0x800 if pattern else 0x20)  # FORCEFILESYSTEM | NOCHANGEDIR | FILEMUSTEXIST/PATHMUSTEXIST or PICKFOLDERS
        if set_options(dialog, options.value | flags) != 0:
            raise OSError("Unable to configure the Windows folder picker")

        if pattern:
            set_file_types = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(_Filter))(table[4])
            set_file_types(dialog, 1, ctypes.byref(_Filter(title, pattern)))
        if initial_dir:
            create_item = ctypes.windll.shell32.SHCreateItemFromParsingName
            create_item.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
            create_item.restype = ctypes.HRESULT
            shell_item = _guid("{43826D1E-E718-42EE-BC55-A1E261C37BFE}")
            if create_item(initial_dir, None, ctypes.byref(shell_item), ctypes.byref(folder_item)) == 0:
                set_folder = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.c_void_p)(table[12])
                set_folder(dialog, folder_item)

        if title:
            set_title = ctypes.WINFUNCTYPE(
                ctypes.HRESULT, ctypes.c_void_p, ctypes.wintypes.LPCWSTR
            )(table[17])
            set_title(dialog, title)

        if owner_hwnd:
            user32 = ctypes.windll.user32
            user32.SetForegroundWindow.argtypes = [ctypes.wintypes.HWND]
            user32.SetForegroundWindow.restype = ctypes.wintypes.BOOL
            user32.SetForegroundWindow(ctypes.wintypes.HWND(owner_hwnd))
        if not _show_dialog(dialog, table[3], owner_hwnd):
            return ""

        get_result = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
        )(table[20])
        if get_result(dialog, ctypes.byref(result_item)) != 0 or not result_item:
            return ""

        item_table = ctypes.cast(
            ctypes.cast(result_item, ctypes.POINTER(ctypes.c_void_p))[0],
            ctypes.POINTER(ctypes.c_void_p * 6),
        ).contents
        get_display_name = ctypes.WINFUNCTYPE(
            ctypes.HRESULT,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.wintypes.LPWSTR),
        )(item_table[5])
        if get_display_name(result_item, 0x80058000, ctypes.byref(path_pointer)) != 0:
            return ""
        return path_pointer.value or ""
    finally:
        if path_pointer:
            ole32.CoTaskMemFree(path_pointer)
        _release(result_item)
        _release(folder_item)
        _release(dialog)
        ole32.CoUninitialize()


def pick_folder(title: str, initial_dir: str = "") -> str:
    """Show the native folder picker on its own Windows STA thread."""
    return _show_on_sta(lambda owner: _pick_folder_sta(title, initial_dir, owner))


def pick_file(title: str, initial_dir: str, pattern: str) -> str:
    """Show the native file picker in the specified starting directory."""
    return _show_on_sta(lambda owner: _pick_item_sta(title, initial_dir, owner, pattern))


def _show_on_sta(pick: Callable[[int], str]) -> str:
    if os.name != "nt":
        raise OSError("The native folder picker is only available on Windows")
    result: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)
    owner_hwnd = _foreground_window()

    def run() -> None:
        try:
            result.put(("ok", pick(owner_hwnd)))
        except Exception as error:
            result.put(("error", error))

    thread = threading.Thread(target=run, name="folder-picker", daemon=True)
    thread.start()
    thread.join()
    status, value = result.get_nowait()
    if status == "error":
        if isinstance(value, BaseException):
            raise value
        raise OSError("The Windows folder picker failed")
    return str(value)
