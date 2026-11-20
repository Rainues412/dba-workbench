"""Opt-in smoke test against the actual Windows WebView2 window and tray."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback

import pytest


@pytest.mark.skipif(sys.platform != "win32" or os.environ.get("DBA_TEST_NATIVE_DESKTOP") != "1", reason="Opt-in Windows desktop smoke test")
def test_native_silent_start_reopen_hide_and_exit(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "DBA_PORT": str(port), "DBA_DATA_DIR": str(tmp_path / "data"),
           "DBA_LOG_DIR": str(tmp_path / "logs"), "DBA_WEBVIEW_PROFILE": str(tmp_path / "webview"),
           "DBA_DESKTOP_SETTINGS_FILE": str(tmp_path / "desktop-settings.json"), "DBA_FILE_VIEWER_DISABLED": "true"}
    # A separate icon path gives this test its own Shell identity.
    root = Path(__file__).resolve().parents[2]
    shutil.copyfile(root / "assets/dba-workbench-icon.ico", tmp_path / "test-icon.ico")
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(tmp_path)], cwd=root / "server", env=env, timeout=50, capture_output=True, text=True)
    report = tmp_path / "native-result.json"
    assert report.is_file(), f"No native report: {completed.stderr[-1500:]}"
    result = json.loads(report.read_text(encoding="utf-8"))
    assert completed.returncode == 0 and result.get("ok"), result


def _run_smoke(directory: Path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import ctypes
    from ctypes import wintypes

    import desktop
    import httpx

    from backend import auth

    class IsolatedStartup:
        def __init__(self, name, command):
            self.command = subprocess.list2cmdline(command)

        def read(self):
            return self.command

    desktop.WindowsStartup = IsolatedStartup
    desktop._tray_icon_path = lambda: directory / "test-icon.ico"
    Path(os.environ["DBA_DESKTOP_SETTINGS_FILE"]).write_text(json.dumps({"silent_start": True, "close_to_tray": True}), encoding="utf-8")
    result = {"ok": False}
    window_holder = []
    original_create = desktop.desktop_window.create

    def create(*args):
        window = original_create(*args)
        assert window is not None, "WebView2 unavailable"
        window_holder.append(window)
        worker.start()
        return window

    desktop.desktop_window.create = create

    def verify():
        window = None
        try:
            deadline = time.monotonic() + 25
            while not window_holder or not window_holder[0].events.loaded.wait(.1):
                assert time.monotonic() < deadline, "Native window initialization timed out"
            window = window_holder[0]
            while desktop._probe_service() != "dba":
                assert time.monotonic() < deadline, "Server startup timed out"
                time.sleep(.05)
            hwnd = window.native.Handle.ToInt64()
            user32 = ctypes.windll.user32
            user32.IsWindowVisible.argtypes = [wintypes.HWND]

            def wait_visible(expected):
                limit = time.monotonic() + 5
                while bool(user32.IsWindowVisible(hwnd)) != expected:
                    assert time.monotonic() < limit, f"Window visibility did not become {expected}"
                    time.sleep(.05)

            time.sleep(.5)
            wait_visible(False)
            result["silent_hidden"] = True
            assert desktop.desktop_window.activate(desktop.PORT)
            wait_visible(True)
            result["activated"] = True
            window.destroy()
            wait_visible(False)
            assert desktop._probe_service() == "dba"
            result["close_keeps_server"] = True
            assert desktop.desktop_window.activate(desktop.PORT)
            wait_visible(True)
            with httpx.Client(base_url=desktop.URL, timeout=5) as client:
                client.post("api/auth/desktop", headers={"X-DBA-Desktop-Token": auth._desktop_token}).raise_for_status()
                csrf = client.get("api/auth/status").json()["csrf_token"]
                state = client.get("api/desktop/settings").json()
                response = client.put("api/desktop/settings", headers={"If-Match": str(state["revision"]), "X-CSRF-Token": csrf}, json={"close_to_tray": False})
                response.raise_for_status()
                assert response.json()["close_to_tray"] is False
            window.destroy()
            result["close_event"] = window.events.closed.wait(5)
            assert result["close_event"], "Close-to-exit did not close the native window"
            result["ok"] = True
        except Exception:
            result["error"] = traceback.format_exc()
            # Ensure a failing smoke test cannot leave a hidden background server.
            import main
            if getattr(main.app.state, "desktop_settings", None):
                main.app.state.desktop_settings.options = lambda: {"silent_start": False, "close_to_tray": False}
            if window is not None:
                window.destroy()
        finally:
            (directory / "native-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    worker = threading.Thread(target=verify, daemon=True)
    desktop.main()
    worker.join(timeout=5)
    assert desktop._probe_service() == "down", "Service remained alive after closing the window"
    assert result["ok"], result


if __name__ == "__main__":
    _run_smoke(Path(sys.argv[1]))
