"""Windows Common Item Dialog helpers with no GUI toolkit dependency."""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import queue
import threading


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


def _pick_folder_sta(title: str, initial_dir: str) -> str:
    del initial_dir  # Windows remembers the last folder used by its common dialog.
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
        flags = 0x20 | 0x40 | 0x08  # PICKFOLDERS | FORCEFILESYSTEM | NOCHANGEDIR
        if set_options(dialog, options.value | flags) != 0:
            raise OSError("Unable to configure the Windows folder picker")

        if title:
            set_title = ctypes.WINFUNCTYPE(
                ctypes.HRESULT, ctypes.c_void_p, ctypes.wintypes.LPCWSTR
            )(table[17])
            set_title(dialog, title)

        show = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.wintypes.HWND
        )(table[3])
        if show(dialog, None) != 0:
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
        _release(dialog)
        ole32.CoUninitialize()


def pick_folder(title: str, initial_dir: str = "") -> str:
    """Show the native folder picker on its own Windows STA thread."""
    if os.name != "nt":
        raise OSError("The native folder picker is only available on Windows")
    result: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def run() -> None:
        try:
            result.put(("ok", _pick_folder_sta(title, initial_dir)))
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
