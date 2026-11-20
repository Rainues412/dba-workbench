from __future__ import annotations

import base64
import sqlite3
from datetime import datetime, timedelta, timezone
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image


OWNER = {"username": "test-owner", "password": "test-only-owner-passphrase"}


def test_first_owner_setup_session_and_csrf(raw_client: TestClient, isolated_app) -> None:
    _, test_db = isolated_app
    assert raw_client.get("/api/auth/status").json() == {
        "authenticated": False,
        "setup_required": True,
    }
    assert raw_client.get("/api/dashboard/stats").status_code == 401

    setup = raw_client.post("/api/auth/setup", json=OWNER)
    assert setup.status_code == 201
    assert setup.cookies.get("dba_session")
    assert "HttpOnly" in setup.headers["set-cookie"]
    assert "SameSite=strict" in setup.headers["set-cookie"]

    session = setup.json()
    assert session["user"]["roles"] == ["owner"]
    assert session["reauth_minutes"] == 30
    assert raw_client.get("/api/dashboard/stats").status_code == 200
    assert raw_client.post("/api/tasks/", json={"title": "blocked"}).status_code == 403
    allowed = raw_client.post(
        "/api/tasks/",
        json={"title": "allowed"},
        headers={"X-CSRF-Token": session["csrf_token"]},
    )
    assert allowed.status_code == 200
    assert raw_client.post("/api/auth/setup", json=OWNER).status_code == 409

    with sqlite3.connect(test_db) as conn:
        stored = conn.execute("SELECT password_hash FROM users").fetchone()[0]
        assert stored.startswith("$argon2id$")
        assert OWNER["password"] not in stored


def test_password_minimum_is_nine_characters(raw_client: TestClient) -> None:
    rejected = raw_client.post(
        "/api/auth/setup",
        json={"username": "owner", "password": "12345678"},
    )
    assert rejected.status_code == 422
    accepted = raw_client.post(
        "/api/auth/setup",
        json={"username": "owner", "password": "123456789"},
    )
    assert accepted.status_code == 201


def test_profile_is_session_scoped_versioned_and_saves_a_thumbnail(raw_client: TestClient) -> None:
    path = "/api/auth/profile"
    assert raw_client.get(path).status_code == 401
    setup = raw_client.post("/api/auth/setup", json=OWNER).json()
    empty = {"display_name": "", "avatar": None, "revision": 1, "work_role": "", "specialties": [], "bio": ""}
    assert raw_client.get(path).json() == empty
    avatar = BytesIO()
    Image.new("RGB", (480, 240), "navy").save(avatar, format="JPEG")
    draft = {
        "display_name": "  值班 DBA  ",
        "avatar": "data:image/jpeg;base64," + base64.b64encode(avatar.getvalue()).decode(),
        "work_role": " Oracle DBA ",
        "specialties": ["Oracle", "oracle", " 恢复 ", " "],
        "bio": " 巡检与备份\n恢复验证 ",
    }
    assert raw_client.put(path, json=draft, headers={"If-Match": "1"}).status_code == 403
    raw_client.headers["X-CSRF-Token"] = setup["csrf_token"]
    assert raw_client.put(path, json=draft).status_code == 428
    headers = {"If-Match": '"1"'}
    assert raw_client.put(path, json={**draft, "user_id": 999}, headers=headers).status_code == 422
    assert raw_client.put(path, json={**draft, "avatar": "data:image/png;base64,AAAA"}, headers=headers).status_code == 422
    assert raw_client.put(path, json={**draft, "display_name": "超" * 41}, headers=headers).status_code == 422

    response = raw_client.put(path, json=draft, headers=headers)
    assert response.status_code == 200
    profile = response.json()
    assert profile["display_name"] == "值班 DBA"
    assert profile["revision"] == 2
    assert (profile["work_role"], profile["specialties"], profile["bio"]) == ("Oracle DBA", ["Oracle", "恢复"], "巡检与备份\n恢复验证")
    mime, payload = profile["avatar"].split(",", 1)
    assert mime == "data:image/png;base64"
    with Image.open(BytesIO(base64.b64decode(payload))) as thumbnail:
        assert thumbnail.size == (192, 192)
    assert raw_client.put(path, json=draft, headers=headers).status_code == 409

    assert raw_client.post("/api/auth/logout").status_code == 200
    login = raw_client.post("/api/auth/login", json=OWNER)
    assert login.status_code == 200
    assert login.json()["user"]["username"] == OWNER["username"]
    assert raw_client.get(path).json() == profile
    raw_client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    reset = raw_client.put(path, json={"display_name": "", "avatar": None}, headers={"If-Match": "2"})
    assert reset.json() == {**profile, "display_name": "", "avatar": None, "revision": 3}
    cleared = raw_client.put(path, json={key: value for key, value in empty.items() if key != "revision"}, headers={"If-Match": "3"})
    assert cleared.json() == {**empty, "revision": 4}


def test_desktop_login_requires_launch_token_without_setting_an_account_password(raw_client, monkeypatch) -> None:
    from backend import auth

    monkeypatch.setattr(auth, "_desktop_token", "test-only-desktop-token")
    credentials = {"X-DBA-Desktop-Token": "test-only-desktop-token"}
    assert raw_client.get("/api/auth/status").json() == {"authenticated": False, "setup_required": False}
    assert raw_client.post("/api/auth/setup", json=OWNER).status_code == 403
    assert raw_client.post("/api/auth/desktop").status_code == 401
    assert raw_client.post("/api/auth/desktop", headers={**credentials, "Origin": "https://example.test"}).status_code == 403

    login = raw_client.post("/api/auth/desktop", headers=credentials)
    assert login.status_code == 204
    assert "HttpOnly" in login.headers["set-cookie"]
    session = raw_client.get("/api/auth/status").json()
    assert session["vault_password_only"] is True
    assert session["reauthenticated_until"] is None
    assert raw_client.get("/api/dashboard/stats").status_code == 200

    headers = {"X-CSRF-Token": session["csrf_token"]}
    password = {"password": OWNER["password"]}
    assert raw_client.post("/api/auth/reauthenticate", json=password, headers=headers).status_code == 403
    assert raw_client.get("/api/vault/profile").json()["initialized"] is False


def test_desktop_login_reuses_existing_owner_without_using_the_old_password_for_vault_access(raw_client, monkeypatch) -> None:
    from backend import auth

    owner = raw_client.post("/api/auth/setup", json=OWNER).json()["user"]
    raw_client.cookies.clear()
    monkeypatch.setattr(auth, "_desktop_token", "test-only-desktop-token")
    assert raw_client.post("/api/auth/desktop", headers={"X-DBA-Desktop-Token": "test-only-desktop-token"}).status_code == 204
    session = raw_client.get("/api/auth/status").json()
    assert session["user"] == owner
    assert session["vault_password_only"] is True
    verified = raw_client.post(
        "/api/auth/reauthenticate",
        json={"password": OWNER["password"]},
        headers={"X-CSRF-Token": session["csrf_token"]},
    )
    assert verified.status_code == 403


def test_login_rotates_session_logout_revokes_and_reauthenticates(
    raw_client: TestClient,
) -> None:
    setup = raw_client.post("/api/auth/setup", json=OWNER)
    old_cookie = setup.cookies.get("dba_session")
    login = raw_client.post("/api/auth/login", json=OWNER)
    assert login.status_code == 200
    assert login.cookies.get("dba_session") != old_cookie
    csrf = login.json()["csrf_token"]

    reauth = raw_client.post(
        "/api/auth/reauthenticate",
        json={"password": OWNER["password"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert reauth.status_code == 200
    reauthenticated_until = datetime.fromisoformat(reauth.json()["reauthenticated_until"])
    remaining = reauthenticated_until - datetime.now(timezone.utc)
    assert timedelta(minutes=29, seconds=50) <= remaining <= timedelta(minutes=30, seconds=5)

    logout = raw_client.post(
        "/api/auth/logout", headers={"X-CSRF-Token": csrf}
    )
    assert logout.status_code == 200
    assert raw_client.get("/api/dashboard/stats").status_code == 401


def test_repeated_status_requests_keep_the_session_csrf_token_valid(
    raw_client: TestClient,
) -> None:
    setup = raw_client.post("/api/auth/setup", json=OWNER)
    original_csrf = setup.json()["csrf_token"]

    first_status = raw_client.get("/api/auth/status")
    second_status = raw_client.get("/api/auth/status")

    assert first_status.json()["csrf_token"] == original_csrf
    assert second_status.json()["csrf_token"] == original_csrf
    response = raw_client.post(
        "/api/auth/reauthenticate",
        json={"password": OWNER["password"]},
        headers={"X-CSRF-Token": original_csrf},
    )
    assert response.status_code == 200


def test_login_rate_limit_uses_backoff(raw_client: TestClient, monkeypatch) -> None:
    from backend import auth

    now = auth.utcnow()
    monkeypatch.setattr(auth, "utcnow", lambda: now)
    raw_client.post("/api/auth/setup", json=OWNER)
    raw_client.cookies.clear()
    for _ in range(4):
        assert raw_client.post(
            "/api/auth/login",
            json={"username": OWNER["username"], "password": "wrong-test-password"},
        ).status_code == 401
    fifth = raw_client.post(
        "/api/auth/login",
        json={"username": OWNER["username"], "password": "wrong-test-password"},
    )
    assert fifth.status_code == 401
    blocked = raw_client.post("/api/auth/login", json=OWNER)
    assert blocked.status_code == 429
    now += timedelta(seconds=1)
    assert raw_client.post("/api/auth/login", json=OWNER).status_code == 200


def test_reauthentication_is_rate_limited(raw_client: TestClient, monkeypatch) -> None:
    from backend import auth

    now = auth.utcnow()
    monkeypatch.setattr(auth, "utcnow", lambda: now)
    setup = raw_client.post("/api/auth/setup", json=OWNER)
    csrf = setup.json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf}
    for _ in range(5):
        response = raw_client.post(
            "/api/auth/reauthenticate",
            json={"password": "wrong-test-password"},
            headers=headers,
        )
        assert response.status_code == 401
    blocked = raw_client.post(
        "/api/auth/reauthenticate",
        json={"password": OWNER["password"]},
        headers=headers,
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    now += timedelta(seconds=1)
    assert raw_client.post("/api/auth/reauthenticate", json={"password": OWNER["password"]}, headers=headers).status_code == 200
