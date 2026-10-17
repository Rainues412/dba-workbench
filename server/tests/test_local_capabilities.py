from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

import pytest

from backend.config import Settings


def _enable_local_capabilities(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    *,
    actions: str = "check,edit,folder,open,pick-folder,scan",
    extensions: str = "",
) -> Settings:
    from backend import local_capabilities
    from backend.routers import launcher

    environment = {
        "DBA_LOCAL_CAPABILITIES": "true",
        "DBA_ALLOWED_ROOTS": str(root),
        "DBA_ALLOWED_LOCAL_ACTIONS": actions,
        "DBA_ALLOWED_RUN_EXTENSIONS": extensions,
    }
    configured = Settings.from_env(environment)
    monkeypatch.setattr(local_capabilities, "settings", configured)
    monkeypatch.setattr(launcher, "settings", configured)
    return configured


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/launcher/path", {"path": r"D:\blocked.txt"}),
        ("post", "/api/launcher/check", {"path": r"D:\blocked.txt"}),
        ("post", "/api/launcher/pick-folder", {}),
        ("get", "/api/scan/dirs", None),
        ("post", "/api/scan/run", {}),
        ("post", "/api/scan/commit", {"items": []}),
    ],
)
def test_local_capabilities_are_closed_by_default(
    client, method: str, path: str, payload: Optional[dict]
) -> None:
    response = client.request(method, path, json=payload)
    assert response.status_code == 403
    assert response.json()["detail"] == "本机能力已关闭"


def test_allowed_root_rejects_outside_traversal_and_unc(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    inside = allowed / "inside.txt"
    inside.write_text("safe", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("blocked", encoding="utf-8")
    _enable_local_capabilities(monkeypatch, allowed)

    assert client.post("/api/launcher/check", json={"path": str(inside)}).status_code == 200
    assert client.post("/api/launcher/check", json={"path": str(outside)}).status_code == 403
    assert (
        client.post(
            "/api/launcher/check",
            json={"path": str(allowed / ".." / "outside.txt")},
        ).status_code
        == 403
    )
    assert client.post(
        "/api/launcher/check", json={"path": r"\\server\share\secret.txt"}
    ).status_code == 403


def test_symlink_cannot_escape_allowed_root(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("blocked", encoding="utf-8")
    link = allowed / "linked-directory"
    created = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)],
        capture_output=True,
        check=False,
    )
    if created.returncode != 0:
        pytest.fail("failed to create a temporary directory junction")
    _enable_local_capabilities(monkeypatch, allowed)

    try:
        response = client.post(
            "/api/launcher/check", json={"path": str(link / "secret.txt")}
        )
        assert response.status_code == 403
    finally:
        os.rmdir(link)


def test_run_requires_action_and_extension_allowlists(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.routers import launcher

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    python_file = allowed / "safe.py"
    python_file.write_text("print('safe')", encoding="utf-8")
    text_file = allowed / "unsafe.txt"
    text_file.write_text("not executable", encoding="utf-8")
    _enable_local_capabilities(
        monkeypatch,
        allowed,
        actions="check,run",
        extensions=".py,.ps1",
    )
    launched = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda args, **kwargs: launched.append(args))

    denied = client.post(
        "/api/launcher/path", json={"path": str(text_file), "mode": "run"}
    )
    assert denied.status_code == 403

    allowed_response = client.post(
        "/api/launcher/path", json={"path": str(python_file), "mode": "run"}
    )
    assert allowed_response.status_code == 200
    assert launched and launched[0][1] == str(python_file.resolve())


def test_powershell_run_does_not_bypass_execution_policy(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.routers import launcher

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    script = allowed / "safe.ps1"
    script.write_text("Write-Output safe", encoding="utf-8")
    _enable_local_capabilities(
        monkeypatch,
        allowed,
        actions="run",
        extensions=".ps1",
    )
    launched = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda args, **kwargs: launched.append(args))

    response = client.post(
        "/api/launcher/path", json={"path": str(script), "mode": "run"}
    )
    assert response.status_code == 200
    command = [str(part).lower() for part in launched[0]]
    assert "-executionpolicy" not in command
    assert "bypass" not in command


def test_scan_revalidates_paths_and_file_kind(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    script = allowed / "safe.sql"
    script.write_text("select 1;", encoding="utf-8")
    outside = tmp_path / "outside.sql"
    outside.write_text("select secret;", encoding="utf-8")
    _enable_local_capabilities(monkeypatch, allowed)

    outside_response = client.post(
        "/api/scan/commit",
        json={"items": [{"kind": "script", "name": "outside", "path": str(outside)}]},
    )
    assert outside_response.status_code == 403

    forged_kind = client.post(
        "/api/scan/commit",
        json={"items": [{"kind": "article", "name": "forged", "path": str(script)}]},
    )
    assert forged_kind.status_code == 400

    accepted = client.post(
        "/api/scan/commit",
        json={"items": [{"kind": "script", "name": "safe", "path": str(script)}]},
    )
    assert accepted.status_code == 200
    assert accepted.json()["imported"]["script"] == 1


def test_local_actions_emit_non_secret_audit_events(
    client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "secret-name.txt"
    target.write_text("secret-content", encoding="utf-8")
    _enable_local_capabilities(monkeypatch, allowed)

    with caplog.at_level(logging.INFO, logger="dba.audit"):
        response = client.post("/api/launcher/check", json={"path": str(target)})

    assert response.status_code == 200
    audit_text = " ".join(record.getMessage() for record in caplog.records)
    assert "action=check" in audit_text
    assert "result=success" in audit_text
    assert "secret-name" not in audit_text
    assert "secret-content" not in audit_text


def test_local_capability_configuration_is_explicit(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError, match="DBA_ALLOWED_ROOTS"):
        Settings.from_env({"DBA_LOCAL_CAPABILITIES": "true"})
    with pytest.raises(ValueError, match="non-local or relative"):
        Settings.from_env({"DBA_ALLOWED_ROOTS": "relative-folder"})
    with pytest.raises(ValueError, match="non-local or relative"):
        Settings.from_env({"DBA_ALLOWED_ROOTS": r"\\server\share"})
    with pytest.raises(ValueError, match="DBA_ALLOWED_RUN_EXTENSIONS"):
        Settings.from_env(
            {
                "DBA_LOCAL_CAPABILITIES": "true",
                "DBA_ALLOWED_ROOTS": str(root),
                "DBA_ALLOWED_LOCAL_ACTIONS": "run",
            }
        )
