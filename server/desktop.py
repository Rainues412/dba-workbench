"""Windows desktop entry point used by the compiled distribution."""
from __future__ import annotations

import os
import json
import logging
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import Future
from pathlib import Path

from backend import desktop_window
from backend.browser_launch import find_edge, open_workbench
from backend.desktop_settings import DesktopSettings, WindowsStartup, startup_command

APP_TITLE = "DBA 工作台"
HOST = "127.0.0.1"
PORT = int(os.environ.get("DBA_PORT", "8686"))
URL = f"http://{HOST}:{PORT}/"
_launch_url = URL


def _data_directory() -> Path:
    configured = os.environ.get("DBA_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        raise RuntimeError("无法确定当前用户的本地应用数据目录。")
    return Path(local_app_data) / "DBA Workbench" / "data"


def _configure_local_capabilities(data_dir: Path) -> None:
    capability_file = data_dir.parent / "local-capabilities.json"
    os.environ.setdefault("DBA_LOCAL_CAPABILITIES_FILE", str(capability_file))
    os.environ.setdefault("DBA_FOLDER_ENROLLMENT", "true")
    if not capability_file.is_file() or "DBA_ALLOWED_ROOTS" in os.environ:
        return
    try:
        config = json.loads(capability_file.read_text(encoding="utf-8"))
        roots = [
            str(Path(root).resolve())
            for root in config.get("allowed_roots", [])
            if isinstance(root, str)
            and Path(root).is_absolute()
            and not root.startswith(("\\\\", "//"))
            and Path(root).is_dir()
        ]
        if roots:
            os.environ["DBA_LOCAL_CAPABILITIES"] = "true"
            os.environ["DBA_ALLOWED_ROOTS"] = os.pathsep.join(roots)
            os.environ["DBA_ALLOWED_LOCAL_ACTIONS"] = "edit,folder,open,pick-folder,scan"
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass


def _log_directory(data_dir: Path) -> Path:
    configured_log_dir = os.environ.get("DBA_LOG_DIR", "").strip()
    return Path(configured_log_dir).expanduser().resolve() if configured_log_dir else data_dir.parent / "logs"


def _configure_runtime() -> Path:
    data_dir = _data_directory()
    log_dir = _log_directory(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DBA_DATA_DIR", str(data_dir))
    os.environ.setdefault("DBA_MODE", "local")
    os.environ.setdefault("DBA_HOST", HOST)
    os.environ.setdefault("DBA_PORT", str(PORT))
    os.environ.setdefault("DBA_OPEN_BROWSER", "false")
    viewer_port = int(os.environ.get("DBA_FILE_VIEWER_PORT", "8012"))
    if not 1 <= viewer_port <= 65535:
        raise RuntimeError("DBA_FILE_VIEWER_PORT 必须是 1 到 65535 之间的端口。")
    os.environ["DBA_FILE_VIEWER_URL"] = f"http://127.0.0.1:{viewer_port}"
    os.environ["DBA_FILE_VIEWER_KEY"] = secrets.token_urlsafe(32)
    _configure_local_capabilities(data_dir)

    log = (log_dir / "server.log").open("a", encoding="utf-8", buffering=1)
    sys.stdout = log
    sys.stderr = log
    return log_dir


def _probe_service() -> str:
    try:
        with urllib.request.urlopen(URL, timeout=1.0) as response:
            body = response.read(4096).decode("utf-8", errors="ignore")
            return "dba" if APP_TITLE in body else "other"
    except (urllib.error.URLError, TimeoutError, OSError):
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                return "other"
        except OSError:
            return "down"


def _open_workbench() -> None:
    if desktop_window.activate(PORT):
        return
    browser_path = os.environ.get("DBA_BROWSER_PATH", "").strip().strip('"')
    browser = Path(browser_path) if browser_path and Path(browser_path).is_file() else find_edge()
    open_workbench(_launch_url, browser)


def _open_browser_when_ready() -> None:
    for _ in range(80):
        if _probe_service() == "dba":
            _open_workbench()
            return
        time.sleep(0.25)


def _show_window_when_ready(server, window, silent_start: bool = False) -> None:
    while not server.should_exit:
        if server.started:
            window.load_url(_launch_url)
            if not silent_start:
                window.show()
                window.maximize()
            return
        time.sleep(0.05)


def _run_webview(server, window, silent_start: bool = False) -> None:
    import webview

    result: Future[None] = Future()

    def serve():
        try:
            if not window.events.loaded.wait(15):
                raise RuntimeError("WebView2 初始化超时。")
            _start_tray(server)
            threading.Thread(target=_show_window_when_ready, args=(server, window, silent_start), daemon=True).start()
            server.run()
        except Exception as error:
            result.set_exception(error)
        else:
            result.set_result(None)
        finally:
            server.should_exit = True
            window.destroy()

    profile = os.environ.get("DBA_WEBVIEW_PROFILE") or str(_data_directory() / "webview")
    webview.start(serve, gui="edgechromium", private_mode=False, storage_path=profile)
    server.should_exit = True
    result.result(timeout=20)


def _run_tauri(server, executable: Path, preferences: DesktopSettings, silent_start: bool) -> None:
    from backend.windows_process_job import ProcessJob

    data_dir = _data_directory()
    env = os.environ | {
        "DBA_TAURI_DATA_DIR": str(data_dir),
        "DBA_TAURI_PORT": str(PORT),
        "DBA_TAURI_DESKTOP_TOKEN": _launch_url.partition("#desktop=")[2],
        "DBA_TAURI_WEBVIEW": os.environ.get("DBA_WEBVIEW_PROFILE") or str(data_dir / "webview"),
        "DBA_TAURI_DESKTOP_SETTINGS": str(preferences.path),
        "DBA_TAURI_SILENT": str(int(silent_start)),
    }
    worker = threading.Thread(target=server.run, name="dba-http", daemon=True)
    worker.start()
    process = job = None
    try:
        deadline = time.monotonic() + 20
        while worker.is_alive() and not server.started and time.monotonic() < deadline:
            worker.join(0.05)
        if not server.started:
            raise RuntimeError("本机服务启动失败。")
        try:
            job = ProcessJob()
            process = subprocess.Popen(
                [str(executable)], env=env, creationflags=subprocess.CREATE_NO_WINDOW,
                stdin=subprocess.DEVNULL, stdout=sys.stdout, stderr=sys.stderr,
            )
            job.assign(process.pid)
            while worker.is_alive() and process.poll() is None:
                worker.join(0.1)
            if not worker.is_alive() or process.returncode == 0:
                return
            raise OSError(f"Tauri 宿主退出，代码 {process.returncode}")
        except OSError:
            logging.exception("无法运行 Tauri 窗口，使用系统托盘与浏览器。")
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            preferences.native_window = False
            _start_tray(server)
            if not silent_start:
                threading.Thread(target=_open_browser_when_ready, daemon=True).start()
            worker.join()
    finally:
        if job is not None:
            job.close()
        server.should_exit = True
        worker.join(timeout=15)


def _show_error(message: str) -> None:
    if os.name == "nt":
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, APP_TITLE, 0x10)
    else:
        print(message, file=sys.stderr)


def _tray_icon_path() -> Path:
    source = Path(__file__).resolve()
    candidates = (
        source.parent / "assets" / "dba-workbench-icon.ico",
        source.parents[1] / "assets" / "dba-workbench-icon.ico",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("未找到系统托盘图标。")


def _exit_from_tray(server, icon) -> None:
    server.should_exit = True
    icon.stop()


def _run_tray(server, ready: Future[None]) -> None:
    import pystray

    menu = pystray.Menu(
        pystray.MenuItem("打开工作台", lambda *_: _open_workbench(), default=True),
        pystray.MenuItem("退出", lambda tray, _: _exit_from_tray(server, tray)),
    )
    if sys.platform == "win32":
        from backend.windows_tray import WorkbenchTrayIcon

        icon = WorkbenchTrayIcon(_tray_icon_path(), APP_TITLE, menu)
    else:
        from PIL import Image

        with Image.open(_tray_icon_path()) as source:
            icon = pystray.Icon("dba-workbench", source.copy(), APP_TITLE, menu)
    def setup(tray):
        try:
            tray.visible = True
        except Exception as error:
            ready.set_exception(error)
            tray.stop()
        else:
            ready.set_result(None)

    icon.run(setup=setup)


def _start_tray(server) -> threading.Thread:
    ready: Future[None] = Future()

    def run():
        try:
            _run_tray(server, ready)
        except Exception as error:
            if not ready.done():
                ready.set_exception(error)

    thread = threading.Thread(target=run, name="system-tray", daemon=True)
    thread.start()
    ready.result(timeout=10)
    return thread


def main() -> None:
    global _launch_url
    log_dir = _configure_runtime()
    state = _probe_service()
    if state == "dba":
        if "--on-logon" not in sys.argv and os.environ.get("DBA_ON_LOGON") != "true":
            _open_workbench()
        return
    if state == "other":
        raise RuntimeError(f"端口 {PORT} 已被其他程序占用。")

    import uvicorn
    from backend.auth import enable_desktop_login
    from file_viewer_runtime import start_file_viewer, stop_file_viewer
    from main import app

    compiled = "__compiled__" in globals()
    name, command = startup_command(
        Path(__file__), Path(sys.executable), compiled=compiled,
        host=os.environ.get("DBA_SOURCE_DESKTOP_HOST", ""),
    )
    default_preferences = _data_directory() / "desktop-settings.json" if compiled else Path(__file__).resolve().parents[1] / ".runtime" / "desktop-settings.json"
    preferences = DesktopSettings(Path(os.environ.get("DBA_DESKTOP_SETTINGS_FILE") or default_preferences), WindowsStartup(name, command))
    app.state.desktop_settings = preferences
    try:
        current = preferences.options()
    except (OSError, ValueError):
        logging.exception("无法读取启动偏好，将显示工作台窗口。")
        current = {"silent_start": False}
    force_show = "--show-window" in sys.argv or os.environ.get("DBA_SHOW_WINDOW") == "true"
    silent_start = current["silent_start"] and not force_show

    viewer = start_file_viewer(_data_directory(), log_dir)
    try:
        _launch_url = f"{URL}#desktop={enable_desktop_login()}"
        config = uvicorn.Config(
            app,
            host=HOST,
            port=PORT,
            loop="asyncio",
            http="h11",
            ws="none",
            log_level="info",
            timeout_graceful_shutdown=10,
        )
        server = uvicorn.Server(config)
        source_host = os.environ.get("DBA_SOURCE_DESKTOP_HOST", "")
        native_host = os.environ.get("DBA_TAURI_HOST")
        tauri_host = Path(native_host) if native_host else None
        if tauri_host is None and source_host:
            tauri_host = Path(source_host).with_name("dba-workbench-tauri.exe")
        if sys.platform == "win32" and not compiled and tauri_host is not None and tauri_host.is_file():
            preferences.native_window = True
            _run_tauri(server, tauri_host, preferences, silent_start)
            return
        window = desktop_window.create(
            APP_TITLE, PORT, _tray_icon_path(), lambda: server.should_exit,
            preferences.close_to_tray,
            lambda: setattr(server, "should_exit", True),
        )
        preferences.native_window = window is not None
        if window is None:
            _start_tray(server)
            if not silent_start:
                threading.Thread(target=_open_browser_when_ready, daemon=True).start()
            server.run()
        else:
            _run_webview(server, window, silent_start)
    except Exception as error:
        raise RuntimeError(f"启动失败，请查看日志：{log_dir / 'server.log'}") from error
    finally:
        stop_file_viewer(viewer)
        app.state.desktop_settings = None


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        _show_error(str(error))
        raise
