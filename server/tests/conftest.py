from __future__ import annotations

import socket
import sys
import threading
import time
from collections.abc import Generator
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient


SERVER_DIR = Path(__file__).resolve().parents[1]
PRODUCTION_DB = SERVER_DIR / "workspace.db"

if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


@pytest.fixture()
def isolated_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Return the application with every database access redirected to tmp_path."""
    test_db = (tmp_path / "workspace-test.db").resolve()
    assert test_db != PRODUCTION_DB.resolve()

    from backend import database

    monkeypatch.setattr(database, "DB_PATH", str(test_db))

    # Import after redirecting DB_PATH. Routers use database.get_db_ctx at call
    # time; vault keeps a separate key path that must also be isolated.
    import main
    from backend.routers import vault

    monkeypatch.setattr(vault, "KEY_FILE", tmp_path / ".workspace-test-secret")
    database.init_db()

    assert test_db.exists()
    assert Path(database.DB_PATH).resolve() == test_db
    yield main.app, test_db


@pytest.fixture()
def client(isolated_app) -> Generator[TestClient, None, None]:
    app, _ = isolated_app
    with TestClient(app) as test_client:
        yield test_client


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
def live_server(isolated_app) -> Generator[str, None, None]:
    """Run the isolated app on an ephemeral localhost port for browser tests."""
    app, _ = isolated_app
    port = _free_local_port()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        pytest.fail("isolated Uvicorn server did not start")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        if thread.is_alive():
            pytest.fail("isolated Uvicorn server did not stop")
