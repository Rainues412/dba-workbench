from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import sys
from uuid import uuid4

import pytest
from fastapi import HTTPException

import desktop
from backend import desktop_settings
from backend.desktop_settings import DesktopSettings, startup_command


class FakeStartup:
    command = '"D:\\DBA 工作台\\DBA工作台.exe" --on-logon'
    value = None

    def read(self):
        return self.value

    def write(self, value):
        self.value = value


@pytest.fixture
def preferences(tmp_path):
    value = DesktopSettings(tmp_path / "desktop-settings.json", FakeStartup())
    value.native_window = True
    return value


def test_persistence_and_startup_readback(preferences):
    initial = preferences.read()
    assert not initial["auto_start"] and not initial["silent_start"] and initial["close_to_tray"]
    enabled = preferences.update({"auto_start": True}, initial["revision"])
    assert preferences.startup.read() == preferences.startup.command
    silent = preferences.update({"silent_start": True, "close_to_tray": False}, enabled["revision"])
    assert silent["silent_start"] and not silent["close_to_tray"]
    restored = DesktopSettings(preferences.path, preferences.startup).read()
    assert restored["auto_start"] and restored["silent_start"] and not restored["close_to_tray"]
    disabled = preferences.update({"auto_start": False}, silent["revision"])
    assert not disabled["silent_start"] and not disabled["auto_start"]
    assert preferences.startup.read() is None


def test_stale_writes_conflicts_and_silent_dependency(preferences):
    initial = preferences.read()
    with pytest.raises(HTTPException, match="先开启开机启动"):
        preferences.update({"silent_start": True}, initial["revision"])
    changed = preferences.update({"close_to_tray": False}, initial["revision"])
    with pytest.raises(HTTPException, match="设置已发生变化"):
        preferences.update({"auto_start": True}, initial["revision"])
    preferences.startup.value = "another-executable.exe"
    conflict = preferences.read()
    assert conflict["startup_conflict"] and conflict["revision"] != changed["revision"]
    with pytest.raises(HTTPException, match="指向其他位置"):
        preferences.update({"auto_start": False}, conflict["revision"])
    assert preferences.startup.value == "another-executable.exe"


def test_failed_file_save_rolls_back_startup_registration(preferences, monkeypatch):
    initial = preferences.read()
    monkeypatch.setattr(desktop_settings.os, "replace", Mock(side_effect=PermissionError("test-only denied")))
    with pytest.raises(PermissionError):
        preferences.update({"auto_start": True}, initial["revision"])
    assert preferences.startup.read() is None
    assert not preferences.path.exists()
    assert not preferences.path.with_suffix(".tmp").exists()


def test_source_and_installed_startup_are_distinct_and_quote_paths(tmp_path):
    source = tmp_path / "源 码" / "server" / "desktop.py"
    interpreter = tmp_path / "Python 环境" / "python.exe"
    interpreter.parent.mkdir()
    interpreter.with_name("pythonw.exe").touch()
    name, command = startup_command(source, interpreter, compiled=False, host="D:\\启动 宿主.exe")
    assert name.startswith("DBAWorkbench.Source.")
    assert command == [str(interpreter.with_name("pythonw.exe")), str(source.parents[1] / "tools/windows/launch_dba_workbench.py"), "--desktop-host", "D:\\启动 宿主.exe", "--on-logon"]
    installed_name, installed = startup_command(source, interpreter, compiled=True)
    assert installed_name == "DBAWorkbench" and installed == [str(interpreter.resolve()), "--on-logon"]


@pytest.mark.parametrize("silent", [False, True])
def test_window_loads_while_silent_and_can_be_reopened(silent, monkeypatch):
    window = SimpleNamespace(load_url=Mock(), show=Mock(), maximize=Mock())
    desktop._show_window_when_ready(SimpleNamespace(started=True, should_exit=False), window, silent)
    window.load_url.assert_called_once()
    assert window.show.call_count == window.maximize.call_count == (0 if silent else 1)
    monkeypatch.setattr(desktop.desktop_window, "activate", Mock(return_value=True))
    monkeypatch.setattr(desktop, "open_workbench", Mock())
    desktop._open_workbench()
    desktop.desktop_window.activate.assert_called_once_with(desktop.PORT)
    desktop.open_workbench.assert_not_called()


def test_settings_api_auth_csrf_revision_validation_and_errors(client, isolated_app, preferences, monkeypatch):
    app, _ = isolated_app
    monkeypatch.setattr(app.state, "desktop_settings", preferences, raising=False)
    initial = client.get("/api/desktop/settings").json()
    assert client.put("/api/desktop/settings", json={"auto_start": True}).status_code == 428
    response = client.put("/api/desktop/settings", headers={"If-Match": str(initial["revision"])}, json={"auto_start": True})
    assert response.status_code == 200 and response.json()["auto_start"]
    assert client.put("/api/desktop/settings", headers={"If-Match": str(initial["revision"])}, json={"silent_start": True}).status_code == 409
    for payload in ({"auto_start": "false"}, {"silent_start": None}, {"command": "arbitrary.exe"}):
        assert client.put("/api/desktop/settings", headers={"If-Match": str(response.json()["revision"])}, json=payload).status_code == 422
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.put("/api/desktop/settings", json={"auto_start": False}).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    monkeypatch.setattr(preferences.startup, "read", Mock(side_effect=PermissionError("test-only denied")))
    assert client.get("/api/desktop/settings").status_code == 503
    client.cookies.clear()
    assert client.get("/api/desktop/settings").status_code == 401


def test_settings_api_is_unavailable_outside_desktop(client):
    assert client.get("/api/desktop/settings").status_code == 404


def test_browser_fallback_cannot_change_window_close(preferences):
    preferences.native_window = False
    with pytest.raises(HTTPException, match="桌面窗口"):
        preferences.update({"close_to_tray": False}, preferences.read()["revision"])


def test_corrupt_settings_preserve_the_close_to_tray_default(preferences):
    preferences.path.write_text("broken json", encoding="utf-8")
    assert preferences.close_to_tray()
    with pytest.raises(ValueError):
        preferences.read()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry")
def test_windows_registration_round_trip_uses_an_isolated_registry_key(monkeypatch):
    import winreg

    key = rf"Software\DBAWorkbench-Settings-Test-{uuid4().hex}"
    monkeypatch.setattr(desktop_settings, "RUN_KEY", key)
    startup = desktop_settings.WindowsStartup("test-only", [r"D:\路径 含空格\app.exe", "--on-logon"])
    try:
        assert startup.read() is None
        startup.write(startup.command)
        assert startup.read() == startup.command
        startup.write(None)
        assert startup.read() is None
    finally:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
