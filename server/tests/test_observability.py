from __future__ import annotations

import io
import json
import logging
import sqlite3
import uuid

from fastapi.testclient import TestClient

from backend.observability import JsonFormatter, logger


def _assert_error(response, status: int, code: str) -> str:
    assert response.status_code == status
    body = response.json()
    assert body["error"]["code"] == code
    request_id = body["error"]["request_id"]
    assert str(uuid.UUID(request_id)) == request_id
    assert response.headers["x-request-id"] == request_id
    return request_id


def test_error_envelope_distinguishes_common_failures(client: TestClient) -> None:
    _assert_error(client.get("/api/scripts/999999"), 404, "NOT_FOUND")
    _assert_error(client.post("/api/tasks/", json={}), 422, "VALIDATION_ERROR")
    _assert_error(
        client.post("/api/launcher/path", json={"path": r"D:\blocked.txt"}),
        403,
        "FORBIDDEN",
    )

    article = client.post("/api/articles/", json={"title": "conflict"}).json()
    first = client.put(
        f"/api/articles/{article['id']}",
        json={"summary": "first"},
        headers={"If-Match": str(article["revision"])},
    )
    assert first.status_code == 200
    _assert_error(
        client.put(
            f"/api/articles/{article['id']}",
            json={"summary": "stale"},
            headers={"If-Match": str(article["revision"])},
        ),
        409,
        "CONFLICT",
    )


def test_unhandled_error_is_generic_and_has_request_id(client: TestClient) -> None:
    path = "/api/test-only/unhandled-error"

    def fail_without_exposing_details():
        raise RuntimeError("password=never-log-this token=never-log-that")

    client.app.add_api_route(path, fail_without_exposing_details, methods=["GET"])
    safe_client = TestClient(
        client.app,
        base_url="http://localhost",
        raise_server_exceptions=False,
    )
    response = safe_client.get(path)
    _assert_error(response, 500, "INTERNAL_ERROR")
    assert "never-log" not in response.text


def test_logs_are_redacted_and_audit_contains_metadata_only(
    client: TestClient, isolated_app
) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    try:
        logger.warning("password=%s token=%s", "log-secret", "session-secret")
        response = client.post(
            "/api/resources/",
            json={
                "name": "audited resource",
                "notes": "password=db-secret token=api-secret ciphertext=blob-secret",
            },
        )
        assert response.status_code == 200
    finally:
        logger.removeHandler(handler)

    log_output = stream.getvalue()
    assert "log-secret" not in log_output
    assert "session-secret" not in log_output
    assert "db-secret" not in log_output
    assert "api-secret" not in log_output
    assert "blob-secret" not in log_output
    for line in log_output.splitlines():
        json.loads(line)

    _, test_db = isolated_app
    with sqlite3.connect(test_db) as conn:
        conn.row_factory = sqlite3.Row
        columns = {row[1] for row in conn.execute("PRAGMA table_info(audit_events)")}
        assert columns == {
            "id", "request_id", "actor", "action", "object_type", "object_id",
            "result", "source", "created_at",
        }
        audit = dict(
            conn.execute(
                "SELECT * FROM audit_events WHERE object_type = 'resources' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        )

    assert audit["actor"] == "local-user"
    assert audit["action"] == "post"
    assert audit["object_type"] == "resources"
    assert audit["result"] == "success"
    assert audit["source"]
    assert audit["created_at"]
    serialized = json.dumps(audit)
    assert "db-secret" not in serialized
    assert "api-secret" not in serialized
    assert "blob-secret" not in serialized
