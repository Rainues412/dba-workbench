from __future__ import annotations

from pathlib import Path
import json
import os
import sys

import desktop
import file_viewer_runtime
import pytest
import uvicorn
from backend import auth
from backend import browser_launch


def test_packaged_data_directory_defaults_to_local_app_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DBA_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert desktop._data_directory() == tmp_path / "DBA Workbench" / "data"


def test_packaged_data_directory_honors_explicit_override(monkeypatch, tmp_path: Path) -> None:
    selected = tmp_path / "portable-data"
    monkeypatch.setenv("DBA_DATA_DIR", str(selected))

    assert desktop._data_directory() == selected.resolve()


def test_packaged_runtime_restores_persisted_directory_permissions(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    allowed = tmp_path / "documents"
    allowed.mkdir()
    (tmp_path / "local-capabilities.json").write_text(
        json.dumps({"allowed_roots": [str(allowed)]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("DBA_DATA_DIR", str(data_dir))
    for name in ("DBA_LOCAL_CAPABILITIES", "DBA_ALLOWED_ROOTS", "DBA_ALLOWED_LOCAL_ACTIONS"):
        monkeypatch.delenv(name, raising=False)

    desktop._configure_local_capabilities(data_dir)

    assert os.environ["DBA_LOCAL_CAPABILITIES"] == "true"
    assert os.environ["DBA_ALLOWED_ROOTS"] == str(allowed.resolve())


def test_tray_exit_stops_server_and_icon() -> None:
    class Server:
        should_exit = False

    class Icon:
        stopped = False

        def stop(self):
            self.stopped = True

    server = Server()
    icon = Icon()
    desktop._exit_from_tray(server, icon)

    assert server.should_exit is True
    assert icon.stopped is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows notification area")
def test_tray_loads_the_desktop_icon_at_small_size_and_uses_a_stable_shell_guid(monkeypatch) -> None:
    import ctypes

    from backend.windows_tray import WorkbenchTrayIcon, win32

    loads = []
    messages = []
    monkeypatch.setattr(WorkbenchTrayIcon, "_register_class", lambda self: None)
    monkeypatch.setattr(win32, "LoadImage", lambda *args: loads.append(args) or 123)
    monkeypatch.setattr(win32, "DestroyIcon", lambda _: True)
    monkeypatch.setattr(win32, "Shell_NotifyIcon", lambda action, data: messages.append((action, data.uFlags, bytes(data.guidItem))))
    path = desktop._tray_icon_path().resolve()
    icon = WorkbenchTrayIcon(path, desktop.APP_TITLE, None)
    icon.visible = True
    icon.visible = False
    icon._release_icon()
    WorkbenchTrayIcon(path, desktop.APP_TITLE, None)._hide()

    metrics = ctypes.windll.user32.GetSystemMetrics
    assert loads == [(None, str(path), win32.IMAGE_ICON, metrics(49), metrics(50), win32.LR_LOADFROMFILE)]
    assert [action for action, _, _ in messages] == [win32.NIM_ADD, win32.NIM_DELETE, win32.NIM_DELETE]
    assert all(flags & win32.NIF_GUID for _, flags, _ in messages)
    assert messages[0][2] != bytes(16)
    assert len({guid for _, _, guid in messages}) == 1


def test_desktop_bounds_shutdown_and_cleans_up_viewer(monkeypatch, tmp_path: Path) -> None:
    viewer = object()
    stopped = []
    monkeypatch.setattr(desktop, "_configure_runtime", lambda: tmp_path)
    monkeypatch.setattr(desktop, "_launch_url", desktop.URL)
    monkeypatch.setattr(auth, "enable_desktop_login", lambda: "test-only-token")
    monkeypatch.setattr(desktop, "_probe_service", lambda: "down")
    monkeypatch.setattr(desktop, "_data_directory", lambda: tmp_path)
    monkeypatch.setattr(desktop.desktop_window, "create", lambda *_: None)
    monkeypatch.setattr(desktop, "_open_browser_when_ready", lambda: None)
    monkeypatch.setattr(file_viewer_runtime, "start_file_viewer", lambda *_: viewer)
    monkeypatch.setattr(file_viewer_runtime, "stop_file_viewer", stopped.append)

    def fail_to_start_tray(server):
        assert server.config.timeout_graceful_shutdown == 10
        assert isinstance(server, uvicorn.Server)
        raise OSError("tray unavailable")

    monkeypatch.setattr(desktop, "_start_tray", fail_to_start_tray)

    with pytest.raises(RuntimeError, match="启动失败"):
        desktop.main()

    assert stopped == [viewer]


def test_configured_browser_is_used_for_source_launcher(monkeypatch, tmp_path: Path) -> None:
    browser = tmp_path / "msedge.exe"
    browser.touch()
    calls = []
    monkeypatch.setattr(desktop.desktop_window, "activate", lambda _: False)
    monkeypatch.setenv("DBA_BROWSER_PATH", str(browser))
    monkeypatch.setattr(browser_launch, "_browser_windows", lambda: {})
    monkeypatch.setattr(browser_launch, "_maximize_new_workbench", lambda existing: None)
    monkeypatch.setattr(browser_launch.subprocess, "Popen", lambda command, **kwargs: calls.append((command, kwargs)))

    desktop._open_workbench()

    assert calls[0][0] == [str(browser), "--new-window", "--start-maximized", desktop.URL]


def test_tray_reopens_existing_desktop_window(monkeypatch) -> None:
    activated = []
    monkeypatch.setattr(desktop.desktop_window, "activate", lambda port: activated.append(port) or True)
    monkeypatch.setattr(desktop, "open_workbench", lambda *_: pytest.fail("must reuse the desktop window"))

    desktop._open_workbench()

    assert activated == [desktop.PORT]


def test_runtime_honors_source_log_directory(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    log_dir = tmp_path / "source-logs"
    monkeypatch.setenv("DBA_LOG_DIR", str(log_dir))

    assert desktop._log_directory(data_dir) == log_dir.resolve()
