def test_resource_facets_keep_database_counts_and_include_all_kinds(client):
    for name, database, kind in [
        ("安装介质", "Oracle", "安装包"),
        ("安装介质二", "Oracle", "安装包"),
        ("客户端", "Oracle", "软件工具"),
        ("自定义资源", "达梦", "自定义类型"),
    ]:
        response = client.post("/api/resources/", json={"name": name, "wb_db": database, "kind": kind})
        assert response.status_code == 200
    facets = client.get("/api/resources/facets").json()
    assert facets["total"] == 4
    assert {(row["wb_db"], row["kind"]): row["count"] for row in facets["items"]} == {
        ("Oracle", "安装包"): 2, ("Oracle", "软件工具"): 1, ("达梦", "自定义类型"): 1,
    }
    filtered = client.get("/api/resources/", params={"wb_db": "Oracle", "kind": "安装包", "page_size": 1}).json()
    assert filtered["total"] == 2 and len(filtered["items"]) == 1 and filtered["pages"] == 2
    assert filtered["items"][0]["kind"] == "安装包"


def test_empty_resource_facets_remain_compatible(client):
    assert client.get("/api/resources/facets").json() == {"total": 0, "items": []}
