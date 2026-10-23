"""Lifecycle wrapper for the bundled kkFileView sidecar."""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path


VIEWER_HOST = "127.0.0.1"
VIEWER_PORT = int(os.environ.get("DBA_FILE_VIEWER_PORT", "8012"))
VIEWER_ORIGIN = f"http://{VIEWER_HOST}:{VIEWER_PORT}"


def _distribution_root() -> Path | None:
    configured = os.environ.get("DBA_FILE_VIEWER_HOME", "").strip()
    candidates = [Path(configured)] if configured else []
    candidates.extend(
        (
            Path(sys.executable).resolve().parent / "file-viewer",
            Path(__file__).resolve().parents[1] / ".runtime" / "file-viewer",
            Path(__file__).resolve().parent / "file-viewer",
        )
    )
    return next((path for path in candidates if (path / "kkFileView.jar").is_file()), None)


def _port_in_use() -> bool:
    try:
        with socket.create_connection((VIEWER_HOST, VIEWER_PORT), timeout=0.5):
            return True
    except OSError:
        return False


def start_file_viewer(data_dir: Path, log_dir: Path) -> subprocess.Popen | None:
    if os.environ.get("DBA_FILE_VIEWER_DISABLED", "").strip().lower() in {"1", "true", "yes", "on"}:
        return None
    if _port_in_use():
        raise RuntimeError(f"文件预览服务端口 {VIEWER_PORT} 已被其他程序占用。")
    root = _distribution_root()
    if root is None:
        print("kkFileView 未安装；Markdown 预览和脚本文本预览仍可用。", file=sys.stderr)
        return None
    java = root / "runtime" / "bin" / "java.exe"
    office = root / "LibreOfficePortable" / "App" / "libreoffice"
    config_template = root / "config" / "application.properties"
    if not java.is_file() or not office.is_dir() or not config_template.is_file():
        print("文件预览服务组件不完整；请重新安装 DBA 工作台。", file=sys.stderr)
        return None

    configured_data = os.environ.get("DBA_FILE_VIEWER_DATA_DIR", "").strip()
    viewer_data = Path(configured_data).expanduser().resolve() if configured_data else data_dir.parent / "file-viewer"
    # kkFileView rejects "\\." in its full download path, including hidden Windows directories.
    # Pass this directory with forward slashes in both CLI and refreshable environment settings.
    conversion_dir = viewer_data / "cache"
    temp_dir = viewer_data / "temp"
    instance_root = viewer_data / "instance"
    instance_bin = instance_root / "bin"
    instance_config = instance_root / "config"
    conversion_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    instance_bin.mkdir(parents=True, exist_ok=True)
    instance_config.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(config_template, instance_config / "application.properties")
    log_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(java),
        "-Dfile.encoding=UTF-8",
        f"-Djava.io.tmpdir={temp_dir}",
        "-jar",
        str(root / "kkFileView.jar"),
        f"--server.address={VIEWER_HOST}",
        f"--server.port={VIEWER_PORT}",
        f"--base.url={VIEWER_ORIGIN}",
        f"--spring.freemarker.template-loader-path=file:{(root / 'templates').as_posix()}/,classpath:/web/",
        "--trust.host=127.0.0.1",
        "--not.trust.host=",
        "--local.preview.dir=default",
        f"--file.dir={conversion_dir.as_posix()}",
        f"--office.home={office}",
        "--office.preview.type=pdf",
        "--file.upload.disable=true",
        "--delete.password=false",
        "--kk.scriptjs=false",
        "--kk.ignore.ssl=false",
        "--kk.enable.redirect=false",
        "--management.endpoints.web.exposure.include=health",
        "--management.endpoint.health.show-details=never",
        "--logging.level.cn.keking.web.controller.OnlinePreviewController=WARN",
    ]
    viewer_environment = os.environ.copy()
    viewer_environment.update(
        {
            "KKFILEVIEW_BIN_FOLDER": str(instance_bin),
            "TEMP": str(temp_dir),
            "TMP": str(temp_dir),
            "KK_SERVER_PORT": str(VIEWER_PORT),
            "KK_BASE_URL": VIEWER_ORIGIN,
            "KK_OFFICE_HOME": str(office),
            "KK_OFFICE_PREVIEW_TYPE": "pdf",
            "KK_PDF_SIDEBAR_OPEN": "false",
            "KK_FILE_DIR": conversion_dir.as_posix(),
            "KK_LOCAL_PREVIEW_DIR": "default",
            "KK_TRUST_HOST": VIEWER_HOST,
            "KK_MEDIA_CONVERT_DISABLE": "true",
            "KK_DELETE_PASSWORD": "false",
            "KK_KEY": os.environ.get("DBA_FILE_VIEWER_KEY", "false"),
        }
    )
    with (log_dir / "file-viewer.log").open("a", encoding="utf-8", buffering=1) as log:
        return subprocess.Popen(
            command,
            cwd=root,
            env=viewer_environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )


def stop_file_viewer(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=8,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                process.wait(timeout=3)
                return
        except (OSError, subprocess.TimeoutExpired):
            pass
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
