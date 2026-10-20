"""Windows desktop entry point used by the compiled distribution."""
from __future__ import annotations

import os
import json
import socket
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


def _configure_runtime() -> Path:
    data_dir = _data_directory()
    log_dir = data_dir.parent / "logs"
    data_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DBA_DATA_DIR", str(data_dir))
    os.environ.setdefault("DBA_MODE", "local")
    os.environ.setdefault("DBA_HOST", HOST)
    os.environ.setdefault("DBA_PORT", str(PORT))
    os.environ.setdefault("DBA_OPEN_BROWSER", "false")
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


def _open_browser_when_ready() -> None:
    for _ in range(80):
        if _probe_service() == "dba":
            webbrowser.open(URL, new=1)
            return
        time.sleep(0.25)


def _show_error(message: str) -> None:
    if os.name == "nt":
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, APP_TITLE, 0x10)
    else:
        print(message, file=sys.stderr)


def main() -> None:
    log_dir = _configure_runtime()
    state = _probe_service()
    if state == "dba":
        webbrowser.open(URL, new=1)
        return
    if state == "other":
        raise RuntimeError(f"端口 {PORT} 已被其他程序占用。")

    import uvicorn
    from main import app

    threading.Thread(target=_open_browser_when_ready, daemon=True).start()
    try:
        uvicorn.run(
            app,
            host=HOST,
            port=PORT,
            loop="asyncio",
            http="h11",
            ws="none",
            log_level="info",
        )
    except Exception as error:
        raise RuntimeError(f"启动失败，请查看日志：{log_dir / 'server.log'}") from error


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        _show_error(str(error))
        raise
