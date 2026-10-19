from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


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


def test_login_rate_limit_uses_backoff(raw_client: TestClient) -> None:
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


def test_reauthentication_is_rate_limited(raw_client: TestClient) -> None:
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
