"""Managed encrypted backup files, scoped to a single vault owner."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from backend import database
from backend.observability import logger

MAX_BACKUP_BYTES = 64 * 1024 * 1024
BACKUP_NAME = r"^(?:backup|auto|before-restore)-\d{8}-\d{6}-[0-9a-f]{12}\.json$"
FILE_LOCK = RLock()


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


def portable_settings(conn, user_id: int, recovery_envelope: str):
    return conn.execute(
        """SELECT portable_seal, signing_key FROM vault_backup_settings
           WHERE user_id = ? AND vault_identity = ? AND portable_seal IS NOT NULL AND signing_key IS NOT NULL""",
        (user_id, identity(recovery_envelope)),
    ).fetchone()


def portable_document(user_id: int, items: list[dict], seal: dict, signing_key: bytes) -> dict:
    document = {"format": "dba-vault-backup-v2", "source_user_id": user_id, **seal, "items": items}
    return {**document, "mac": hmac.digest(signing_key, canonical(document), "sha256").hex()}


def save(user_id: int, document: dict, *, prefix: str = "backup") -> str:
    folder = directory(user_id)
    encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_BACKUP_BYTES:
        raise ValueError("备份文件不能超过 64 MiB。")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"{prefix}-{timestamp}-{secrets.token_hex(6)}.json"
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(folder / filename)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
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


def prune(user_id: int, retention: int, *protected: str | None) -> None:
    """Keep newest files and reserve a slot for each file involved in a restore."""
    try:
        backups = entries(user_id)
        kept = {entry["filename"] for entry in backups if entry["filename"] in protected}
        for entry in backups:
            filename = entry["filename"]
            if filename in kept:
                continue
            if len(kept) < retention:
                kept.add(filename)
            else:
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
