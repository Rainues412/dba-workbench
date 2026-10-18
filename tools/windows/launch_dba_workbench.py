"""Start DBA Workbench locally and open it in the default browser."""

from __future__ import annotations

import os
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
HOST = "127.0.0.1"
PORT = 8686
URL = f"http://{HOST}:{PORT}/"
LOG_DIR = Path(
    os.environ.get("DBA_WORKBENCH_LOG_DIR", REPO_DIR / ".runtime" / "logs")
)
LOG_PATH = LOG_DIR / "server.log"


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
    env.update(
        {
            "DBA_MODE": "local",
            "DBA_HOST": HOST,
            "DBA_PORT": str(PORT),
            "DBA_OPEN_BROWSER": "false",
        }
    )

    with LOG_PATH.open("ab", buffering=0) as log_file:
        log_file.write(
            f"\n[{datetime.now().isoformat(timespec='seconds')}] starting DBA Workbench\n".encode()
        )
        subprocess.Popen(
            [sys.executable, "main.py"],
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
        if state == "other":
            return False
    return False


def main() -> None:
    if not (SERVER_DIR / "main.py").is_file():
        raise SystemExit(f"找不到服务入口：{SERVER_DIR / 'main.py'}")

    state = probe_service()
    if state == "other":
        raise SystemExit(f"端口 {PORT} 已被其他程序占用。")
    if state == "down" and not start_server():
        raise SystemExit(f"DBA 工作台启动失败，请查看日志：{LOG_PATH}")

    if not webbrowser.open(URL, new=1):
        raise SystemExit(f"无法打开默认浏览器，请手动访问：{URL}")


if __name__ == "__main__":
    main()
