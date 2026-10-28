"""Task list ordering must match the dashboard, including before pagination."""


def test_task_order_matches_dashboard_across_pages_and_filters(client):
    rows = {}
    cases = [
        ("低进行中逾期", "低", "进行中", "2000-01-01"),
        ("高待处理逾期", "高", "待处理", "2000-01-01"),
        ("中待处理", "中", "待处理", None),
        ("高待处理未来", "高", "待处理", "2098-01-01"),
        ("高进行中未来", "高", "进行中", "2099-01-01"),
        ("中进行中", "中", "进行中", None),
        ("高进行中逾期", "高", "进行中", "2001-01-01"),
        ("高进行中空日期", "高", "进行中", ""),
        ("高进行中无日期", "高", "进行中", None),
    ]
    for title, priority, status, due_date in cases:
        response = client.post("/api/tasks/", json={"title": title, "priority": priority, "status": status, "due_date": due_date})
        assert response.status_code == 200
        rows[title] = response.json()
    expected = ["高进行中逾期", "高待处理逾期", "低进行中逾期", "高进行中未来", "高进行中无日期", "高进行中空日期", "高待处理未来", "中进行中", "中待处理"]
    assert [row["title"] for row in client.get("/api/dashboard/recent-tasks").json()] == expected
    actual = []
    for page in range(1, 4):
        response = client.get("/api/tasks/", params={"page": page, "page_size": 3})
        assert response.status_code == 200
        result = response.json()
        assert result["total"] == 9 and result["pages"] == 3
        actual.extend(row["title"] for row in result["items"])
    assert actual == expected
    for filters in [{"status": "待处理"}, {"status": "进行中"}, {"priority": "高"}, {"overdue": True}]:
        filtered = client.get("/api/tasks/", params=filters).json()["items"]
        assert [row["title"] for row in filtered] == [title for title in expected if all(
            rows[title][key if key != "overdue" else "is_overdue"] == value for key, value in filters.items()
        )]
    changed = rows["中待处理"]
    response = client.put(f"/api/tasks/{changed['id']}", headers={"If-Match": str(changed["revision"])}, json={"priority": "高", "status": "进行中"})
    assert response.status_code == 200
    expected.remove("中待处理")
    expected.insert(6, "中待处理")  # Same-priority in-progress tasks stay ahead of pending tasks.
    assert [row["title"] for row in client.get("/api/tasks/").json()["items"]] == expected
