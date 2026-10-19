import pytest

from backend.database import get_db_ctx


def archive_entry(**changes):
    return {"id": "legacy-01", "title": "历史归档任务", "notes": "归档说明", "priority": "P0", "deadline": "2025-05-01", "completedAt": "2025-05-02T08:30:00Z", **changes}


def test_archive_import_appends_completed_tasks_and_is_idempotent(client):
    existing = client.post("/api/tasks/", json={"title": "现有任务"}).json()
    payload = {"items": [archive_entry()]}
    result = client.post("/api/tasks/legacy-archive", json=payload)
    assert result.status_code == 200, result.text
    assert result.json() == {"ok": True, "imported": 1, "skipped": 0}
    assert client.post("/api/tasks/legacy-archive", json=payload).json() == {"ok": True, "imported": 0, "skipped": 1}
    rows = client.get("/api/tasks/", params={"page_size": 200}).json()["items"]
    assert len(rows) == 2
    imported = next(row for row in rows if row["id"] != existing["id"])
    assert imported["title"] == "历史归档任务"
    assert imported["description"] == "归档说明"
    assert imported["status"] == "已完成"
    assert imported["priority"] == "高"
    assert imported["due_date"] == "2025-05-01"
    assert imported["completed_at"] == "2025-05-02T08:30:00+00:00"
    assert client.get(f"/api/tasks/{existing['id']}").json()["status"] == "待处理"


@pytest.mark.parametrize("invalid", [{"deadline": "not-a-date"}, {"completedAt": "not-a-date"}, {"priority": "unknown"}])
def test_archive_failed_batch_rolls_back_tasks_and_receipts(client, invalid):
    response = client.post("/api/tasks/legacy-archive", json={"items": [archive_entry(), archive_entry(id="bad-entry", **invalid)]})
    assert response.status_code == 422, response.text
    assert client.get("/api/tasks/").json()["total"] == 0
    with get_db_ctx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM legacy_task_imports").fetchone()[0] == 0
    # The successfully processed first row was also rolled back, so retry imports it.
    assert client.post("/api/tasks/legacy-archive", json={"items": [archive_entry()]}).json()["imported"] == 1


def test_archive_retry_after_deleting_imported_task_does_not_resurrect_it(client):
    payload = {"items": [archive_entry()]}
    assert client.post("/api/tasks/legacy-archive", json=payload).status_code == 200
    row = client.get("/api/tasks/").json()["items"][0]
    assert client.delete(f"/api/tasks/{row['id']}", headers={"If-Match": str(row["revision"])}).status_code == 200
    assert client.post("/api/tasks/legacy-archive", json=payload).json() == {"ok": True, "imported": 0, "skipped": 1}
    assert client.get("/api/tasks/").json()["total"] == 0
    with get_db_ctx() as conn:
        receipt = conn.execute("SELECT task_id FROM legacy_task_imports").fetchone()
        assert receipt is not None and receipt["task_id"] is None


def test_script_historical_body_endpoint_reads_exact_version_and_404(client):
    created = client.post("/api/scripts/", json={"title": "版本脚本", "content": "SELECT 'first';"}).json()
    second = client.put(f"/api/scripts/{created['id']}", json={"content": "SELECT 'second';"}, headers={"If-Match": str(created["revision"])}).json()
    third = client.put(f"/api/scripts/{created['id']}", json={"content": "SELECT 'third';"}, headers={"If-Match": str(second["revision"])}).json()
    assert third["version"] == 3
    for version, expected in [(1, "SELECT 'first';"), (2, "SELECT 'second';")]:
        response = client.get(f"/api/scripts/{created['id']}/versions/{version}")
        assert response.status_code == 200
        assert response.json()["version"] == version
        assert response.json()["content"] == expected
    assert client.get(f"/api/scripts/{created['id']}/versions/999").status_code == 404
    assert client.get("/api/scripts/999999/versions/1").status_code == 404
    # Historical reads do not mutate the current body or revision.
    current = client.get(f"/api/scripts/{created['id']}").json()
    assert current["content"] == "SELECT 'third';"
    assert current["revision"] == third["revision"]
