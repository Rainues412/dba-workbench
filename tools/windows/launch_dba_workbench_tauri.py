"""Run the Tauri migration preview against a fresh, separate workbench database."""
from __future__ import annotations

import argparse
import http.client
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import ExitStack
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend"
HOST = "127.0.0.1"
VITE_PORT = 5174  # Must match the Tauri development URL.


def port_for_backend() -> int:
    with socket.socket() as listener:
        listener.bind((HOST, 0))
        return listener.getsockname()[1]


def wait_for_http(process: subprocess.Popen, port: int, path: str, log: Path) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and process.poll() is None:
        connection = http.client.HTTPConnection(HOST, port, timeout=0.4)
        try:
            connection.request("GET", path)
            if connection.getresponse().status == 200 and process.poll() is None:
                return
        except (OSError, http.client.HTTPException):
            pass
        finally:
            connection.close()
        time.sleep(0.1)
    raise RuntimeError(f"迁移预览的本机服务启动失败，请查看 {log}")


def stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def start_backend(env: dict[str, str], port: int, stack: ExitStack) -> str:
    # This dedicated launcher also owns the temporary backend, so its desktop
    # launch token can be passed to the WebView without writing it to a file.
    for key in list(os.environ):
        if key.upper().startswith("DBA_"):
            del os.environ[key]
    os.environ.update(env)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(REPO / "server"))

    import uvicorn
    from backend.auth import enable_desktop_login
    from main import app

    token = enable_desktop_login()
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, ws="none"))
    worker = threading.Thread(target=server.run, name="tauri-preview-backend", daemon=True)
    worker.start()

    def stop_backend() -> None:
        server.should_exit = True
        worker.join(timeout=5)

    stack.callback(stop_backend)
    deadline = time.monotonic() + 20
    while not server.started and worker.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("迁移预览的测试后端启动失败")
    return token


def main(executable: Path, work_dir: Path) -> int:
    node = shutil.which("node")
    vite = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
    if not node or not vite.is_file():
        raise RuntimeError("请先准备 Node.js 并安装 frontend 的依赖")
    if not executable.is_file() or not work_dir.is_dir():
        raise RuntimeError("请指定已构建的 Tauri EXE 和已存在的测试工作目录")
    # Reserve in exclusive mode to avoid opening the WebView against another Vite app.
    with socket.socket() as guard:
        guard.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        guard.bind((HOST, VITE_PORT))

    data_dir = Path(tempfile.mkdtemp(prefix="tauri-preview-", dir=work_dir)).resolve()
    print(data_dir, flush=True)
    # Do not inherit runtime configuration for the regular desktop application.
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("DBA_")}
    backend_port = port_for_backend()
    env.update(
        DBA_DATA_DIR=str(data_dir),
        DBA_TAURI_DEV_DATA_DIR=str(data_dir),
        DBA_TAURI_DEV_BACKEND_PORT=str(backend_port),
        DBA_PORT=str(backend_port),
        DBA_HOST=HOST,
        DBA_OPEN_BROWSER="false",
        DBA_CORS_ORIGINS=f"http://{HOST}:{VITE_PORT}",
        PYTHONDONTWRITEBYTECODE="1",
        TEMP=str(data_dir),
        TMP=str(data_dir),
    )

    with ExitStack() as stack:
        env["DBA_TAURI_DEV_DESKTOP_TOKEN"] = start_backend(env, backend_port, stack)

        def start(command: list[str], cwd: Path, name: str) -> tuple[subprocess.Popen, Path]:
            log_path = data_dir / name
            log = stack.enter_context(log_path.open("wb"))
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            stack.callback(stop, process)
            return process, log_path

        frontend, frontend_log = start(
            [node, str(vite), "--strictPort", "--port", str(VITE_PORT)], FRONTEND, "frontend.log"
        )
        wait_for_http(frontend, VITE_PORT, "/", frontend_log)
        desktop, _ = start([str(executable)], executable.parent, "desktop.log")
        return desktop.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    sys.exit(main(args.executable.resolve(), args.work_dir.resolve()))
