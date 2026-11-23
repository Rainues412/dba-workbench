"""Managed encrypted backup files, scoped to a single vault owner."""

from __future__ import annotations

import hashlib
import base64
import ctypes
import filecmp
import json
import os
import re
import secrets
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from ctypes import wintypes
from pathlib import Path, PureWindowsPath
from threading import RLock
from unicodedata import normalize

from pyrage import IdentityError, encrypt, x25519

from backend import database
from backend.observability import logger

MAX_BACKUP_BYTES = 64 * 1024 * 1024
BACKUP_NAME = r"^(?:backup|auto|before-restore)-\d{8}-\d{6}-[0-9a-f]{12}(?:-legacy-\d+)?\.(?:age|json)$"
AGE_HEADER = b"-----BEGIN AGE ENCRYPTED FILE-----"
FILE_LOCK = RLock()
FORMAT = "dba-vault-backup-v3"


def backup_root() -> Path:
    data_dir = Path(database.DB_PATH).resolve().parent
    if data_dir == Path(__file__).resolve().parents[1]:
        return data_dir.parent / "backups"
    return data_dir / "backups"


def directory(user_id: int) -> Path:
    return backup_root() / str(user_id)


def _legacy_directory(user_id: int) -> Path:
    return Path(database.DB_PATH).resolve().parent / "vault-backups" / str(user_id)


def _safe_folder(folder: Path) -> bool:
    return folder.resolve() == folder


def _filename_allowed(filename: str) -> bool:
    if not filename or filename.endswith((" ", ".")) or re.search(r'[<>:"/\\|?*\x00-\x1f\x7f]', filename):
        return False
    path = PureWindowsPath(filename)
    return path.suffix.lower() in {".age", ".json"} and not path.is_reserved()


def _backup_file(path: Path) -> bool:
    if not _filename_allowed(path.name) or path.is_symlink() or not path.is_file():
        return False
    if re.fullmatch(BACKUP_NAME, path.name, re.IGNORECASE):
        return True
    try:
        with path.open("rb") as handle:
            if path.suffix.lower() == ".age":
                return handle.read(len(AGE_HEADER)) == AGE_HEADER
            data = handle.read(MAX_BACKUP_BYTES + 1)
        if len(data) > MAX_BACKUP_BYTES:
            return False
        document = json.loads(data)
        return isinstance(document, dict) and document.get("format") in {"dba-vault-backup-v1", "dba-vault-backup-v2"}
    except (FileNotFoundError, ValueError):
        return False


def _rename_without_replacing(source: Path, target: Path) -> None:
    if os.name == "nt":
        source.rename(target)
    else:
        os.link(source, target)
        try:
            source.unlink()
        except OSError:
            target.unlink()
            raise


def _copy_legacy_file(source: Path, destination: Path) -> None:
    temporary = None
    try:
        stat = source.stat()
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            with source.open("rb") as backup:
                shutil.copyfileobj(backup, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.utime(temporary, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        _rename_without_replacing(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare_directory(conn, user_id: int) -> None:
    """Copy prior releases' backups once, leaving the old directory intact."""
    if conn.execute("SELECT 1 FROM vault_backup_layout WHERE user_id=?", (user_id,)).fetchone():
        return
    folder = directory(user_id)
    legacy = _legacy_directory(user_id)
    if not _safe_folder(folder) or not _safe_folder(legacy):
        raise OSError("Backup directory must not redirect to another location")
    if legacy.is_dir():
        folder.mkdir(parents=True, exist_ok=True)
        for source in legacy.iterdir():
            if not re.fullmatch(BACKUP_NAME, source.name, re.IGNORECASE) or not _backup_file(source):
                continue
            target = folder / source.name
            suffix = 2
            while target.exists() or target.is_symlink():
                if not target.is_symlink() and target.is_file() and filecmp.cmp(source, target, shallow=False):
                    break
                target = folder / f"{source.stem}-legacy-{suffix}{source.suffix}"
                suffix += 1
            else:
                _copy_legacy_file(source, target)
    conn.execute("INSERT INTO vault_backup_layout(user_id) VALUES (?)", (user_id,))
    conn.commit()


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


def key_directory(user_id: int) -> Path:
    return Path(database.DB_PATH).resolve().parent / "vault-backup-keys" / str(user_id)


def portable_key_directory(user_id: int) -> Path:
    return key_directory(user_id) / "portable"


def _key_path(user_id: int, recipient: str) -> Path:
    name = hashlib.sha256(recipient.encode("ascii")).hexdigest()
    return key_directory(user_id) / (name + ".dpapi")


def read_identity(user_id: int, recipient: str) -> str:
    return _dpapi(_key_path(user_id, recipient).read_bytes(), False).decode("ascii")


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("descriptor", ctypes.c_void_p), ("inherit_handle", wintypes.BOOL)]


def _open_private_file(path: Path) -> int:
    import msvcrt

    kernel = ctypes.WinDLL("Kernel32", use_last_error=True)
    convert = ctypes.WinDLL("Advapi32", use_last_error=True).ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p)
    convert.restype = wintypes.BOOL
    kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_SecurityAttributes),
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel.LocalFree.restype = ctypes.c_void_p
    descriptor = ctypes.c_void_p()
    # Protect the file from inherited permissions on the backup drive.
    if not convert("D:P(A;;FA;;;OW)(A;;FA;;;SY)(A;;FA;;;BA)", 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        attributes = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), descriptor, False)
        generic_write, create_new, normal_file = 0x40000000, 1, 0x80
        handle = kernel.CreateFileW(str(path), generic_write, 0, ctypes.byref(attributes), create_new, normal_file, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            volume_info = kernel.GetVolumeInformationByHandleW
            volume_info.argtypes = (wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD)
            volume_info.restype = wintypes.BOOL
            flags = wintypes.DWORD()
            if not volume_info(handle, None, 0, None, None, ctypes.byref(flags), None, 0):
                raise ctypes.WinError(ctypes.get_last_error())
            if not flags.value & 0x8:  # FILE_PERSISTENT_ACLS
                raise OSError("Recovery key directory does not support Windows file permissions")
            return msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
        except BaseException:
            kernel.CloseHandle(handle)
            path.unlink(missing_ok=True)
            raise
    finally:
        kernel.LocalFree(descriptor)


def ensure_portable_key(user_id: int, recipient: str) -> None:
    folder = portable_key_directory(user_id)
    path = folder / (_key_path(user_id, recipient).stem + ".key")
    with FILE_LOCK:
        if not _safe_folder(folder) or path.is_symlink():
            raise OSError("Recovery key directory must not redirect to another location")
        if path.is_file():
            return
        if os.name != "nt":
            raise OSError("Windows file permissions are required for portable recovery keys")
        private_key = read_identity(user_id, recipient)
        try:
            actual_recipient = str(x25519.Identity.from_str(private_key).to_public())
        except IdentityError as exc:
            raise ValueError("Invalid local backup recovery key") from exc
        if actual_recipient != recipient:
            raise ValueError("Backup recovery key does not match the vault")
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / (secrets.token_hex(16) + ".tmp")
        descriptor = _open_private_file(temporary)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write((private_key + "\n").encode("ascii"))
                output.flush()
                os.fsync(output.fileno())
            temporary.rename(path)
        finally:
            temporary.unlink(missing_ok=True)


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


@contextmanager
def _staged_file(folder: Path, data: bytes):
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        yield temporary
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write(path: Path, data: bytes) -> None:
    with _staged_file(path.parent, data) as temporary:
        temporary.replace(path)


def save(user_id: int, data: bytes, *, conn=None, kind: str = "manual") -> str:
    if len(data) > MAX_BACKUP_BYTES:
        raise ValueError("备份文件不能超过 64 MiB。")
    timestamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
    folder = directory(user_id)
    if not _safe_folder(folder):
        raise OSError("Backup directory must not redirect to another location")
    with _staged_file(folder, data) as temporary:
        if conn is not None:
            _remember_kind(conn, user_id, temporary.stat(), kind)
        number = 1
        while True:
            name = timestamp if number == 1 else f"{timestamp} ({number})"
            path = folder / f"{name}.age"
            try:
                if not path.with_suffix(".json").exists():
                    _rename_without_replacing(temporary, path)
                    return path.name
            except FileExistsError:
                pass
            number += 1


def _file_id(stat: os.stat_result) -> str:
    return f"{stat.st_dev}:{stat.st_ino}:{getattr(stat, 'st_birthtime_ns', 0)}"


def _remember_kind(conn, user_id: int, stat: os.stat_result, kind: str) -> None:
    conn.execute("INSERT OR IGNORE INTO vault_backup_file_kinds(user_id, file_id, kind) VALUES (?, ?, ?)",
                 (user_id, _file_id(stat), kind))


def _kind(filename: str) -> str:
    if re.fullmatch(BACKUP_NAME, filename, re.IGNORECASE):
        if filename.lower().startswith("before-restore-"):
            return "safety"
        if filename.lower().startswith("auto-"):
            return "auto"
    return "manual"


def entries(conn, user_id: int) -> list[dict]:
    folder = directory(user_id)
    if not _safe_folder(folder):
        raise OSError("Backup directory must not redirect to another location")
    if not folder.is_dir():
        return []
    kinds = dict(conn.execute("SELECT file_id, kind FROM vault_backup_file_kinds WHERE user_id=?", (user_id,)))
    result = []
    for path in folder.iterdir():
        if not _backup_file(path):
            continue
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        result.append({
            "filename": path.name,
            "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "size": stat.st_size,
            "kind": kinds.get(_file_id(stat), _kind(path.name)),
        })
    return sorted(result, key=lambda entry: (entry["created_at"], entry["filename"]), reverse=True)


def prune(user_id: int, retention: int, previous: list[dict]) -> None:
    try:
        folder = directory(user_id)
        if not _safe_folder(folder):
            return
        older = [entry["filename"] for entry in previous if entry["kind"] == "auto" and entry["filename"].lower().endswith(".age")]
        for filename in older[retention - 1:]:
            path = folder / filename
            if not path.is_symlink():
                path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not complete vault backup retention")


def existing_path(user_id: int, filename: str) -> Path:
    if not _filename_allowed(filename):
        raise FileNotFoundError(filename)
    folder = directory(user_id)
    path = folder / filename
    if _safe_folder(folder) and _backup_file(path):
        return path
    raise FileNotFoundError(filename)


def rename(conn, user_id: int, filename: str, requested: str) -> str:
    source = existing_path(user_id, filename)
    name = normalize("NFC", requested.strip())
    if name.lower().endswith(source.suffix.lower()):
        name = name[:-len(source.suffix)]
    new_filename = name + source.suffix
    if not name or name.endswith((" ", ".")) or not _filename_allowed(new_filename):
        raise ValueError("请输入有效的 Windows 文件名，扩展名会自动保留。")
    if new_filename == source.name:
        return new_filename

    for sibling in source.parent.iterdir():
        candidate = normalize("NFC", sibling.stem).casefold()
        if sibling.name != source.name and sibling.suffix.lower() in {".age", ".json"} and candidate == name.casefold():
            raise FileExistsError(new_filename)

    # A file's identity survives renaming. Commit the type before moving the file
    # so it stays consistent even if the move fails or the process stops.
    stat = source.stat()
    _remember_kind(conn, user_id, stat, _kind(source.name))
    conn.commit()
    _rename_without_replacing(source, source.with_name(new_filename))
    return new_filename


def read(user_id: int, filename: str) -> bytes:
    with existing_path(user_id, filename).open("rb") as handle:
        content = handle.read(MAX_BACKUP_BYTES + 1)
    if len(content) > MAX_BACKUP_BYTES:
        raise ValueError("备份文件不能超过 64 MiB。")
    return content


def read_selected_file(path: Path, *, recovery_key: bool) -> str:
    path = path.resolve(strict=True)
    suffixes = {".txt", ".key"} if recovery_key else {".age", ".json"}
    if not re.fullmatch(r"[a-zA-Z]:", path.drive) or path.suffix.lower() not in suffixes or not path.is_file():
        raise ValueError("Unsupported backup selection")
    limit = 4096 if recovery_key else MAX_BACKUP_BYTES
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Backup selection exceeds its size limit")
    text = data.decode("utf-8-sig")
    if recovery_key:
        lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
        if len(lines) != 1:
            raise ValueError("Invalid recovery key file")
        try:
            x25519.Identity.from_str(lines[0])
        except IdentityError as exc:
            raise ValueError("Invalid recovery key file") from exc
    elif not text.startswith("-----BEGIN AGE ENCRYPTED FILE-----"):
        document = json.loads(text)
        if not isinstance(document, dict) or document.get("format") not in ("dba-vault-backup-v1", "dba-vault-backup-v2"):
            raise ValueError("Invalid backup file")
    return text
