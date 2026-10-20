from __future__ import annotations

import logging
import json
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
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert response.json()["error"]["message"] == "本机能力已关闭"


def test_packaged_picker_enrolls_only_the_selected_directory(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend import local_capabilities
    from backend.routers import launcher

    selected = tmp_path / "selected"
    selected.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    config_file = tmp_path / "app-data" / "local-capabilities.json"
    monkeypatch.setenv("DBA_FOLDER_ENROLLMENT", "true")
    monkeypatch.setenv("DBA_LOCAL_CAPABILITIES_FILE", str(config_file))
    monkeypatch.setattr(local_capabilities, "_enrolled_roots", set())

    class FakeRoot:
        def withdraw(self): pass
        def attributes(self, *_): pass
        def destroy(self): pass

    import tkinter
    from tkinter import filedialog
    monkeypatch.setattr(tkinter, "Tk", FakeRoot)
    monkeypatch.setattr(filedialog, "askdirectory", lambda **_: str(selected))

    picked = client.post("/api/launcher/pick-folder", json={})
    assert picked.status_code == 200
    assert picked.json()["path"] == str(selected.resolve())
    assert client.post("/api/scan/run", json={"paths": [str(selected)]}).status_code == 200
    assert client.post("/api/scan/run", json={"paths": [str(outside)]}).status_code == 403
    saved = json.loads(config_file.read_text(encoding="utf-8"))
    assert saved["allowed_roots"] == [str(selected.resolve())]
    assert "run" not in saved["allowed_actions"]


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


def test_open_edit_and_folder_use_native_apps_without_shell_interpolation(client, tmp_path, monkeypatch):
    from backend.routers import launcher

    script = tmp_path / "巡检 脚本.sql"
    script.write_text("select 1;", encoding="utf-8")
    _enable_local_capabilities(monkeypatch, tmp_path, actions="edit,folder,open")
    monkeypatch.setattr(launcher, "EDITORS", [])
    commands = []
    opened = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda command, **kwargs: commands.append((command, kwargs)))
    monkeypatch.setattr(launcher.os, "startfile", lambda path: opened.append(path))

    for mode in ["edit", "folder", "open"]:
        response = client.post("/api/launcher/path", json={"path": str(script), "mode": mode})
        assert response.status_code == 200, response.text
    assert commands[0][0] == ["notepad.exe", str(script.resolve())]
    assert commands[1][0] == ["explorer", "/select,", str(script.resolve())]
    assert all(not options.get("shell") for _, options in commands)
    assert opened == [str(script.resolve())]
    assert client.post("/api/launcher/path", json={"path": str(script), "mode": "run"}).status_code == 403


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
    from backend.local_capabilities import audit_logger

    audit_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="dba.audit"):
            response = client.post("/api/launcher/check", json={"path": str(target)})
    finally:
        audit_logger.removeHandler(caplog.handler)

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
