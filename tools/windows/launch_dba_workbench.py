"""Start DBA Workbench from this checkout and open it in Microsoft Edge."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[2]
SERVER_DIR = REPO_DIR / "server"
LOCAL_CONFIG = REPO_DIR / ".runtime" / "local-capabilities.json"
VENV_PYTHON = REPO_DIR / ".runtime" / ".venv" / "Scripts" / "python.exe"
HOST = "127.0.0.1"
PORT = 8686
URL = f"http://{HOST}:{PORT}/"
LOG_DIR = Path(
    os.environ.get("DBA_WORKBENCH_LOG_DIR", REPO_DIR / ".runtime" / "logs")
)
LOG_PATH = LOG_DIR / "server.log"


def find_edge() -> Path | None:
    """Find Edge without tying the checkout to one Windows installation path."""
    configured = os.environ.get("DBA_EDGE_PATH", "").strip().strip('"')
    if configured:
        candidate = Path(configured)
        return candidate if candidate.is_file() else None
    discovered = shutil.which("msedge")
    if discovered:
        return Path(discovered)
    candidates = []
    for variable, suffix in (
        ("PROGRAMFILES", ("Microsoft", "Edge", "Application", "msedge.exe")),
        ("PROGRAMFILES(X86)", ("Microsoft", "Edge", "Application", "msedge.exe")),
        ("LOCALAPPDATA", ("Microsoft", "Edge", "Application", "msedge.exe")),
    ):
        base = os.environ.get(variable)
        if base:
            candidates.append(Path(base).joinpath(*suffix))
    return next((candidate for candidate in candidates if candidate.is_file()), None)


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


def start_server() -> bool:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if LOCAL_CONFIG.is_file():
        config = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8"))
        roots = config.get("allowed_roots") if isinstance(config, dict) else None
        if not isinstance(roots, list) or not roots or not all(isinstance(root, str) and root.strip() for root in roots):
            raise ValueError(f"本机打开配置缺少有效 allowed_roots：{LOCAL_CONFIG}")
        actions = config.get("allowed_actions", ["edit", "folder", "open"])
        if not isinstance(actions, list) or not actions or not all(isinstance(action, str) and action in {"edit", "folder", "open", "scan", "pick-folder"} for action in actions):
            raise ValueError(f"本机配置 allowed_actions 无效（不允许脚本执行）：{LOCAL_CONFIG}")
        env.setdefault("DBA_LOCAL_CAPABILITIES", "true")
        env.setdefault("DBA_ALLOWED_ROOTS", os.pathsep.join(roots))
        env.setdefault("DBA_ALLOWED_LOCAL_ACTIONS", ",".join(actions))
    env.update(
        {
            "DBA_MODE": "local",
            "DBA_HOST": HOST,
            "DBA_PORT": str(PORT),
            "DBA_OPEN_BROWSER": "false",
            "DBA_DATA_DIR": str(SERVER_DIR),
            "DBA_LOG_DIR": str(LOG_DIR),
        }
    )
    if EDGE_PATH is not None and EDGE_PATH.is_file():
        env["DBA_BROWSER_PATH"] = str(EDGE_PATH)

    with LOG_PATH.open("ab", buffering=0) as log_file:
        log_file.write(
            f"\n[{datetime.now().isoformat(timespec='seconds')}] starting DBA Workbench\n".encode()
        )
        subprocess.Popen(
            [str(VENV_PYTHON) if VENV_PYTHON.is_file() else sys.executable, "desktop.py"],
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


def main() -> None:
    if not (SERVER_DIR / "main.py").is_file():
        raise SystemExit(f"找不到服务入口：{SERVER_DIR / 'main.py'}")

    state = probe_service()
    if state == "other":
        raise SystemExit(f"端口 {PORT} 已被其他程序占用。")
    if state == "down":
        if not start_server():
            raise SystemExit(f"DBA 工作台启动失败，请查看日志：{LOG_PATH}")
        return

    if os.name == "nt" and EDGE_PATH is not None and EDGE_PATH.is_file():
        subprocess.Popen(
            [str(EDGE_PATH), "--new-window", URL],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    elif not webbrowser.open(URL, new=1):
        raise SystemExit(f"无法打开默认浏览器，请手动访问：{URL}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, SystemExit) as error:
        if os.name == "nt":
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, str(error), "DBA 工作台", 0x10)
        else:
            raise
