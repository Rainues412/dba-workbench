from __future__ import annotations

from pathlib import Path
import json
import os

import desktop


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


def test_configured_browser_is_used_for_source_launcher(monkeypatch, tmp_path: Path) -> None:
    browser = tmp_path / "msedge.exe"
    browser.touch()
    calls = []
    monkeypatch.setenv("DBA_BROWSER_PATH", str(browser))
    monkeypatch.setattr(desktop.subprocess, "Popen", lambda command, **kwargs: calls.append((command, kwargs)))

    desktop._open_workbench()

    assert calls[0][0] == [str(browser), "--new-window", desktop.URL]


def test_runtime_honors_source_log_directory(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    log_dir = tmp_path / "source-logs"
    monkeypatch.setenv("DBA_LOG_DIR", str(log_dir))

    assert desktop._log_directory(data_dir) == log_dir.resolve()
