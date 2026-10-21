"""Administrator recovery key lifecycle and data-key rewrapping helpers.

The private key never leaves the backend. It is consumed by the offline admin
command or by the authenticated local recovery endpoint and is never returned
through HTTP.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from pathlib import Path

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from backend import database


def _paths() -> tuple[Path, Path]:
    root = Path(database.DB_PATH).resolve().parent
    return root / ".vault_recovery_private.pem", root / ".vault_recovery_public.pem"


def _key_id(public_der: bytes) -> str:
    return hashlib.sha256(public_der).hexdigest()[:24]


def ensure_recovery_key() -> tuple[Path, Path]:
    private_path, public_path = _paths()
    if private_path.exists() and public_path.exists():
        return private_path, public_path
    if private_path.exists() != public_path.exists():
        raise RuntimeError("recovery key pair is incomplete; restore it from backup")
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    private_bytes = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_bytes = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_tmp = private_path.with_suffix(".tmp")
    public_tmp = public_path.with_suffix(".tmp")
    private_tmp.write_bytes(private_bytes)
    public_tmp.write_bytes(public_bytes)
    os.chmod(private_tmp, 0o600)
    os.chmod(public_tmp, 0o644)
    private_tmp.replace(private_path)
    public_tmp.replace(public_path)
    return private_path, public_path


def public_key_payload() -> dict[str, str]:
    _, public_path = ensure_recovery_key()
    public_pem = public_path.read_bytes()
    public_key = serialization.load_pem_public_key(public_pem)
    public_der = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return {
        "algorithm": "RSA-OAEP-3072-SHA256",
        "key_id": _key_id(public_der),
        "public_key_pem": public_pem.decode("ascii"),
    }


def decrypt_recovery_envelope(ciphertext_b64: str) -> bytes:
    private_path, _ = _paths()
    if not private_path.exists():
        raise RuntimeError("administrator recovery key is unavailable")
    key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    ciphertext = base64.urlsafe_b64decode(ciphertext_b64 + "=" * (-len(ciphertext_b64) % 4))
    return key.decrypt(
        ciphertext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=b"dba-vault-recovery-v1",
        ),
    )


def wrap_dek_for_master_password(
    dek: bytes,
    master_password: str,
    user_id: int,
    *,
    memory_kib: int = 65536,
    iterations: int = 3,
    parallelism: int = 1,
) -> dict[str, str | int]:
    if len(dek) != 32:
        raise ValueError("recovery envelope is invalid")
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    kek = hash_secret_raw(
        secret=master_password.encode("utf-8"),
        salt=salt,
        time_cost=iterations,
        memory_cost=memory_kib,
        parallelism=parallelism,
        hash_len=32,
        type=Type.ID,
    )
    aad = f"dba-vault:profile:{user_id}:v1".encode("utf-8")
    wrapped = AESGCM(kek).encrypt(nonce, dek, aad)
    encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
    return {
        "kdf_salt": encode(salt),
        "kdf_memory_kib": memory_kib,
        "kdf_iterations": iterations,
        "kdf_parallelism": parallelism,
        "wrapped_dek": encode(wrapped),
        "wrapped_dek_nonce": encode(nonce),
    }
