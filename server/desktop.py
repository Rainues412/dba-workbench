"""Windows desktop entry point used by the compiled distribution."""
from __future__ import annotations

import os
import json
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


APP_TITLE = "DBA 工作台"
HOST = "127.0.0.1"
PORT = int(os.environ.get("DBA_PORT", "8686"))
URL = f"http://{HOST}:{PORT}/"


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
            os.environ["DBA_ALLOWED_LOCAL_ACTIONS"] = "check,edit,folder,open,pick-folder,scan"
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
    browser_path = os.environ.get("DBA_BROWSER_PATH", "").strip().strip('"')
    if browser_path and Path(browser_path).is_file():
        subprocess.Popen(
            [browser_path, "--new-window", URL],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return
    webbrowser.open(URL, new=1)


def _open_browser_when_ready() -> None:
    for _ in range(80):
        if _probe_service() == "dba":
            _open_workbench()
            return
        time.sleep(0.25)


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


def _run_tray(server) -> None:
    import pystray
    from PIL import Image

    icon = pystray.Icon(
        "dba-workbench",
        Image.open(_tray_icon_path()),
        APP_TITLE,
        pystray.Menu(
            pystray.MenuItem("打开工作台", lambda *_: _open_workbench(), default=True),
            pystray.MenuItem("退出", lambda tray, _: _exit_from_tray(server, tray)),
        ),
    )
    icon.run()


def _start_tray(server) -> threading.Thread:
    thread = threading.Thread(target=_run_tray, args=(server,), name="system-tray", daemon=True)
    thread.start()
    return thread


def main() -> None:
    log_dir = _configure_runtime()
    state = _probe_service()
    if state == "dba":
        _open_workbench()
        return
    if state == "other":
        raise RuntimeError(f"端口 {PORT} 已被其他程序占用。")

    import uvicorn
    from file_viewer_runtime import start_file_viewer, stop_file_viewer
    from main import app

    viewer = start_file_viewer(_data_directory(), log_dir)
    threading.Thread(target=_open_browser_when_ready, daemon=True).start()
    config = uvicorn.Config(
        app,
        host=HOST,
        port=PORT,
        loop="asyncio",
        http="h11",
        ws="none",
        log_level="info",
    )
    server = uvicorn.Server(config)
    _start_tray(server)
    try:
        server.run()
    except Exception as error:
        raise RuntimeError(f"启动失败，请查看日志：{log_dir / 'server.log'}") from error
    finally:
        stop_file_viewer(viewer)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        _show_error(str(error))
        raise
