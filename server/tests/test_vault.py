from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path

import pytest
from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pyrage import decrypt, x25519

from backend.vault_recovery import decrypt_recovery_envelope
from backend import admin
from backend.routers import vault as vault_router


LOGIN_PASSWORD = "test-only-owner-passphrase"
MASTER_PASSWORD = "test-only-vault-passphrase"


def test_recovery_key_backup_destination_is_portable_and_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_directory = tmp_path / "server-data"
    data_directory.mkdir()
    private_key = data_directory / ".vault_recovery_private.pem"
    public_key = data_directory / ".vault_recovery_public.pem"
    private_key.write_text("private", encoding="utf-8")
    public_key.write_text("public", encoding="utf-8")
    monkeypatch.setattr(admin.database, "DB_PATH", str(data_directory / "workspace.db"))
    monkeypatch.setattr(admin, "ensure_recovery_key", lambda: (private_key, public_key))

    destination = tmp_path / "portable-backup"
    admin.backup_recovery_key(destination)
    assert (destination / private_key.name).read_text(encoding="utf-8") == "private"
    assert (destination / public_key.name).read_text(encoding="utf-8") == "public"

    with pytest.raises(SystemExit, match="absolute path"):
        admin.backup_recovery_key(Path("relative-backup"))
    with pytest.raises(SystemExit, match="outside the server data directory"):
        admin.backup_recovery_key(data_directory / "backup")


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def reauthenticate(client: TestClient) -> None:
    response = client.post(
        "/api/auth/reauthenticate", json={"password": LOGIN_PASSWORD}
    )
    assert response.status_code == 200, response.text


def initialize_vault(client: TestClient, questions=None) -> tuple[bytes, bytes]:
    if questions is None:
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
            **({"questions": questions} if questions is not None else {}),
        },
    )
    assert response.status_code == 201, response.text
    return dek, recovery_wrapped


def master_proof(client, password):
    profile = client.get("/api/vault/profile").json()["profile"]
    kek = hash_secret_raw(
        password.encode(), unb64(profile["kdf_salt"]), time_cost=3, memory_cost=65536,
        parallelism=1, hash_len=32, type=Type.ID,
    )
    return {"wrapping_key": b64(kek)}


def desktop_unlock(client, password):
    return client.post("/api/vault/unlock", json=master_proof(client, password))


def test_desktop_recovery_and_password_change_preserve_items(client, isolated_app, monkeypatch):
    from backend import auth

    monkeypatch.setattr(auth, "_desktop_token", "test-only-desktop-token")
    questions = [
        {"question": "测试问题甲", "answer": "unique-test-only-answer"},
        {"question": "测试问题乙", "answer": "another-test-only-answer"},
    ]
    dek, _ = initialize_vault(client, questions)
    assert client.get("/api/vault/profile").json()["questions_set"]
    assert client.get("/api/vault/recovery/questions").json() == {"questions": [q["question"] for q in questions]}
    old_grant = {"X-DBA-Vault-Token": desktop_unlock(client, MASTER_PASSWORD).json()["token"]}
    item = encrypted_item(dek, "test-item-key-0021", bytes(range(12)), "original-test-only-value")
    assert client.post("/api/vault/items", json=item, headers=old_grant).status_code == 201
    backup = client.post("/api/vault/backups").json()["filename"]
    assert client.put("/api/vault/profile/password", json={
        "current_master_password": "wrong-test-only-password", "new_master_password": "new-test-only-password",
    }).status_code == 401
    with sqlite3.connect(isolated_app[1]) as conn:
        stored = [row[0] for row in conn.execute("SELECT answer_hash FROM vault_recovery_questions")]
        assert all(value.startswith("$argon2id$") for value in stored)
        assert all(question["answer"] not in " ".join(stored) for question in questions)
    assert client.post("/api/vault/recovery/verify", json={"answers": [questions[0]["answer"]]}).status_code == 401
    result = client.post("/api/vault/recovery/verify", json={"answers": [q["answer"] for q in questions]})
    assert result.status_code == 200, result.text
    reset = {"ticket": result.json()["ticket"], "new_master_password": "reset-test-only-password"}
    assert client.put("/api/vault/recovery/reset", json=reset).status_code == 204
    assert client.put("/api/vault/recovery/reset", json=reset).status_code == 403
    assert client.get("/api/vault/items", headers=old_grant).status_code == 403
    assert desktop_unlock(client, MASTER_PASSWORD).status_code == 401
    assert client.put("/api/vault/profile/password", json={
        "current_master_password": reset["new_master_password"], "new_master_password": "changed-test-only-password",
    }).status_code == 204
    new_grant = {"X-DBA-Vault-Token": desktop_unlock(client, "changed-test-only-password").json()["token"]}
    saved = client.get("/api/vault/items", headers=new_grant).json()["items"][0]
    assert saved["ciphertext"] == item["ciphertext"]
    assert saved["nonce"] == item["nonce"]
    proof = master_proof(client, "changed-test-only-password")
    key = client.post("/api/vault/backup/key", json=proof, headers=new_grant).json()["identity"]
    encrypted = client.get(f"/api/vault/backups/{backup}", headers=new_grant).json()["encrypted"]
    assert json.loads(decrypt(encrypted.encode(), [x25519.Identity.from_str(key)]))["items"][0]["ciphertext"] == item["ciphertext"]


def test_existing_desktop_vault_can_enroll_only_after_unlock(client, monkeypatch):
    from backend import auth

    initialize_vault(client)
    monkeypatch.setattr(auth, "_desktop_token", "test-only-desktop-token")
    questions = {"questions": [{"question": "旧保险箱问题", "answer": "old-vault-test-only-answer"}]}
    assert client.get("/api/vault/recovery/questions").json() == {"questions": []}
    assert client.post("/api/vault/recovery/questions", json=questions).status_code == 403
    grant = {"X-DBA-Vault-Token": desktop_unlock(client, MASTER_PASSWORD).json()["token"]}
    assert client.post("/api/vault/recovery/questions", json=questions, headers=grant).status_code == 204
    assert client.post("/api/vault/recovery/questions", json=questions, headers=grant).status_code == 409
    for _ in range(5):
        assert client.post("/api/vault/recovery/verify", json={"answers": ["wrong"]}).status_code == 401
    assert client.post("/api/vault/recovery/verify", json={"answers": ["wrong"]}).status_code == 429


def test_windows_credential_auto_unlock_respects_navigation_and_explicit_lock(client, monkeypatch):
    from backend import auth, vault_device

    if not vault_device.available():
        pytest.skip("Windows Credential Manager is required")
    monkeypatch.setattr(auth, "_desktop_token", "test-only-desktop-token")
    dek, _ = initialize_vault(client, [{"question": "测试问题", "answer": "auto-unlock-test-only-answer"}])
    route = "/api/vault/auto-unlock"
    try:
        assert client.get(route).json() == {"available": True, "enabled": False}
        assert client.put(route, json={"enabled": True}).status_code == 403
        grant = {"X-DBA-Vault-Token": desktop_unlock(client, MASTER_PASSWORD).json()["token"]}
        assert client.put(route, json={"enabled": True}, headers=grant).json()["enabled"]
        assert client.get(route).json()["enabled"]
        result = client.post(route).json()
        assert unb64(result["data_key"]) == dek
        grant = {"X-DBA-Vault-Token": result["token"]}
        assert client.post("/api/vault/unlock/renew", headers=grant).status_code == 200
        assert client.delete("/api/vault/unlock?block_auto_unlock=false", headers=grant).status_code == 204
        assert client.get("/api/vault/items", headers=grant).status_code == 403
        result = client.post(route).json()
        assert unb64(result["data_key"]) == dek
        grant = {"X-DBA-Vault-Token": result["token"]}
        assert client.delete("/api/vault/unlock", headers=grant).status_code == 204
        assert client.post(route).json() is None
        # Page cleanup cannot undo a deliberate or idle lock.
        assert client.delete("/api/vault/unlock?block_auto_unlock=false", headers=grant).status_code == 204
        assert client.post(route).json() is None
        assert desktop_unlock(client, MASTER_PASSWORD).status_code == 200
        assert unb64(client.post(route).json()["data_key"]) == dek
        assert client.put(route, json={"enabled": False}).status_code == 200
        assert not client.get(route).json()["enabled"]
        assert client.post(route).json() is None
        # A fresh application process also permits start-up auto unlock after a lock.
        grant = {"X-DBA-Vault-Token": desktop_unlock(client, MASTER_PASSWORD).json()["token"]}
        assert client.put(route, json={"enabled": True}, headers=grant).status_code == 200
        assert client.delete("/api/vault/unlock", headers=grant).status_code == 204
        monkeypatch.setattr(vault_router, "_auto_unlock_blocked", set())
        assert unb64(client.post(route).json()["data_key"]) == dek
    finally:
        vault_device.delete_key(1)


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


def test_existing_desktop_vault_requires_a_master_password_grant(client, isolated_app, monkeypatch):
    from backend import auth

    dek, _ = initialize_vault(client)
    _, test_db = isolated_app
    test_db.with_name(".vault_recovery_private.pem").unlink()
    monkeypatch.setattr(auth, "_desktop_token", "test-only-desktop-token")

    item = encrypted_item(dek, "desktop-item-key-001", bytes(range(12)), "test-secret")
    assert client.get("/api/vault/items").status_code == 403
    assert client.post("/api/vault/items", json=item).status_code == 403
    assert client.get("/api/vault/captcha").status_code == 404
    assert client.post("/api/vault/unlock", json={"wrapping_key": b64(bytes(32))}).status_code == 401

    profile = client.get("/api/vault/profile").json()["profile"]
    wrapping_key = hash_secret_raw(MASTER_PASSWORD.encode(), unb64(profile["kdf_salt"]),
                                  time_cost=3, memory_cost=65536, parallelism=1, hash_len=32, type=Type.ID)
    result = client.post("/api/vault/unlock", json={"wrapping_key": b64(wrapping_key)})
    assert result.status_code == 200, result.text
    headers = {"X-DBA-Vault-Token": result.json()["token"]}
    assert client.post("/api/vault/items", json=item, headers=headers).status_code == 201
    assert client.get("/api/vault/items", headers=headers).json()["total"] == 1
    assert client.delete("/api/vault/unlock", headers=headers).status_code == 204
    assert client.get("/api/vault/items", headers=headers).status_code == 403


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


def test_forgot_master_password_recovers_without_reencrypting_items(client: TestClient, monkeypatch) -> None:
    dek, _ = initialize_vault(client)
    item = encrypted_item(dek, "test-item-key-0001", bytes(range(12)), "test-value")
    created = client.post("/api/vault/items", json=item).json()
    monkeypatch.setattr(vault_router.secrets, "choice", lambda _: "A")
    challenge = client.get("/api/vault/captcha").json()
    payload = {
        "new_master_password": "test-only-new-vault-passphrase",
        "login_password": "wrong-login-password",
        "captcha_id": challenge["challenge_id"], "captcha_code": "AAAAA",
    }
    assert client.put("/api/vault/profile/recover", json=payload).status_code == 401

    challenge = client.get("/api/vault/captcha").json()
    payload.update(login_password=LOGIN_PASSWORD, captcha_id=challenge["challenge_id"], captcha_code="WRONG")
    assert client.put("/api/vault/profile/recover", json=payload).status_code == 401

    challenge = client.get("/api/vault/captcha").json()
    payload.update(captcha_id=challenge["challenge_id"], captcha_code="AAAAA")
    changed = client.put(
        "/api/vault/profile/recover",
        json=payload,
    )
    assert changed.status_code == 200
    profile = changed.json()
    new_kek = hash_secret_raw(
        payload["new_master_password"].encode(), unb64(profile["kdf_salt"]), time_cost=3,
        memory_cost=65536, parallelism=1, hash_len=32, type=Type.ID,
    )
    recovered = AESGCM(new_kek).decrypt(
        unb64(profile["wrapped_dek_nonce"]),
        unb64(profile["wrapped_dek"]),
        b"dba-vault:profile:1:v1",
    )
    assert recovered == dek
    assert profile["recovery_confirmed_at"] is None
    listed = client.get("/api/vault/items").json()["items"][0]
    assert listed["ciphertext"] == created["ciphertext"]


def test_backup_restore_preserves_current_items_on_conflict_or_write_failure(client, isolated_app, monkeypatch):
    from backend import vault_backups

    _, path = isolated_app
    dek, _ = initialize_vault(client)
    original = encrypted_item(dek, "test-item-key-0001", bytes(range(12)), "original-value")
    incoming = encrypted_item(dek, "test-item-key-0002", bytes(range(1, 13)), "imported-value")
    assert client.post("/api/vault/items", json=original).status_code == 201
    existing = client.get("/api/vault/backup").json()
    proof = master_proof(client, MASTER_PASSWORD)
    payload = {**proof, "confirm": "RESTORE", "expected_digest": existing["digest"], "items": [incoming]}
    assert client.post("/api/vault/backup/restore", json={**payload, "wrapping_key": b64(bytes(32))}).status_code == 401
    assert client.post("/api/vault/backup/restore", json={**payload, "expected_digest": "0" * 64}).status_code == 409
    assert client.post("/api/vault/backup/restore", json={**payload, "confirm": "cancel"}).status_code == 422

    with monkeypatch.context() as patch:
        def disk_unavailable(*args, **kwargs):
            raise OSError("test-only storage failure")
        patch.setattr(vault_backups, "save", disk_unavailable)
        assert client.post("/api/vault/backup/restore", json=payload).status_code == 503
    assert client.get("/api/vault/backup").json() == existing

    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TRIGGER test_reject_restore BEFORE INSERT ON vault_items
                        BEGIN SELECT RAISE(ABORT, 'test-only write failure'); END;""")
    assert client.post("/api/vault/backup/restore", json=payload).status_code == 503
    assert client.get("/api/vault/backup").json() == existing
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TRIGGER test_reject_restore")

    restored = client.post("/api/vault/backup/restore", json=payload)
    assert restored.status_code == 200, restored.text
    assert restored.json()["item_count"] == 1
    safety = restored.json()["safety_backup"]
    key_response = client.post("/api/vault/backup/key", json=proof)
    identity = x25519.Identity.from_str(key_response.json()["identity"])
    saved = client.get(f"/api/vault/backups/{safety}").json()
    assert json.loads(decrypt(saved["encrypted"].encode(), [identity]))["items"] == existing["items"]
    current = client.get("/api/vault/backup").json()
    assert current["profile"] == existing["profile"]
    assert current["items"][0]["ciphertext"] == incoming["ciphertext"]


def test_scheduled_portable_backup_respects_interval_and_retention(client, isolated_app, monkeypatch):
    import os
    from datetime import datetime, timedelta, timezone

    from backend import vault_backups

    dek, _ = initialize_vault(client)
    item = encrypted_item(dek, "test-item-key-0001", bytes(range(12)), "original-value")
    assert client.post("/api/vault/items", json=item).status_code == 201
    response = client.get("/api/vault/backup-settings")
    assert response.json() == {"interval_hours": 24, "retention": 10, "portable_ready": False, "key_exported": False,
                               "directory": str(vault_backups.backup_root()), "key_directory": str(vault_backups.portable_key_directory(1))}
    opened_paths = []
    monkeypatch.setattr(os, "startfile", opened_paths.append)
    assert client.post("/api/vault/backups/open-directory", json={"path": "C:/test-other"}).status_code == 204
    assert client.post("/api/vault/backups/open-directory?kind=key", json={"path": "C:/test-other"}).status_code == 204
    assert client.post("/api/vault/backups/open-directory?kind=other").status_code == 422
    assert opened_paths == [vault_backups.backup_root(), vault_backups.portable_key_directory(1)]
    assert client.put("/api/vault/backup-settings", json={"directory": "C:/test-other"}).status_code == 422
    assert client.get("/api/vault/backup-settings").json()["directory"] == str(vault_backups.backup_root())
    assert client.put("/api/vault/backup-settings", json={"interval_hours": 7, "retention": 3}).status_code == 422
    assert client.put("/api/vault/backup-settings", json={"interval_hours": 6, "retention": 3}).status_code == 200

    proof = master_proof(client, MASTER_PASSWORD)
    assert client.post("/api/vault/backups").status_code == 409
    assert client.get("/api/vault/backups").json() == []
    assert client.post("/api/vault/backup-settings/prepare", json=proof).status_code == 204
    assert client.post("/api/vault/backups").status_code == 201
    assert client.get("/api/vault/backup-settings").json()["portable_ready"]
    key_response = client.post("/api/vault/backup/key?export=true", json=proof)
    assert key_response.status_code == 200
    identity = x25519.Identity.from_str(key_response.json()["identity"])
    portable, = vault_backups.portable_key_directory(1).glob("*.key")
    assert portable.read_text(encoding="ascii").strip() == str(identity)
    protected, = vault_backups.key_directory(1).glob("*.dpapi")
    assert str(identity).encode("ascii") not in protected.read_bytes()
    # Existing vaults can create a missing portable copy from their original local key.
    portable.unlink()
    assert client.get("/api/vault/backup-settings").json()["key_exported"]
    vault_router.run_scheduled_backups()
    assert portable.read_text(encoding="ascii").strip() == str(identity)

    def verify_document(entry):
        encrypted = vault_backups.read(1, entry["filename"])
        assert encrypted.startswith(b"-----BEGIN AGE ENCRYPTED FILE-----")
        backup = json.loads(decrypt(encrypted, [identity]))
        assert backup["format"] == "dba-vault-backup-v3" and backup["source_user_id"] == 1
        assert decrypt(unb64(backup["wrapped_dek"]), [identity]) == dek
        assert backup["items"][0]["ciphertext"] == item["ciphertext"]
        assert set(backup) == {"format", "source_user_id", "wrapped_dek", "items"}

    files = client.get("/api/vault/backups").json()
    assert len(files) == 2 and files[0]["kind"] == "auto"
    verify_document(files[0])
    vault_router.run_scheduled_backups()
    assert client.get("/api/vault/backups").json() == files

    def age_files():
        now = datetime.now(timezone.utc)
        for offset, entry in enumerate(client.get("/api/vault/backups").json(), 7):
            old = (now - timedelta(hours=offset)).timestamp()
            os.utime(vault_backups.directory(1) / entry["filename"], (old, old))

    for _ in range(4):
        age_files()
        vault_router.run_scheduled_backups()
    files = client.get("/api/vault/backups").json()
    assert len([entry for entry in files if entry["kind"] == "auto"]) == 3
    assert len([entry for entry in files if entry["kind"] == "manual"]) == 1
    verify_document(files[0])
    assert client.put("/api/vault/backup-settings", json={"interval_hours": 0, "retention": 3}).status_code == 200
    age_files()
    disabled = client.get("/api/vault/backups").json()
    vault_router.run_scheduled_backups()
    assert client.get("/api/vault/backups").json() == disabled


def test_backup_names_and_deleting_the_last_file(client, isolated_app):
    from backend import vault_backups

    initialize_vault(client)
    proof = master_proof(client, MASTER_PASSWORD)
    assert client.post("/api/vault/backup-settings/prepare", json=proof).status_code == 204
    legacy_dir = Path(isolated_app[1]).parent / "vault-backups" / "1"
    legacy_dir.mkdir(parents=True)
    name = "backup-20261010-120000-abcdefabcdef.json"
    file = legacy_dir / name
    original = client.get("/api/vault/backup").content
    file.write_bytes(original)
    url = f"/api/vault/backups/{name}"
    assert client.patch(url, json={"display_name": "  升级前快照  "}).status_code == 204
    listing = client.get("/api/vault/backups").json()
    assert [(entry["filename"], entry["display_name"]) for entry in listing] == [(name, "升级前快照")]
    assert file.read_bytes() == original
    assert client.get(url).content == original
    assert client.delete("/api/vault/backups/ordinary.txt").status_code == 404

    replacement = client.delete(url).json()["replacement"]
    assert not file.exists()
    assert replacement.startswith("auto-")
    new_file = vault_backups.directory(1) / replacement
    assert new_file.is_file()
    sample_age = new_file.read_bytes()
    assert [entry["filename"] for entry in client.get("/api/vault/backups").json()] == [replacement]

    assert client.put("/api/vault/backup-settings", json={"interval_hours": 0}).status_code == 200
    assert client.delete(f"/api/vault/backups/{replacement}").json() == {"replacement": None}
    vault_router.run_scheduled_backups()
    assert client.get("/api/vault/backups").json() == []

    old_auto = legacy_dir / "auto-20261010-120000-abcdefabcdef.age"
    old_auto.write_bytes(sample_age)
    assert client.put("/api/vault/backup-settings", json={"interval_hours": 24}).status_code == 200
    vault_router.run_scheduled_backups()
    assert old_auto.read_bytes() == sample_age
    assert len(list(vault_backups.directory(1).glob("auto-*.age"))) == 1


def test_desktop_picks_only_one_user_selected_supported_file(client, tmp_path, monkeypatch):
    from backend import auth, vault_backups

    monkeypatch.setattr(auth, "_desktop_token", "test-only-desktop-token")
    initialize_vault(client, [{"question": "测试问题", "answer": "test-only-picker-answer"}])
    grant = {"X-DBA-Vault-Token": desktop_unlock(client, MASTER_PASSWORD).json()["token"]}
    calls = []
    route = "/api/vault/backups/pick-file?kind=key"
    key = tmp_path / "test-only-key.txt"
    key.write_text("unrelated file", encoding="utf-8")
    monkeypatch.setattr(vault_router, "pick_native_file", lambda *args: calls.append(args) or str(key))
    assert client.post(route).status_code == 403
    assert not calls
    assert client.post(route, headers=grant).status_code == 422
    identity = str(x25519.Identity.generate())
    key.write_text(identity, encoding="utf-8")
    result = client.post(route, headers=grant, json={"path": "C:/unrelated.txt"})
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert result.json() == {"name": key.name, "path": str(key), "text": identity}
    assert calls[-1] == ("选择备份恢复密钥", str(vault_backups.portable_key_directory(1)), "*.txt;*.key")


def test_source_backup_root_is_fixed_at_the_repository_root(monkeypatch):
    from backend import database, vault_backups

    server = Path(vault_backups.__file__).resolve().parents[1]
    monkeypatch.setattr(database, "DB_PATH", str(server / "workspace.db"))
    assert vault_backups.backup_root() == server.parent / "backups"


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
