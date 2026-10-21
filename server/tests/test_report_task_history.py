def test_overdue_filter_only_returns_unfinished_past_due_tasks(client):
    overdue = client.post("/api/tasks/", json={"title": "逾期任务", "due_date": "2000-01-01"}).json()
    client.post("/api/tasks/", json={"title": "未来任务", "due_date": "2999-01-01"})
    client.post("/api/tasks/", json={"title": "已完成旧任务", "due_date": "2000-01-01", "status": "已完成"})

    result = client.get("/api/tasks/", params={"overdue": "true"}).json()
    assert result["total"] == 1
    assert result["items"][0]["id"] == overdue["id"]
    assert result["items"][0]["is_overdue"] == 1


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
