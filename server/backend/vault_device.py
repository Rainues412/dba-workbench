"""Per-Windows-user storage for the optional desktop vault start-up key."""
from __future__ import annotations

import ctypes
import hashlib
import os
from ctypes import wintypes

from backend import database


class Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(wintypes.BYTE)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


GENERIC = 1
LOCAL_MACHINE = 2
NOT_FOUND = 1168


def _target(user_id: int) -> str:
    path = os.path.normcase(os.path.realpath(database.DB_PATH))
    return "DBA Workbench vault/" + hashlib.sha256(f"{path}:{user_id}".encode()).hexdigest()


def available() -> bool:
    return os.name == "nt"


def _wincred():
    if not available():
        raise OSError("Windows Credential Manager is unavailable")
    library = ctypes.WinDLL("Advapi32", use_last_error=True)
    pointer = ctypes.POINTER(Credential)
    library.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(pointer)]
    library.CredWriteW.argtypes = [pointer, wintypes.DWORD]
    library.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    library.CredFree.argtypes = [ctypes.c_void_p]
    library.CredFree.restype = None
    return library


def read_key(user_id: int, envelope: str) -> bytes | None:
    target_fingerprint = hashlib.sha256(envelope.encode()).digest()
    library = _wincred()
    result = ctypes.POINTER(Credential)()
    if not library.CredReadW(_target(user_id), GENERIC, 0, ctypes.byref(result)):
        if ctypes.get_last_error() == NOT_FOUND:
            return None
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        credential = result.contents
        if credential.CredentialBlobSize != 64:
            return None
        data = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        return data[32:] if data[:32] == target_fingerprint else None
    finally:
        library.CredFree(result)


def save_key(user_id: int, envelope: str, key: bytes) -> None:
    data = hashlib.sha256(envelope.encode()).digest() + key
    blob = (wintypes.BYTE * len(data)).from_buffer_copy(data)
    credential = Credential(
        Type=GENERIC, TargetName=_target(user_id), UserName="DBA Workbench",
        CredentialBlobSize=len(data), CredentialBlob=blob, Persist=LOCAL_MACHINE,
    )
    if not _wincred().CredWriteW(ctypes.byref(credential), 0):
        raise ctypes.WinError(ctypes.get_last_error())


def delete_key(user_id: int) -> None:
    if not _wincred().CredDeleteW(_target(user_id), GENERIC, 0):
        if ctypes.get_last_error() != NOT_FOUND:
            raise ctypes.WinError(ctypes.get_last_error())
