from __future__ import annotations

import base64
import json
import sqlite3

import pytest
from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from backend.vault_recovery import decrypt_recovery_envelope
from backend import admin


LOGIN_PASSWORD = "test-only-owner-passphrase"
MASTER_PASSWORD = "test-only-vault-passphrase"


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def reauthenticate(client: TestClient) -> None:
    response = client.post(
        "/api/auth/reauthenticate", json={"password": LOGIN_PASSWORD}
    )
    assert response.status_code == 200, response.text


def initialize_vault(client: TestClient) -> tuple[bytes, bytes]:
    reauthenticate(client)
    key_response = client.get("/api/vault/recovery-public-key")
    assert key_response.status_code == 200, key_response.text
    recovery = key_response.json()
    user_id = 1
    dek = bytes(range(32))
    salt = bytes(range(16))
    wrap_nonce = bytes(range(12))
    kek = hash_secret_raw(
        MASTER_PASSWORD.encode(), salt, time_cost=3, memory_cost=65536,
        parallelism=1, hash_len=32, type=Type.ID,
    )
    profile_aad = f"dba-vault:profile:{user_id}:v1".encode()
    wrapped_dek = AESGCM(kek).encrypt(wrap_nonce, dek, profile_aad)
    public_key = serialization.load_pem_public_key(
        recovery["public_key_pem"].encode("ascii")
    )
    recovery_wrapped = public_key.encrypt(
        dek,
        padding.OAEP(
            mgf=padding.MGF1(hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=b"dba-vault-recovery-v1",
        ),
    )
    response = client.post(
        "/api/vault/profile",
        json={
            "envelope_version": 1,
            "kdf_name": "argon2id",
            "kdf_salt": b64(salt),
            "kdf_memory_kib": 65536,
            "kdf_iterations": 3,
            "kdf_parallelism": 1,
            "wrapped_dek": b64(wrapped_dek),
            "wrapped_dek_nonce": b64(wrap_nonce),
            "recovery_wrapped_dek": b64(recovery_wrapped),
            "recovery_key_id": recovery["key_id"],
        },
    )
    assert response.status_code == 201, response.text
    return dek, recovery_wrapped


def encrypted_item(dek: bytes, item_key: str, nonce: bytes, password: str) -> dict:
    aad = f"dba-vault:item:1:{item_key}:v1"
    payload = json.dumps(
        {"site": "test-service", "username": "test-user", "password": password, "notes": ""},
        separators=(",", ":"),
    ).encode()
    return {
        "item_key": item_key,
        "envelope_version": 1,
        "ciphertext": b64(AESGCM(dek).encrypt(nonce, payload, aad.encode())),
        "nonce": b64(nonce),
        "aad": aad,
    }


def test_versioned_envelope_tamper_nonce_and_recovery(
    client: TestClient, isolated_app
) -> None:
    _, test_db = isolated_app
    dek, recovery_wrapped = initialize_vault(client)
    assert decrypt_recovery_envelope(b64(recovery_wrapped)) == dek

    one = encrypted_item(dek, "test-item-key-0001", bytes(range(12)), "test-secret-value")
    two = encrypted_item(dek, "test-item-key-0002", bytes(range(1, 13)), "test-secret-value")
    assert one["ciphertext"] != two["ciphertext"]
    first = client.post("/api/vault/items", json=one)
    second = client.post("/api/vault/items", json=two)
    assert first.status_code == 201
    assert second.status_code == 201

    duplicate_nonce = encrypted_item(
        dek, "test-item-key-0003", bytes(range(12)), "another-test-value"
    )
    assert client.post("/api/vault/items", json=duplicate_nonce).status_code == 409

    ciphertext = bytearray(unb64(one["ciphertext"]))
    ciphertext[0] ^= 1
    with pytest.raises(InvalidTag):
        AESGCM(dek).decrypt(bytes(range(12)), bytes(ciphertext), one["aad"].encode())

    with sqlite3.connect(test_db) as conn:
        db_dump = " ".join(
            value
            for row in conn.execute("SELECT ciphertext, aad FROM vault_items")
            for value in row
        )
    assert "test-secret-value" not in db_dump


def test_master_password_change_only_rewraps_dek(client: TestClient) -> None:
    dek, _ = initialize_vault(client)
    item = encrypted_item(dek, "test-item-key-0001", bytes(range(12)), "test-value")
    created = client.post("/api/vault/items", json=item).json()
    new_salt = bytes(range(16, 32))
    new_nonce = bytes(range(12, 24))
    new_kek = hash_secret_raw(
        b"test-only-new-vault-passphrase", new_salt, time_cost=3,
        memory_cost=65536, parallelism=1, hash_len=32, type=Type.ID,
    )
    wrapped = AESGCM(new_kek).encrypt(
        new_nonce, dek, b"dba-vault:profile:1:v1"
    )
    changed = client.put(
        "/api/vault/profile/rewrap",
        json={
            "kdf_salt": b64(new_salt), "kdf_memory_kib": 65536,
            "kdf_iterations": 3, "kdf_parallelism": 1,
            "wrapped_dek": b64(wrapped), "wrapped_dek_nonce": b64(new_nonce),
        },
    )
    assert changed.status_code == 200
    listed = client.get("/api/vault/items").json()["items"][0]
    assert listed["ciphertext"] == created["ciphertext"]


def test_encrypted_backup_detects_tampering_and_restores(client: TestClient) -> None:
    dek, _ = initialize_vault(client)
    client.post(
        "/api/vault/items",
        json=encrypted_item(dek, "test-item-key-0001", bytes(range(12)), "test-value"),
    )
    backup = client.get("/api/vault/backup")
    assert backup.status_code == 200
    document = backup.json()
    tampered = dict(document)
    tampered["items"] = [dict(document["items"][0], ciphertext="tampered-value-0000")]
    tampered["confirm"] = "RESTORE"
    assert client.post("/api/vault/backup/restore", json=tampered).status_code == 422
    document["confirm"] = "RESTORE"
    restored = client.post("/api/vault/backup/restore", json=document)
    assert restored.status_code == 200
    assert restored.json()["item_count"] == 1


def test_offline_admin_recovery_rewraps_without_reencrypting_items(
    client: TestClient, isolated_app, monkeypatch
) -> None:
    _, test_db = isolated_app
    dek, _ = initialize_vault(client)
    created = client.post(
        "/api/vault/items",
        json=encrypted_item(dek, "test-item-key-0001", bytes(range(12)), "test-value"),
    ).json()
    answers = iter(["test-only-recovered-master", "test-only-recovered-master"])
    monkeypatch.setattr(admin.getpass, "getpass", lambda _: next(answers))
    admin.recover_vault("test-owner")

    with sqlite3.connect(test_db) as conn:
        conn.row_factory = sqlite3.Row
        profile = conn.execute("SELECT * FROM vault_profiles WHERE user_id = 1").fetchone()
        item = conn.execute("SELECT ciphertext FROM vault_items WHERE user_id = 1").fetchone()
    recovered_kek = hash_secret_raw(
        b"test-only-recovered-master", unb64(profile["kdf_salt"]),
        time_cost=profile["kdf_iterations"], memory_cost=profile["kdf_memory_kib"],
        parallelism=profile["kdf_parallelism"], hash_len=32, type=Type.ID,
    )
    recovered_dek = AESGCM(recovered_kek).decrypt(
        unb64(profile["wrapped_dek_nonce"]), unb64(profile["wrapped_dek"]),
        b"dba-vault:profile:1:v1",
    )
    assert recovered_dek == dek
    assert item["ciphertext"] == created["ciphertext"]


def test_legacy_cleanup_requires_the_exact_migrated_item_key(
    client: TestClient, isolated_app
) -> None:
    _, test_db = isolated_app
    dek, _ = initialize_vault(client)
    legacy_key = Fernet.generate_key()
    key_path = test_db.parent / ".workspace_secret"
    key_path.write_bytes(legacy_key)
    with sqlite3.connect(test_db) as conn:
        cursor = conn.execute(
            "INSERT INTO passwords(site_name, username, password_enc) VALUES (?, ?, ?)",
            ("legacy-service", "legacy-user", Fernet(legacy_key).encrypt(b"legacy-test-secret").decode()),
        )
        source_id = cursor.lastrowid
        conn.commit()

    unrelated = encrypted_item(dek, "unrelated-item-key", bytes(range(12)), "test-value")
    assert client.post("/api/vault/items", json=unrelated).status_code == 201
    assert client.post("/api/vault/legacy/complete", json={"expected_source_count": 1}).status_code == 409

    expected_key = f"legacy_server_{source_id:08d}"
    migrated = encrypted_item(dek, expected_key, bytes(range(1, 13)), "legacy-test-secret")
    assert client.post("/api/vault/items", json=migrated).status_code == 201
    completed = client.post("/api/vault/legacy/complete", json={"expected_source_count": 1})
    assert completed.status_code == 200
    with sqlite3.connect(test_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM passwords").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM legacy_password_backups").fetchone()[0] == 1
