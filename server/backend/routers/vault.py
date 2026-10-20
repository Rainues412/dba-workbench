"""Ciphertext-only vault API with one-time legacy migration support."""
from __future__ import annotations

import hashlib
import base64
import json
import secrets
import sqlite3
import string
import threading
import time
from pathlib import Path
from typing import Annotated

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend import database
from backend.auth import (
    MIN_PASSWORD_LENGTH,
    attempt_identifier,
    clear_attempts,
    record_failed_attempt,
    require_recent_reauth,
    retry_after,
    verify_password,
)
from backend.database import get_db_ctx, page_response, validate_page
from backend.vault_recovery import public_key_payload


router = APIRouter()
ENCODED = Annotated[str, Field(min_length=16, max_length=131072)]
ITEM_KEY = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{16,80}$")]
CAPTCHA_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CAPTCHA_TTL_SECONDS = 180
_captcha_lock = threading.Lock()
_captchas: dict[str, tuple[int, float, str]] = {}


class VaultProfileCreate(BaseModel):
    envelope_version: int = 1
    kdf_name: str = "argon2id"
    kdf_salt: ENCODED
    kdf_memory_kib: int = 65536
    kdf_iterations: int = 3
    kdf_parallelism: int = 1
    wrapped_dek: ENCODED
    wrapped_dek_nonce: ENCODED
    recovery_wrapped_dek: ENCODED
    recovery_key_id: Annotated[str, Field(min_length=8, max_length=128)]


class VaultProfileRewrap(BaseModel):
    kdf_salt: ENCODED
    kdf_memory_kib: int = 65536
    kdf_iterations: int = 3
    kdf_parallelism: int = 1
    wrapped_dek: ENCODED
    wrapped_dek_nonce: ENCODED
    login_password: Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)]
    captcha_id: Annotated[str, Field(min_length=32, max_length=64)]
    captcha_code: Annotated[str, Field(min_length=5, max_length=5)]


class VaultItemWrite(BaseModel):
    item_key: ITEM_KEY
    envelope_version: int = 1
    ciphertext: ENCODED
    nonce: ENCODED
    aad: Annotated[str, Field(min_length=8, max_length=512)]
    revision: int | None = None


class LegacyComplete(BaseModel):
    expected_source_count: int = Field(ge=0)


class BackupRestore(BaseModel):
    confirm: str
    digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    profile: dict
    items: list[dict]


def _user(request: Request) -> int:
    return int(request.state.session["user_id"])


def _captcha_image(code: str) -> str:
    letters = "".join(
        f'<text x="{18 + index * 28}" y="38" transform="rotate({(-7, 5, -4, 7, -5)[index]} {18 + index * 28} 38)">{character}</text>'
        for index, character in enumerate(code)
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="164" height="52" viewBox="0 0 164 52">'
        '<rect width="164" height="52" rx="8" fill="#edf3ff"/>'
        '<path d="M8 17L156 35M12 40L151 12M4 29L159 24" stroke="#9db7ff" stroke-width="1"/>'
        '<g fill="#2454c6" font-family="Consolas,monospace" font-size="25" font-weight="700">'
        f'{letters}</g></svg>'
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode("ascii")


def _consume_captcha(request: Request, challenge_id: str, supplied: str) -> bool:
    now = time.monotonic()
    session_id = int(request.state.session["id"])
    with _captcha_lock:
        expired = [key for key, (_, expires, _) in _captchas.items() if expires <= now]
        for key in expired:
            _captchas.pop(key, None)
        challenge = _captchas.pop(challenge_id, None)
    if not challenge or challenge[0] != session_id or challenge[1] <= now:
        return False
    expected = challenge[2]
    actual = hashlib.sha256(f"{challenge_id}:{supplied.strip().upper()}".encode()).hexdigest()
    return secrets.compare_digest(actual, expected)


def _verify_rewrap(request: Request, data: VaultProfileRewrap) -> None:
    identifier = attempt_identifier(request, f"vault-rewrap:{request.state.session['username']}")
    delay = retry_after(identifier)
    if delay:
        raise HTTPException(429, f"Too many verification attempts; retry in {delay} seconds")
    captcha_ok = _consume_captcha(request, data.captcha_id, data.captcha_code)
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ? AND is_active = 1",
            (_user(request),),
        ).fetchone()
    password_ok = bool(row and verify_password(row["password_hash"], data.login_password))
    if not captcha_ok or not password_ok:
        record_failed_attempt(identifier)
        raise HTTPException(401, "Invalid login password or verification code")
    clear_attempts(identifier)


def _validate_profile(data: VaultProfileCreate | VaultProfileRewrap) -> None:
    if getattr(data, "envelope_version", 1) != 1:
        raise HTTPException(422, "Unsupported vault envelope version")
    if getattr(data, "kdf_name", "argon2id") != "argon2id":
        raise HTTPException(422, "Only Argon2id is supported")
    if data.kdf_memory_kib < 65536 or data.kdf_iterations < 3:
        raise HTTPException(422, "Argon2id parameters are below the security floor")
    if not 1 <= data.kdf_parallelism <= 4:
        raise HTTPException(422, "Invalid Argon2id parallelism")


def _profile_row(conn, user_id: int):
    return conn.execute(
        """SELECT envelope_version, kdf_name, kdf_salt, kdf_memory_kib,
                  kdf_iterations, kdf_parallelism, wrapped_dek,
                  wrapped_dek_nonce, recovery_wrapped_dek, recovery_key_id,
                  recovery_confirmed_at, created_at, updated_at
           FROM vault_profiles WHERE user_id = ?""",
        (user_id,),
    ).fetchone()


def _expected_aad(user_id: int, item_key: str) -> str:
    return f"dba-vault:item:{user_id}:{item_key}:v1"


def _backup_document(conn, user_id: int) -> dict:
    profile = _profile_row(conn, user_id)
    if not profile:
        raise HTTPException(404, "Vault is not initialized")
    items = conn.execute(
        """SELECT item_key, envelope_version, ciphertext, nonce, aad, revision,
                  created_at, updated_at
           FROM vault_items WHERE user_id = ? ORDER BY id""",
        (user_id,),
    ).fetchall()
    return {"format": "dba-vault-backup-v1", "profile": dict(profile), "items": [dict(row) for row in items]}


def _digest(document: dict) -> str:
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@router.get("/recovery-public-key")
def recovery_public_key(_: dict = Depends(require_recent_reauth)):
    return public_key_payload()


@router.get("/profile")
def get_profile(request: Request):
    with get_db_ctx() as conn:
        row = _profile_row(conn, _user(request))
    return {"initialized": bool(row), "profile": dict(row) if row else None}


@router.get("/captcha")
def create_captcha(request: Request):
    challenge_id = secrets.token_hex(16)
    code = "".join(secrets.choice(CAPTCHA_ALPHABET) for _ in range(5))
    digest = hashlib.sha256(f"{challenge_id}:{code}".encode()).hexdigest()
    with _captcha_lock:
        _captchas[challenge_id] = (
            int(request.state.session["id"]),
            time.monotonic() + CAPTCHA_TTL_SECONDS,
            digest,
        )
    return {"challenge_id": challenge_id, "image": _captcha_image(code), "expires_in": CAPTCHA_TTL_SECONDS}


@router.post("/profile", status_code=201)
def create_profile(
    data: VaultProfileCreate,
    request: Request,
    _: dict = Depends(require_recent_reauth),
):
    _validate_profile(data)
    public = public_key_payload()
    if data.recovery_key_id != public["key_id"]:
        raise HTTPException(409, "Recovery key changed; refresh and retry")
    user_id = _user(request)
    with get_db_ctx() as conn:
        try:
            conn.execute(
                """INSERT INTO vault_profiles
                   (user_id, envelope_version, kdf_name, kdf_salt, kdf_memory_kib,
                    kdf_iterations, kdf_parallelism, wrapped_dek, wrapped_dek_nonce,
                    recovery_wrapped_dek, recovery_key_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id, data.envelope_version, data.kdf_name, data.kdf_salt,
                    data.kdf_memory_kib, data.kdf_iterations, data.kdf_parallelism,
                    data.wrapped_dek, data.wrapped_dek_nonce,
                    data.recovery_wrapped_dek, data.recovery_key_id,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "Vault is already initialized") from exc
        row = _profile_row(conn, user_id)
    return dict(row)


@router.put("/profile/rewrap")
def rewrap_profile(
    data: VaultProfileRewrap,
    request: Request,
):
    _verify_rewrap(request, data)
    _validate_profile(data)
    user_id = _user(request)
    with get_db_ctx() as conn:
        cursor = conn.execute(
            """UPDATE vault_profiles SET
                   kdf_salt = ?, kdf_memory_kib = ?, kdf_iterations = ?,
                   kdf_parallelism = ?, wrapped_dek = ?, wrapped_dek_nonce = ?,
                   updated_at = CURRENT_TIMESTAMP
               WHERE user_id = ?""",
            (
                data.kdf_salt, data.kdf_memory_kib, data.kdf_iterations,
                data.kdf_parallelism, data.wrapped_dek, data.wrapped_dek_nonce,
                user_id,
            ),
        )
        if cursor.rowcount != 1:
            raise HTTPException(404, "Vault is not initialized")
        conn.commit()
        row = _profile_row(conn, user_id)
    return dict(row)


@router.post("/recovery/confirm")
def confirm_recovery(request: Request, _: dict = Depends(require_recent_reauth)):
    with get_db_ctx() as conn:
        cursor = conn.execute(
            """UPDATE vault_profiles SET recovery_confirmed_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP WHERE user_id = ?""",
            (_user(request),),
        )
        if cursor.rowcount != 1:
            raise HTTPException(404, "Vault is not initialized")
        conn.commit()
    return {"confirmed": True}


@router.get("/items")
def list_items(request: Request, page: int = 1, page_size: int = 100):
    offset, page_size = validate_page(page, page_size)
    user_id = _user(request)
    with get_db_ctx() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM vault_items WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        rows = conn.execute(
            """SELECT id, item_key, envelope_version, ciphertext, nonce, aad,
                      revision, created_at, updated_at
               FROM vault_items WHERE user_id = ?
               ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?""",
            (user_id, page_size, offset),
        ).fetchall()
    return page_response(total, rows, page, page_size)


@router.post("/items", status_code=201)
def create_item(
    data: VaultItemWrite,
    request: Request,
    _: dict = Depends(require_recent_reauth),
):
    user_id = _user(request)
    if data.envelope_version != 1 or data.aad != _expected_aad(user_id, data.item_key):
        raise HTTPException(422, "Invalid vault item envelope")
    with get_db_ctx() as conn:
        try:
            cursor = conn.execute(
                """INSERT INTO vault_items
                   (user_id, item_key, envelope_version, ciphertext, nonce, aad)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, data.item_key, 1, data.ciphertext, data.nonce, data.aad),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "Vault item key or nonce already exists") from exc
        row = conn.execute(
            "SELECT * FROM vault_items WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


@router.put("/items/{item_id}")
def update_item(
    item_id: int,
    data: VaultItemWrite,
    request: Request,
    _: dict = Depends(require_recent_reauth),
):
    user_id = _user(request)
    if data.revision is None:
        raise HTTPException(428, "revision is required")
    if data.envelope_version != 1 or data.aad != _expected_aad(user_id, data.item_key):
        raise HTTPException(422, "Invalid vault item envelope")
    with get_db_ctx() as conn:
        try:
            cursor = conn.execute(
                """UPDATE vault_items SET ciphertext = ?, nonce = ?, aad = ?,
                       revision = revision + 1, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND user_id = ? AND item_key = ? AND revision = ?""",
                (
                    data.ciphertext, data.nonce, data.aad, item_id, user_id,
                    data.item_key, data.revision,
                ),
            )
            if cursor.rowcount != 1:
                exists = conn.execute(
                    "SELECT 1 FROM vault_items WHERE id = ? AND user_id = ?",
                    (item_id, user_id),
                ).fetchone()
                raise HTTPException(409 if exists else 404, "Vault item conflict" if exists else "Vault item not found")
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "Vault nonce was already used") from exc
        row = conn.execute("SELECT * FROM vault_items WHERE id = ?", (item_id,)).fetchone()
    return dict(row)


@router.delete("/items/{item_id}")
def delete_item(
    item_id: int,
    request: Request,
    revision: int,
    _: dict = Depends(require_recent_reauth),
):
    with get_db_ctx() as conn:
        cursor = conn.execute(
            "DELETE FROM vault_items WHERE id = ? AND user_id = ? AND revision = ?",
            (item_id, _user(request), revision),
        )
        if cursor.rowcount != 1:
            raise HTTPException(409, "Vault item conflict or not found")
        conn.commit()
    return {"ok": True}


@router.get("/backup")
def encrypted_backup(request: Request, _: dict = Depends(require_recent_reauth)):
    user_id = _user(request)
    with get_db_ctx() as conn:
        document = _backup_document(conn, user_id)
    return {**document, "digest": _digest(document)}


@router.post("/backup/restore")
def restore_encrypted_backup(
    data: BackupRestore,
    request: Request,
    _: dict = Depends(require_recent_reauth),
):
    if data.confirm != "RESTORE":
        raise HTTPException(422, "Restore confirmation is required")
    document = {"format": "dba-vault-backup-v1", "profile": data.profile, "items": data.items}
    if _digest(document) != data.digest:
        raise HTTPException(422, "Backup digest mismatch")
    required_profile = {
        "envelope_version", "kdf_name", "kdf_salt", "kdf_memory_kib",
        "kdf_iterations", "kdf_parallelism", "wrapped_dek", "wrapped_dek_nonce",
        "recovery_wrapped_dek", "recovery_key_id",
    }
    if not required_profile.issubset(data.profile):
        raise HTTPException(422, "Backup profile is incomplete")
    user_id = _user(request)
    with get_db_ctx() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM vault_items WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM vault_profiles WHERE user_id = ?", (user_id,))
            profile = data.profile
            conn.execute(
                """INSERT INTO vault_profiles
                   (user_id, envelope_version, kdf_name, kdf_salt, kdf_memory_kib,
                    kdf_iterations, kdf_parallelism, wrapped_dek, wrapped_dek_nonce,
                    recovery_wrapped_dek, recovery_key_id, recovery_confirmed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id, profile["envelope_version"], profile["kdf_name"],
                    profile["kdf_salt"], profile["kdf_memory_kib"],
                    profile["kdf_iterations"], profile["kdf_parallelism"],
                    profile["wrapped_dek"], profile["wrapped_dek_nonce"],
                    profile["recovery_wrapped_dek"], profile["recovery_key_id"],
                    profile.get("recovery_confirmed_at"),
                ),
            )
            for item in data.items:
                if item.get("aad") != _expected_aad(user_id, item.get("item_key", "")):
                    raise ValueError("invalid item AAD")
                conn.execute(
                    """INSERT INTO vault_items
                       (user_id, item_key, envelope_version, ciphertext, nonce, aad, revision)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        user_id, item["item_key"], item["envelope_version"],
                        item["ciphertext"], item["nonce"], item["aad"], item["revision"],
                    ),
                )
            conn.execute(
                "INSERT INTO vault_backup_checks(user_id, digest, item_count) VALUES (?, ?, ?)",
                (user_id, data.digest, len(data.items)),
            )
            conn.commit()
        except (KeyError, ValueError, sqlite3.IntegrityError) as exc:
            conn.rollback()
            raise HTTPException(422, "Backup contents are invalid") from exc
    return {"restored": True, "item_count": len(data.items)}


def _legacy_key_path() -> Path:
    return Path(database.DB_PATH).resolve().parent / ".workspace_secret"


def _legacy_decrypt(token: str) -> str:
    key_path = _legacy_key_path()
    if not key_path.exists():
        raise HTTPException(409, "Legacy vault key is unavailable")
    try:
        return Fernet(key_path.read_bytes().strip()).decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise HTTPException(409, "Legacy vault entry cannot be decrypted") from exc


@router.get("/legacy/status")
def legacy_status(request: Request):
    with get_db_ctx() as conn:
        count = conn.execute("SELECT COUNT(*) FROM passwords").fetchone()[0]
    return {"backend_entries": count, "backend_key_available": _legacy_key_path().exists()}


@router.post("/legacy/export")
def legacy_export(request: Request, _: dict = Depends(require_recent_reauth)):
    with get_db_ctx() as conn:
        rows = conn.execute("SELECT * FROM passwords ORDER BY id").fetchall()
    return {
        "items": [
            {
                "legacy_id": row["id"], "site": row["site_name"],
                "url": row["site_url"], "username": row["username"],
                "password": _legacy_decrypt(row["password_enc"]) if row["password_enc"] else "",
                "category": row["category"], "notes": row["notes"],
                "favorite": bool(row["is_favorite"]),
            }
            for row in rows
        ]
    }


@router.post("/legacy/complete")
def legacy_complete(
    data: LegacyComplete,
    request: Request,
    _: dict = Depends(require_recent_reauth),
):
    user_id = _user(request)
    with get_db_ctx() as conn:
        source_ids = [row["id"] for row in conn.execute("SELECT id FROM passwords ORDER BY id")]
        expected_keys = [f"legacy_server_{str(source_id).zfill(8)}" for source_id in source_ids]
        migrated_count = 0
        if expected_keys:
            placeholders = ",".join("?" for _ in expected_keys)
            migrated_count = conn.execute(
                f"SELECT COUNT(*) FROM vault_items WHERE user_id = ? AND item_key IN ({placeholders})",
                (user_id, *expected_keys),
            ).fetchone()[0]
        source_count = len(source_ids)
        if source_count != data.expected_source_count or migrated_count != source_count:
            raise HTTPException(409, "Legacy migration counts do not match")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT OR IGNORE INTO legacy_password_backups
               (id, site_name, site_url, username, password_enc, category, notes,
                is_favorite, created_at, updated_at)
               SELECT id, site_name, site_url, username, password_enc, category,
                      notes, is_favorite, created_at, updated_at FROM passwords"""
        )
        conn.execute("DELETE FROM passwords")
        conn.commit()
    return {"migrated": source_count, "backup_preserved": True}
