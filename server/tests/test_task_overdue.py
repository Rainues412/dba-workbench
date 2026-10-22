import pytest

from backend.database import get_db_ctx


@pytest.mark.parametrize("date_fields", [{}, {"due_date": None}, {"due_date": ""}, {"due_date": "   "}])
def test_tasks_without_a_deadline_are_not_overdue_in_any_view(client, date_fields):
    customer = client.post("/api/customers/", json={"name": "无截止日期测试客户"}).json()
    created = client.post("/api/tasks/", json={
        "title": "未设置截止日期", "customer_id": customer["id"], **date_fields,
    })
    assert created.status_code == 200
    row = created.json()
    assert row["is_overdue"] == 0
    assert client.get(f"/api/tasks/{row['id']}").json()["is_overdue"] == 0
    assert client.get("/api/tasks/").json()["items"][0]["is_overdue"] == 0
    assert client.get("/api/tasks/", params={"overdue": True}).json()["total"] == 0
    assert client.get("/api/dashboard/stats").json()["task_overdue"] == 0
    assert client.get("/api/dashboard/recent-tasks").json()[0]["is_overdue"] == 0
    assert client.get(f"/api/customers/{customer['id']}").json()["tasks"][0]["is_overdue"] == 0


def test_only_unfinished_tasks_before_today_are_overdue_and_sort_first(client):
    with get_db_ctx() as conn:
        yesterday, today, tomorrow = conn.execute(
            "SELECT date('now', 'localtime', '-1 day'), date('now', 'localtime'), date('now', 'localtime', '+1 day')"
        ).fetchone()
    rows = []
    for title, due_date, status, priority in [
        ("无日期高优先级", "", "进行中", "高"),
        ("昨日到期", yesterday, "待处理", "低"),
        ("今日到期", today, "待处理", "中"),
        ("明日到期", tomorrow, "进行中", "中"),
        ("昨日已完成", yesterday, "已完成", "高"),
    ]:
        response = client.post("/api/tasks/", json={
            "title": title, "due_date": due_date, "status": status, "priority": priority,
        })
        assert response.status_code == 200
        rows.append(response.json())
    assert [row["is_overdue"] for row in rows] == [0, 1, 0, 0, 0]
    listed = client.get("/api/tasks/").json()
    assert listed["items"][0]["id"] == rows[1]["id"]
    overdue = client.get("/api/tasks/", params={"overdue": True}).json()
    assert overdue["total"] == 1 and overdue["items"][0]["id"] == rows[1]["id"]
    assert client.get("/api/dashboard/stats").json()["task_overdue"] == 1
    assert client.get("/api/dashboard/recent-tasks").json()[0]["id"] == rows[1]["id"]


def test_clearing_a_deadline_removes_overdue_without_bypassing_revision(client):
    row = client.post("/api/tasks/", json={"title": "清除截止日期", "due_date": "2000-01-01"}).json()
    assert row["is_overdue"] == 1
    response = client.put(f"/api/tasks/{row['id']}", json={"due_date": ""}, headers={"If-Match": str(row["revision"])})
    assert response.status_code == 200
    updated = response.json()
    assert updated["due_date"] == "" and updated["is_overdue"] == 0
    assert updated["revision"] == row["revision"] + 1
    assert client.get("/api/tasks/", params={"overdue": True}).json()["total"] == 0
    assert client.get("/api/dashboard/stats").json()["task_overdue"] == 0
    assert client.put(f"/api/tasks/{row['id']}", json={"due_date": "2000-01-01"}, headers={"If-Match": str(row["revision"])}).status_code == 409
