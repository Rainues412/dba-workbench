"""Managed encrypted backup files, scoped to a single vault owner."""

from __future__ import annotations

import hashlib
import base64
import ctypes
import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timezone
from ctypes import wintypes
from pathlib import Path
from threading import RLock

from pyrage import encrypt, x25519

from backend import database
from backend.observability import logger

MAX_BACKUP_BYTES = 64 * 1024 * 1024
BACKUP_NAME = r"^(?:backup|auto|before-restore)-\d{8}-\d{6}-[0-9a-f]{12}\.(?:age|json)$"
FILE_LOCK = RLock()
FORMAT = "dba-vault-backup-v3"


def directory(user_id: int) -> Path:
    return Path(database.DB_PATH).resolve().parent / "vault-backups" / str(user_id)


def settings(conn, user_id: int) -> dict:
    row = conn.execute(
        "SELECT interval_hours, retention FROM vault_backup_settings WHERE user_id = ?", (user_id,),
    ).fetchone()
    return dict(row) if row else {"interval_hours": 24, "retention": 10}


def canonical(document: dict) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def identity(recovery_envelope: str) -> str:
    return hashlib.sha256(recovery_envelope.encode("utf-8")).hexdigest()


def backup_key(conn, user_id: int, recovery_envelope: str):
    return conn.execute(
        """SELECT recipient, wrapped_dek, exported FROM vault_backup_keys
           WHERE user_id = ? AND vault_identity = ?""",
        (user_id, identity(recovery_envelope)),
    ).fetchone()


class _DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    if os.name != "nt":
        raise OSError("Windows DPAPI unavailable")
    dll = ctypes.WinDLL("Crypt32", use_last_error=True)
    apply = dll.CryptProtectData if protect else dll.CryptUnprotectData
    apply.argtypes = [ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                      ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    apply.restype = wintypes.BOOL
    free = ctypes.WinDLL("Kernel32").LocalFree
    free.argtypes = [ctypes.c_void_p]
    free.restype = ctypes.c_void_p
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = _DataBlob(len(data), buffer)
    output = _DataBlob()
    try:
        if not apply(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
            raise ctypes.WinError(ctypes.get_last_error())
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.memset(buffer, 0, len(data))
        if output.data:
            ctypes.memset(output.data, 0, output.size)
            free(output.data)


def _key_path(user_id: int, recipient: str) -> Path:
    name = hashlib.sha256(recipient.encode("ascii")).hexdigest()
    return directory(user_id).parent.parent / "vault-backup-keys" / str(user_id) / (name + ".dpapi")


def read_identity(user_id: int, recipient: str) -> str:
    return _dpapi(_key_path(user_id, recipient).read_bytes(), False).decode("ascii")


def prepare_key(conn, user_id: int, recovery_envelope: str, dek: bytes) -> None:
    if backup_key(conn, user_id, recovery_envelope):
        return
    private_key = x25519.Identity.generate()
    public_key = private_key.to_public()
    recipient = str(public_key)
    wrapped_dek = base64.urlsafe_b64encode(encrypt(dek, [public_key])).decode("ascii").rstrip("=")
    _write(_key_path(user_id, recipient), _dpapi(str(private_key).encode("ascii"), True))
    conn.execute(
        """INSERT INTO vault_backup_keys(user_id, vault_identity, recipient, wrapped_dek) VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET vault_identity=excluded.vault_identity, recipient=excluded.recipient,
           wrapped_dek=excluded.wrapped_dek, exported=0""",
        (user_id, identity(recovery_envelope), recipient, wrapped_dek),
    )
    conn.execute("UPDATE vault_backup_settings SET portable_seal=NULL, signing_key=NULL, vault_identity=NULL WHERE user_id=?", (user_id,))


def encrypted_snapshot(user_id: int, items: list[dict], key) -> bytes:
    document = {"format": FORMAT, "source_user_id": user_id, "wrapped_dek": key["wrapped_dek"], "items": items}
    return encrypt(canonical(document), [x25519.Recipient.from_str(key["recipient"])], armored=True)


def _write(path: Path, data: bytes) -> None:
    folder = path.parent
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save(user_id: int, data: bytes, *, prefix: str = "backup") -> str:
    if len(data) > MAX_BACKUP_BYTES:
        raise ValueError("备份文件不能超过 64 MiB。")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"{prefix}-{timestamp}-{secrets.token_hex(6)}.age"
    _write(directory(user_id) / filename, data)
    return filename


def entries(user_id: int) -> list[dict]:
    folder = directory(user_id)
    if not folder.is_dir():
        return []
    result = []
    for path in folder.iterdir():
        if not re.fullmatch(BACKUP_NAME, path.name) or path.is_symlink() or not path.is_file():
            continue
        stat = path.stat()
        result.append({
            "filename": path.name,
            "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "size": stat.st_size,
            "kind": "safety" if path.name.startswith("before-restore-") else "auto" if path.name.startswith("auto-") else "manual",
        })
    return sorted(result, key=lambda entry: entry["created_at"], reverse=True)


def prune(user_id: int, retention: int, newest: str) -> None:
    try:
        older = [entry["filename"] for entry in entries(user_id)
                 if entry["kind"] == "auto" and entry["filename"].endswith(".age") and entry["filename"] != newest]
        for filename in older[retention - 1:]:
            (directory(user_id) / filename).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not complete vault backup retention")


def read(user_id: int, filename: str) -> bytes:
    if not re.fullmatch(BACKUP_NAME, filename):
        raise FileNotFoundError(filename)
    path = directory(user_id) / filename
    if path.is_symlink():
        raise FileNotFoundError(filename)
    with path.open("rb") as handle:
        content = handle.read(MAX_BACKUP_BYTES + 1)
    if len(content) > MAX_BACKUP_BYTES:
        raise ValueError("备份文件不能超过 64 MiB。")
    return content
