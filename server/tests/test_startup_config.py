from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings


def test_local_settings_are_safe_by_default() -> None:
    settings = Settings.from_env({})

    assert settings.mode == "local"
    assert settings.host == "127.0.0.1"
    assert settings.reload is False
    assert "*" not in settings.allowed_hosts
    assert "*" not in settings.cors_origins


def test_development_reload_requires_explicit_mode() -> None:
    development = Settings.from_env({"DBA_MODE": "development"})
    assert development.host == "127.0.0.1"
    assert development.reload is True

    with pytest.raises(ValueError, match="only allowed in development"):
        Settings.from_env({"DBA_RELOAD": "true"})


@pytest.mark.parametrize(
    "environment",
    [
        {"DBA_MODE": "lan"},
        {"DBA_HOST": "0.0.0.0"},
        {"DBA_ALLOWED_HOSTS": "*"},
        {"DBA_CORS_ORIGINS": "*"},
    ],
)
def test_unsafe_network_settings_are_rejected(environment: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        Settings.from_env(environment)


def test_lifespan_initializes_a_fresh_database(isolated_app) -> None:
    app, test_db = isolated_app
    assert not Path(test_db).exists()

    with TestClient(app, base_url="http://localhost") as test_client:
        assert test_client.get("/api/auth/status").status_code == 200
        assert test_client.get("/api/dashboard/stats").status_code == 401

    assert Path(test_db).exists()


def test_lifespan_rejects_a_newer_database_schema(isolated_app) -> None:
    app, test_db = isolated_app
    with sqlite3.connect(test_db) as conn:
        conn.execute("PRAGMA user_version = 999")

    with pytest.raises(RuntimeError, match="newer than supported"):
        with TestClient(app, base_url="http://localhost"):
            pass


def test_trusted_host_and_cors_allowlists(client: TestClient) -> None:
    rejected = client.get("/", headers={"host": "attacker.example"})
    assert rejected.status_code == 400

    allowed_preflight = client.options(
        "/api/tasks/",
        headers={
            "origin": "http://localhost:8686",
            "access-control-request-method": "POST",
            "access-control-request-headers": "content-type",
        },
    )
    assert allowed_preflight.status_code == 200
    assert (
        allowed_preflight.headers["access-control-allow-origin"]
        == "http://localhost:8686"
    )

    rejected_preflight = client.options(
        "/api/tasks/",
        headers={
            "origin": "http://attacker.example",
            "access-control-request-method": "POST",
        },
    )
    assert rejected_preflight.status_code == 400
