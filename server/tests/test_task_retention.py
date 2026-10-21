from datetime import datetime, timedelta, timezone

from backend.database import get_db_ctx


def task(client, title, **values):
    response = client.post("/api/tasks/", json={"title": title, **values})
    assert response.status_code == 200, response.text
    return response.json()


def age(row, expression="datetime('now', '-16 days')", created="2020-01-01"):
    with get_db_ctx() as conn:
        conn.execute(f"UPDATE tasks SET completed_at = {expression}, created_at = ? WHERE id = ?", (created, row["id"]))
        conn.commit()


def test_completed_tasks_sort_by_creation_not_priority_due_or_completion(client):
    oldest = task(client, "最早创建", status="已完成", priority="高", due_date="2000-01-01")
    newest = task(client, "最近创建", status="已完成", priority="低", due_date="2999-01-01")
    tied = task(client, "同时间创建", status="已完成", priority="中")
    unfinished = task(client, "未完成", priority="低")
    with get_db_ctx() as conn:
        conn.execute("UPDATE tasks SET created_at = '2020-01-01' WHERE id = ?", (oldest["id"],))
        conn.execute("UPDATE tasks SET created_at = '2025-01-01' WHERE id IN (?, ?)", (newest["id"], tied["id"]))
        conn.commit()
    rows = client.get("/api/tasks/").json()["items"]
    assert [row["id"] for row in rows] == [unfinished["id"], tied["id"], newest["id"], oldest["id"]]
    assert [row["id"] for row in client.get("/api/tasks/", params={"status": "已完成"}).json()["items"]] == [tied["id"], newest["id"], oldest["id"]]


def test_archive_boundary_is_fifteen_days_since_completion_and_preserves_data(client):
    recent = task(client, "未满十五天", status="已完成")
    boundary = task(client, "刚满十五天", status="已完成", description="完整说明")
    old_open = task(client, "旧的未完成")
    offset = task(client, "有时区的历史任务", status="已完成")
    age(recent, "datetime('now', '-15 days', '+1 hour')")
    age(boundary, "datetime('now', '-15 days')")
    age(old_open)
    completed = (datetime.now(timezone.utc) - timedelta(days=16)).astimezone(timezone(timedelta(hours=8))).isoformat()
    with get_db_ctx() as conn:
        conn.execute("UPDATE tasks SET completed_at = ? WHERE id = ?", (completed, offset["id"]))
        conn.commit()
    active = client.get("/api/tasks/").json()
    archived = client.get("/api/tasks/", params={"archived": True}).json()
    assert {row["id"] for row in active["items"]} == {recent["id"], old_open["id"]}
    assert {row["id"] for row in archived["items"]} == {boundary["id"], offset["id"]}
    assert all(row["is_archived"] == 1 for row in archived["items"])
    detail = client.get(f"/api/tasks/{boundary['id']}").json()
    assert detail["description"] == "完整说明"
    assert detail["revision"] == boundary["revision"]  # Archiving reads never mutate rows.
    assert len(client.get("/api/export/all").json()["tasks"]) == 4


def test_completed_edits_do_not_restart_retention_and_restore_respects_revision(client):
    row = task(client, "旧已完成", status="已完成")
    assert row["completed_at"] is not None
    age(row)
    original = client.get(f"/api/tasks/{row['id']}").json()
    updated = client.put(f"/api/tasks/{row['id']}", json={"status": "已完成", "title": "改标题"}, headers={"If-Match": str(row["revision"])}).json()
    assert updated["completed_at"] == original["completed_at"]
    assert updated["is_archived"] == 1
    assert client.put(f"/api/tasks/{row['id']}", json={"status": "待处理"}, headers={"If-Match": str(row["revision"])}).status_code == 409
    restored = client.put(f"/api/tasks/{row['id']}", json={"status": "待处理"}, headers={"If-Match": str(updated["revision"])}).json()
    assert restored["completed_at"] is None and restored["is_archived"] == 0
    assert client.get("/api/tasks/", params={"archived": True}).json()["total"] == 0
    completed = client.post(f"/api/tasks/{row['id']}/toggle-status", headers={"If-Match": str(restored["revision"])}).json()
    completed = client.post(f"/api/tasks/{row['id']}/toggle-status", headers={"If-Match": str(completed["revision"])}).json()
    current = client.get(f"/api/tasks/{row['id']}").json()
    assert current["status"] == "已完成" and current["completed_at"] != original["completed_at"]
    assert current["is_archived"] == 0


def test_archive_filters_and_pagination_apply_before_limit(client):
    for index in range(23):
        row = task(client, f"归档标题-{index:02d}", status="已完成", priority="高")
        age(row)
    recent = task(client, "归档标题-新", status="已完成", priority="高")
    result = []
    for page in range(1, 4):
        response = client.get("/api/tasks/", params={"archived": True, "priority": "高", "keyword": "归档标题", "page": page, "page_size": 10}).json()
        assert response["total"] == 23 and response["pages"] == 3
        result.extend(row["id"] for row in response["items"])
    assert len(set(result)) == 23 and result == sorted(result, reverse=True)
    assert recent["id"] not in result
    assert client.get("/api/tasks/", params={"archived": True, "priority": "低"}).json()["total"] == 0


def test_backup_import_preserves_aged_completions_and_dates_missing_start_now(client):
    response = client.post("/api/export/import", json={"data": {"tasks": [
        {"title": "无完成时间", "status": "已完成", "created_at": "2000-01-01"},
        {"title": "有完成时间", "status": "已完成", "completed_at": "2000-01-01", "created_at": "1999-01-01"},
    ]}})
    assert response.status_code == 200, response.text
    assert client.get("/api/tasks/").json()["items"][0]["title"] == "无完成时间"
    assert client.get("/api/tasks/", params={"archived": True}).json()["items"][0]["title"] == "有完成时间"
    backup = client.get("/api/export/all").json()
    assert client.post("/api/export/import", json={"data": backup}).status_code == 200
    assert client.get("/api/tasks/").json()["total"] == 2
    assert client.get("/api/tasks/", params={"archived": True}).json()["total"] == 2


def test_legacy_import_missing_completion_gets_full_retention(client):
    response = client.post("/api/tasks/legacy-archive", json={"items": [{"title": "无日期旧归档"}]})
    assert response.status_code == 200
    row = client.get("/api/tasks/").json()["items"][0]
    assert row["completed_at"] is not None and row["is_archived"] == 0
