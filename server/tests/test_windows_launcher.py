from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture()
def launcher(tmp_path):
    source = Path(__file__).resolve().parents[2] / "tools/windows/launch_dba_workbench.py"
    spec = importlib.util.spec_from_file_location("workbench_launcher", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.LOCAL_CONFIG = tmp_path / "local-capabilities.json"
    return module


@pytest.mark.parametrize("has_venv", [True, False])
def test_server_uses_checkout_environment(launcher, tmp_path, monkeypatch, has_venv):
    venv_python = tmp_path / "python.exe"
    if has_venv:
        venv_python.touch()
    monkeypatch.setattr(launcher, "VENV_PYTHON", venv_python)
    monkeypatch.setattr(launcher, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(launcher, "LOG_PATH", tmp_path / "logs/server.log")
    monkeypatch.setattr(launcher.time, "sleep", lambda _: None)
    monkeypatch.setattr(launcher, "probe_service", lambda: "dba")
    calls = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda command, **kwargs: calls.append((command, kwargs)))

    assert launcher.start_server()
    command, options = calls[0]
    assert command == [str(venv_python) if has_venv else launcher.sys.executable, "desktop.py"]
    assert options["cwd"] == launcher.SERVER_DIR
    assert options["env"]["DBA_HOST"] == "127.0.0.1"
    assert options["env"]["DBA_OPEN_BROWSER"] == "false"
    assert options["env"]["DBA_DATA_DIR"] == str(launcher.SERVER_DIR)
    assert options["env"]["DBA_LOG_DIR"] == str(launcher.LOG_DIR)
    assert launcher.LOG_PATH.is_file()


def test_local_opening_configuration_is_scoped_and_does_not_enable_execution(launcher, tmp_path, monkeypatch):
    import json
    import os

    launcher.LOCAL_CONFIG.write_text(json.dumps({"allowed_roots": [str(tmp_path)]}), encoding="utf-8")
    monkeypatch.setattr(launcher, "LOG_DIR", tmp_path)
    monkeypatch.setattr(launcher, "LOG_PATH", tmp_path / "server.log")
    monkeypatch.setattr(launcher.time, "sleep", lambda _: None)
    monkeypatch.setattr(launcher, "probe_service", lambda: "dba")
    for key in ["DBA_LOCAL_CAPABILITIES", "DBA_ALLOWED_ROOTS", "DBA_ALLOWED_LOCAL_ACTIONS"]:
        monkeypatch.delenv(key, raising=False)
    launched = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda command, **kwargs: launched.append(kwargs))

    assert launcher.start_server()
    environment = launched[0]["env"]
    assert environment["DBA_LOCAL_CAPABILITIES"] == "true"
    assert environment["DBA_ALLOWED_ROOTS"].split(os.pathsep) == [str(tmp_path)]
    assert environment["DBA_ALLOWED_LOCAL_ACTIONS"] == "edit,folder,open"


def test_empty_local_opening_configuration_is_rejected(launcher):
    launcher.LOCAL_CONFIG.write_text('{"allowed_roots": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="allowed_roots"):
        launcher.start_server()


def test_explicit_scan_permission_stays_scoped_to_roots(launcher, tmp_path, monkeypatch):
    import json

    launcher.LOCAL_CONFIG.write_text(json.dumps({"allowed_roots": [str(tmp_path)], "allowed_actions": ["edit", "folder", "open", "scan", "pick-folder"]}), encoding="utf-8")
    monkeypatch.setattr(launcher, "LOG_DIR", tmp_path)
    monkeypatch.setattr(launcher, "LOG_PATH", tmp_path / "server.log")
    monkeypatch.setattr(launcher.time, "sleep", lambda _: None)
    monkeypatch.setattr(launcher, "probe_service", lambda: "dba")
    for key in ["DBA_LOCAL_CAPABILITIES", "DBA_ALLOWED_ROOTS", "DBA_ALLOWED_LOCAL_ACTIONS"]:
        monkeypatch.delenv(key, raising=False)
    calls = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *args, **kwargs: calls.append(kwargs))
    assert launcher.start_server()
    assert calls[0]["env"]["DBA_ALLOWED_ROOTS"] == str(tmp_path)
    assert calls[0]["env"]["DBA_ALLOWED_LOCAL_ACTIONS"] == "edit,folder,open,scan,pick-folder"


@pytest.mark.parametrize("actions", [["run"], "scan", [], [None]])
def test_local_configuration_never_enables_run(launcher, actions):
    import json

    launcher.LOCAL_CONFIG.write_text(json.dumps({"allowed_roots": ["D:\\Database"], "allowed_actions": actions}), encoding="utf-8")
    with pytest.raises(ValueError, match="allowed_actions"):
        launcher.start_server()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Edge launcher")
def test_running_service_is_reused_and_opened_in_edge(launcher, tmp_path, monkeypatch):
    edge = tmp_path / "msedge.exe"
    edge.touch()
    monkeypatch.setattr(launcher, "EDGE_PATH", edge)
    monkeypatch.setattr(launcher, "probe_service", lambda: "dba")
    monkeypatch.setattr(launcher, "start_server", lambda: pytest.fail("must reuse the running service"))
    calls = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda command, **kwargs: calls.append(command))

    launcher.main()
    assert calls == [[str(edge), "--new-window", launcher.URL]]


def test_new_server_owns_browser_and_tray_lifecycle(launcher, monkeypatch):
    monkeypatch.setattr(launcher, "probe_service", lambda: "down")
    monkeypatch.setattr(launcher, "start_server", lambda: True)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("launcher must not open a second browser"))
    monkeypatch.setattr(launcher.webbrowser, "open", lambda *args, **kwargs: pytest.fail("launcher must not open a second browser"))

    launcher.main()


def test_server_waits_for_http_readiness_after_port_opens(launcher, tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "LOG_DIR", tmp_path)
    monkeypatch.setattr(launcher, "LOG_PATH", tmp_path / "server.log")
    monkeypatch.setattr(launcher.time, "sleep", lambda _: None)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *args, **kwargs: None)
    states = iter(["other", "dba"])
    monkeypatch.setattr(launcher, "probe_service", lambda: next(states))

    assert launcher.start_server()


def test_missing_edge_uses_default_browser(launcher, tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "EDGE_PATH", tmp_path / "missing-edge.exe")
    monkeypatch.setattr(launcher, "probe_service", lambda: "dba")
    calls = []
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url, **kwargs: calls.append(url) or True)

    launcher.main()
    assert calls == [launcher.URL]


def test_edge_discovery_accepts_portable_environment_override(launcher, tmp_path, monkeypatch):
    edge = tmp_path / "msedge.exe"
    edge.touch()
    monkeypatch.setenv("DBA_EDGE_PATH", str(edge))
    assert launcher.find_edge() == edge


def test_foreign_service_is_not_opened(launcher, monkeypatch):
    monkeypatch.setattr(launcher, "probe_service", lambda: "other")
    monkeypatch.setattr(launcher.webbrowser, "open", lambda *args, **kwargs: pytest.fail("must not open a foreign service"))

    with pytest.raises(SystemExit, match="已被其他程序占用"):
        launcher.main()
