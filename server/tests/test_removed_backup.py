def test_ordinary_backup_routes_are_unavailable(client):
    assert client.get("/api/export/all").status_code == 404
    assert client.post("/api/export/import", json={"data": {"scripts": [{"title": "不得写入"}]}}).status_code == 404
    assert client.get("/api/scripts/").json()["total"] == 0
