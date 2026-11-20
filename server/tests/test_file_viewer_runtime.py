import subprocess
import json
import os
import sys
import time
from pathlib import Path

import pytest

import file_viewer_runtime


class FakeProcess:
    def __init__(self):
        self.pid = 4321
        self.terminated = False
        self.killed = False
        self.waits = []

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout):
        self.waits.append(timeout)
        return 0


def viewer_distribution(tmp_path):
    root = tmp_path / "file-viewer"
    (root / "runtime" / "bin").mkdir(parents=True)
    (root / "runtime" / "bin" / "java.exe").write_bytes(b"java")
    (root / "LibreOfficePortable" / "App" / "libreoffice").mkdir(parents=True)
    (root / "kkFileView.jar").write_bytes(b"jar")
    (root / "config").mkdir()
    (root / "config" / "application.properties").write_text("kk.key = ${KK_KEY:false}\n", encoding="utf-8")
    return root


@pytest.mark.parametrize("data_folder", ["file-viewer-data", ".runtime/file-viewer-data"])
def test_start_file_viewer_uses_bundled_runtime_and_loopback_only(tmp_path, monkeypatch, data_folder):
    root = viewer_distribution(tmp_path)
    process = FakeProcess()
    calls = []
    monkeypatch.setattr(file_viewer_runtime, "_port_in_use", lambda: False)
    monkeypatch.setattr(file_viewer_runtime, "_distribution_root", lambda: root)
    monkeypatch.setattr(file_viewer_runtime, "_create_process_job", lambda: None)
    monkeypatch.setattr(file_viewer_runtime.subprocess, "Popen", lambda command, **kwargs: calls.append((command, kwargs)) or process)
    monkeypatch.setenv("DBA_FILE_VIEWER_KEY", "viewer-secret")
    viewer_data = tmp_path / data_folder
    monkeypatch.setenv("DBA_FILE_VIEWER_DATA_DIR", str(viewer_data))

    result = file_viewer_runtime.start_file_viewer(tmp_path / "data", tmp_path / "logs")

    assert result is process
    command, kwargs = calls[0]
    assert command[0] == str(root / "runtime" / "bin" / "java.exe")
    assert f"--server.address={file_viewer_runtime.VIEWER_HOST}" in command
    assert "--trust.host=127.0.0.1" in command
    assert "--local.preview.dir=default" in command
    assert "--file.upload.disable=true" in command
    assert "--kk.scriptjs=false" in command
    assert not any(value.startswith("--kk.key=") for value in command)
    assert "--logging.level.cn.keking.web.controller.OnlinePreviewController=WARN" in command
    assert any(value.startswith("--office.home=") for value in command)
    assert kwargs["cwd"] == root
    assert kwargs["env"]["KKFILEVIEW_BIN_FOLDER"] == str(viewer_data / "instance" / "bin")
    assert kwargs["env"]["KK_OFFICE_HOME"] == str(root / "LibreOfficePortable" / "App" / "libreoffice")
    assert kwargs["env"]["KK_PDF_SIDEBAR_OPEN"] == "false"
    assert kwargs["env"]["KK_TRUST_HOST"] == "127.0.0.1"
    assert kwargs["env"]["KK_FILE_DIR"] == (viewer_data / "cache").as_posix()
    assert f"--file.dir={(viewer_data / 'cache').as_posix()}" in command
    assert "\\." not in kwargs["env"]["KK_FILE_DIR"]
    assert kwargs["env"]["KK_KEY"] == "viewer-secret"
    assert kwargs["env"]["TEMP"] == str(viewer_data / "temp")
    assert kwargs["env"]["TMP"] == kwargs["env"]["TEMP"]
    assert f"-Djava.io.tmpdir={viewer_data / 'temp'}" in command
    assert (viewer_data / "instance" / "config" / "application.properties").is_file()


def test_start_file_viewer_rejects_an_occupied_port(tmp_path, monkeypatch):
    monkeypatch.setattr(file_viewer_runtime, "_port_in_use", lambda: True)
    try:
        file_viewer_runtime.start_file_viewer(tmp_path / "data", tmp_path / "logs")
    except RuntimeError as error:
        assert "已被其他程序占用" in str(error)
    else:
        raise AssertionError("occupied viewer port must fail closed")


def test_viewer_is_assigned_to_its_lifetime_job_and_released_on_stop(tmp_path, monkeypatch):
    root = viewer_distribution(tmp_path)
    process = FakeProcess()
    assigned = []
    closed = []

    class Job:
        def assign(self, pid):
            assigned.append(pid)

        def close(self):
            closed.append(True)

    monkeypatch.setattr(file_viewer_runtime, "_port_in_use", lambda: False)
    monkeypatch.setattr(file_viewer_runtime, "_distribution_root", lambda: root)
    monkeypatch.setattr(file_viewer_runtime, "_create_process_job", Job)
    monkeypatch.setattr(file_viewer_runtime.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(file_viewer_runtime, "_stop_file_viewer_process", lambda _: None)
    result = file_viewer_runtime.start_file_viewer(tmp_path / "data", tmp_path / "logs")
    assert assigned == [process.pid]
    file_viewer_runtime.stop_file_viewer(result)
    file_viewer_runtime.stop_file_viewer(result)
    assert closed == [True]


def test_failed_job_assignment_cleans_up_new_viewer(tmp_path, monkeypatch):
    root = viewer_distribution(tmp_path)
    process = FakeProcess()
    closed = []
    stopped = []

    class Job:
        def assign(self, pid):
            raise OSError("test-only job assignment failure")

        def close(self):
            closed.append(True)

    monkeypatch.setattr(file_viewer_runtime, "_port_in_use", lambda: False)
    monkeypatch.setattr(file_viewer_runtime, "_distribution_root", lambda: root)
    monkeypatch.setattr(file_viewer_runtime, "_create_process_job", Job)
    monkeypatch.setattr(file_viewer_runtime.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(file_viewer_runtime, "_stop_file_viewer_process", stopped.append)
    with pytest.raises(OSError, match="job assignment failure"):
        file_viewer_runtime.start_file_viewer(tmp_path / "data", tmp_path / "logs")
    assert stopped == [process]
    assert closed == [True]


@pytest.mark.skipif(os.name != "nt", reason="Windows process lifetime jobs")
def test_job_reaps_viewer_tree_after_desktop_host_is_killed(tmp_path):
    import ctypes
    from ctypes import wintypes
    from backend.windows_process_job import ProcessJob

    result_path = tmp_path / "owned-processes.json"
    child_script = (
        "import subprocess,sys,time;"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);"
        "print(child.pid,flush=True);time.sleep(120)"
    )
    owner_script = "\n".join([
        "import sys,subprocess,json,time",
        "from pathlib import Path",
        "from backend.windows_process_job import ProcessJob",
        "job=ProcessJob()",
        f"viewer=subprocess.Popen([sys.executable,'-c',{child_script!r}],stdout=subprocess.PIPE,text=True)",
        "job.assign(viewer.pid)",
        "child_id=int(viewer.stdout.readline())",
        f"Path({str(result_path)!r}).write_text(json.dumps([viewer.pid,child_id]))",
        "time.sleep(120)",
    ])
    # An outer job guarantees cleanup even if this regression assertion fails.
    cleanup = ProcessJob()
    owner = subprocess.Popen(
        [sys.executable, "-c", owner_script],
        cwd=Path(file_viewer_runtime.__file__).parent,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handles = []
    try:
        cleanup.assign(owner.pid)
        deadline = time.monotonic() + 10
        while not result_path.exists() and owner.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert result_path.exists(), "process lifetime test did not become ready"
        for pid in json.loads(result_path.read_text()):
            handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
            assert handle, ctypes.WinError(ctypes.get_last_error())
            handles.append(handle)
        owner.kill()
        owner.wait(timeout=5)
        assert all(kernel.WaitForSingleObject(handle, 5000) == 0 for handle in handles)
    finally:
        cleanup.close()
        owner.wait(timeout=5)
        owner.stderr.close()
        for handle in handles:
            kernel.CloseHandle(handle)


def test_start_file_viewer_handles_missing_distribution(tmp_path, monkeypatch):
    monkeypatch.setattr(file_viewer_runtime, "_port_in_use", lambda: False)
    monkeypatch.setattr(file_viewer_runtime, "_distribution_root", lambda: None)
    assert file_viewer_runtime.start_file_viewer(tmp_path / "data", tmp_path / "logs") is None


def test_distribution_root_finds_source_runtime(tmp_path, monkeypatch):
    module_path = tmp_path / "server" / "file_viewer_runtime.py"
    module_path.parent.mkdir()
    module_path.write_text("", encoding="utf-8")
    source_runtime = tmp_path / ".runtime" / "file-viewer"
    source_runtime.mkdir(parents=True)
    (source_runtime / "kkFileView.jar").write_bytes(b"jar")
    monkeypatch.delenv("DBA_FILE_VIEWER_HOME", raising=False)
    monkeypatch.setattr(file_viewer_runtime, "__file__", str(module_path))
    monkeypatch.setattr(file_viewer_runtime.sys, "executable", str(tmp_path / "python" / "python.exe"))

    assert file_viewer_runtime._distribution_root() == source_runtime


def test_stop_file_viewer_terminates_owned_process(monkeypatch):
    process = FakeProcess()
    taskkill_calls = []
    monkeypatch.setattr(
        file_viewer_runtime.subprocess,
        "run",
        lambda command, **kwargs: taskkill_calls.append((command, kwargs)) or subprocess.CompletedProcess(command, 0),
    )
    file_viewer_runtime.stop_file_viewer(process)
    assert taskkill_calls[0][0] == ["taskkill.exe", "/PID", "4321", "/T", "/F"]
    assert process.terminated is False
    assert process.killed is False
    assert process.waits == [3]


def test_stop_file_viewer_kills_process_that_does_not_exit(monkeypatch):
    process = FakeProcess()
    attempts = 0

    def wait(timeout):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise subprocess.TimeoutExpired("java", timeout)
        return 0

    process.wait = wait
    monkeypatch.setattr(
        file_viewer_runtime.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1),
    )
    file_viewer_runtime.stop_file_viewer(process)
    assert process.terminated is True
    assert process.killed is True
