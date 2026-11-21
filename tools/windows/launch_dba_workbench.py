"""Start DBA Workbench from this checkout and open its desktop window."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[2]
SERVER_DIR = REPO_DIR / "server"
sys.path.insert(0, str(SERVER_DIR))
from backend import desktop_window
from backend.browser_launch import find_edge, open_workbench
LOCAL_CONFIG = REPO_DIR / ".runtime" / "local-capabilities.json"
VENV_PYTHON = REPO_DIR / ".runtime" / ".venv" / "Scripts" / "python.exe"
HOST = "127.0.0.1"
PORT = 8686
URL = f"http://{HOST}:{PORT}/"
LOG_DIR = Path(
    os.environ.get("DBA_WORKBENCH_LOG_DIR", REPO_DIR / ".runtime" / "logs")
)
LOG_PATH = LOG_DIR / "server.log"


EDGE_PATH = find_edge()


def probe_service() -> str:
    """Return ``dba``, ``other``, or ``down`` for the configured endpoint."""
    try:
        with urllib.request.urlopen(URL, timeout=1.0) as response:
            body = response.read(4096).decode("utf-8", errors="ignore")
            return "dba" if "DBA 工作台" in body else "other"
    except (urllib.error.URLError, TimeoutError, OSError):
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                return "other"
        except OSError:
            return "down"


def start_server(desktop_host: Path | None = None) -> bool:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if LOCAL_CONFIG.is_file():
        config = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8"))
        roots = config.get("allowed_roots") if isinstance(config, dict) else None
        if not isinstance(roots, list) or not roots or not all(isinstance(root, str) and root.strip() for root in roots):
            raise ValueError(f"本机打开配置缺少有效 allowed_roots：{LOCAL_CONFIG}")
        actions = config.get("allowed_actions", ["edit", "folder", "open"])
        if not isinstance(actions, list) or not actions or not all(isinstance(action, str) and action in {"check", "edit", "folder", "open", "scan", "pick-folder"} for action in actions):
            raise ValueError(f"本机配置 allowed_actions 无效（不允许脚本执行）：{LOCAL_CONFIG}")
        env.setdefault("DBA_LOCAL_CAPABILITIES", "true")
        env.setdefault("DBA_ALLOWED_ROOTS", os.pathsep.join(roots))
        env.setdefault("DBA_ALLOWED_LOCAL_ACTIONS", ",".join(action for action in actions if action != "check"))
    env.update(
        {
            "DBA_MODE": "local",
            "DBA_HOST": HOST,
            "DBA_PORT": str(PORT),
            "DBA_OPEN_BROWSER": "false",
            "DBA_DATA_DIR": str(SERVER_DIR),
            "DBA_LOG_DIR": str(LOG_DIR),
            "DBA_FILE_VIEWER_DATA_DIR": str(REPO_DIR / ".runtime" / "file-viewer-data"),
            "DBA_WEBVIEW_PROFILE": str(REPO_DIR / ".runtime" / "webview"),
            "DBA_DESKTOP_SETTINGS_FILE": str(REPO_DIR / ".runtime" / "desktop-settings.json"),
        }
    )
    if EDGE_PATH is not None and EDGE_PATH.is_file():
        env["DBA_BROWSER_PATH"] = str(EDGE_PATH)

    python = VENV_PYTHON if VENV_PYTHON.is_file() else Path(sys.executable)
    command = [str(python), "desktop.py"]
    if desktop_host is not None:
        desktop_host = desktop_host.resolve(strict=True)
        if not desktop_host.is_file():
            raise ValueError(f"无效的桌面启动宿主：{desktop_host}")
        # The shortcut launches this helper with the same Python environment the host will use.
        python_dll = Path(sys.base_prefix) / f"python{sys.version_info.major}{sys.version_info.minor}.dll"
        if not python_dll.is_file():
            raise ValueError(f"未找到 Python 运行库：{python_dll}")
        command = [str(desktop_host), str(python_dll), sys.executable, "desktop.py"]
        env["DBA_SOURCE_DESKTOP_HOST"] = str(desktop_host)

    with LOG_PATH.open("ab", buffering=0) as log_file:
        log_file.write(
            f"\n[{datetime.now().isoformat(timespec='seconds')}] starting DBA Workbench\n".encode()
        )
        subprocess.Popen(
            command,
            cwd=SERVER_DIR,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=(
                subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                if os.name == "nt"
                else 0
            ),
        )

    for _ in range(60):
        time.sleep(0.25)
        state = probe_service()
        if state == "dba":
            return True
    return False


def main(desktop_host: Path | None = None, *, on_logon: bool = False, show_window: bool = False) -> None:
    if on_logon:
        os.environ["DBA_ON_LOGON"] = "true"
    if show_window:
        os.environ["DBA_SHOW_WINDOW"] = "true"
    if not (SERVER_DIR / "main.py").is_file():
        raise SystemExit(f"找不到服务入口：{SERVER_DIR / 'main.py'}")

    state = probe_service()
    if state == "other":
        raise SystemExit(f"端口 {PORT} 已被其他程序占用。")
    if state == "down":
        started = start_server() if desktop_host is None else start_server(desktop_host)
        if not started:
            raise SystemExit(f"DBA 工作台启动失败，请查看日志：{LOG_PATH}")
        return

    if on_logon:
        return
    if not desktop_window.activate(PORT) and not open_workbench(URL, EDGE_PATH):
        raise SystemExit(f"无法打开默认浏览器，请手动访问：{URL}")


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="启动 DBA 工作台")
        parser.add_argument("--desktop-host", type=Path, help="使用指定的 DBA 工作台源码启动宿主")
        parser.add_argument("--on-logon", action="store_true", help="Windows 登录自启")
        parser.add_argument("--show-window", action="store_true", help="忽略静默启动并显示窗口")
        args = parser.parse_args()
        main(args.desktop_host, on_logon=args.on_logon, show_window=args.show_window)
    except (OSError, ValueError, SystemExit) as error:
        if os.name == "nt":
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, str(error), "DBA 工作台", 0x10)
        else:
            raise
