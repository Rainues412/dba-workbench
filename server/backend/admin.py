"""Offline-only emergency administration for the local DBA workbench."""
from __future__ import annotations

import argparse
import base64
import getpass
import secrets
import shutil
from pathlib import Path

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend import database
from backend.auth import hash_password, validate_password
from backend.database import get_db_ctx, run_startup_migrations
from backend.observability import record_audit
from backend.vault_recovery import decrypt_recovery_envelope, ensure_recovery_key


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _prompt_new_secret(label: str) -> str:
    first = getpass.getpass(f"New {label}: ")
    second = getpass.getpass(f"Confirm new {label}: ")
    if first != second:
        raise SystemExit("Values do not match")
    validate_password(first)
    return first


def reset_login_password(username: str) -> None:
    password = _prompt_new_secret("login password")
    with get_db_ctx() as conn:
        cursor = conn.execute(
            """UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
               WHERE username = ? COLLATE NOCASE""",
            (hash_password(password), username),
        )
        if cursor.rowcount != 1:
            raise SystemExit("User not found")
        user_id = conn.execute(
            "SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()["id"]
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()
    record_audit(
        action="reset-login-password", object_type="user", object_id=str(user_id),
        result="success", source="offline-cli", actor="offline-admin",
    )
    print("Login password reset; all sessions were revoked.")


def recover_vault(username: str) -> None:
    master_password = _prompt_new_secret("vault master password")
    with get_db_ctx() as conn:
        row = conn.execute(
            """SELECT users.id AS user_id, vault_profiles.* FROM users
               JOIN vault_profiles ON vault_profiles.user_id = users.id
               WHERE users.username = ? COLLATE NOCASE""",
            (username,),
        ).fetchone()
        if not row:
            raise SystemExit("Vault profile not found")
        dek = decrypt_recovery_envelope(row["recovery_wrapped_dek"])
        if len(dek) != 32:
            raise SystemExit("Recovery envelope is invalid")
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)
        kek = hash_secret_raw(
            secret=master_password.encode("utf-8"),
            salt=salt,
            time_cost=int(row["kdf_iterations"]),
            memory_cost=int(row["kdf_memory_kib"]),
            parallelism=int(row["kdf_parallelism"]),
            hash_len=32,
            type=Type.ID,
        )
        aad = f"dba-vault:profile:{row['user_id']}:v1".encode("utf-8")
        wrapped = AESGCM(kek).encrypt(nonce, dek, aad)
        conn.execute(
            """UPDATE vault_profiles SET kdf_salt = ?, wrapped_dek = ?,
                   wrapped_dek_nonce = ?, recovery_confirmed_at = NULL,
                   updated_at = CURRENT_TIMESTAMP WHERE user_id = ?""",
            (_b64(salt), _b64(wrapped), _b64(nonce), row["user_id"]),
        )
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (row["user_id"],))
        conn.commit()
    record_audit(
        action="recover-vault", object_type="vault", object_id=str(row["user_id"]),
        result="success", source="offline-cli", actor="offline-admin",
    )
    print("Vault data key was rewrapped; sign in and confirm recovery backup.")


def backup_recovery_key(output: Path) -> None:
    output = output.resolve()
    required_root = Path(r"D:\Software\AI\Codex").resolve()
    if output != required_root and required_root not in output.parents:
        raise SystemExit(r"Recovery backups must stay under D:\Software\AI\Codex")
    output.mkdir(parents=True, exist_ok=True)
    private_path, public_path = ensure_recovery_key()
    shutil.copy2(private_path, output / private_path.name)
    shutil.copy2(public_path, output / public_path.name)
    print(f"Recovery key pair copied to {output}")


def verify_recovery_key() -> None:
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT user_id, recovery_wrapped_dek FROM vault_profiles"
        ).fetchall()
    for row in rows:
        if len(decrypt_recovery_envelope(row["recovery_wrapped_dek"])) != 32:
            raise SystemExit(f"Recovery envelope failed for user {row['user_id']}")
    print(f"Recovery key verified for {len(rows)} vault profile(s).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    reset = subparsers.add_parser("reset-login-password")
    reset.add_argument("username")
    recover = subparsers.add_parser("recover-vault")
    recover.add_argument("username")
    backup = subparsers.add_parser("backup-recovery-key")
    backup.add_argument("--output", required=True, type=Path)
    subparsers.add_parser("verify-recovery-key")
    args = parser.parse_args()
    run_startup_migrations()
    if args.command == "reset-login-password":
        reset_login_password(args.username)
    elif args.command == "recover-vault":
        recover_vault(args.username)
    elif args.command == "backup-recovery-key":
        backup_recovery_key(args.output)
    else:
        verify_recovery_key()


if __name__ == "__main__":
    main()
