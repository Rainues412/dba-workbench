from backend.database import get_db_ctx
from backend.routers.export_import import _TABLE_COLS


def test_backup_import_covers_every_exported_business_column(client):
    with get_db_ctx() as conn:
        for table, meta in _TABLE_COLS.items():
            actual = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert actual - {"id", "revision"} == set(meta["cols"]) | set(meta["fk"])


def test_backup_roundtrip_preserves_business_fields_and_relationships(client):
    backup = {
        "customers": [{"id": 1, "name": "客户", "wb_person": "张三", "wb_contact": "电话", "created_at": "2020-01-01"}],
        "scripts": [{"id": 2, "title": "脚本", "wb_type": "备份", "db_type": "Oracle", "version": 3}],
        "script_versions": [{"id": 3, "script_id": 2, "content": "select 1", "version": 2}],
        "articles": [{"id": 4, "title": "文档", "wb_db": "Redis", "view_count": 8, "is_pinned": 1}],
        "resources": [{"id": 5, "name": "工具", "wb_db": "PostgreSQL", "version": "v2.0-beta"}],
        "tasks": [{"id": 6, "title": "已完成", "customer_id": 1, "completed_at": "2020-01-02", "is_overdue": 1}],
        "contacts": [{"id": 7, "name": "李四", "customer_id": 1}],
        "communications": [{"id": 8, "customer_id": 1, "date": "2020-01-01", "content": "联系"}],
    }
    assert client.post("/api/export/import", json={"data": backup}).status_code == 200
    exported = client.get("/api/export/all").json()
    assert client.post("/api/export/import", json={"data": exported}).json()["ok"] is True
    after = client.get("/api/export/all").json()
    for table, rows in backup.items():
        original, restored = after[table]
        for field, value in rows[0].items():
            if field != "id" and not field.endswith("_id"):
                assert original[field] == restored[field] == value
        if table in ("tasks", "contacts", "communications"):
            assert restored["customer_id"] == after["customers"][1]["id"]
        if table == "script_versions":
            assert restored["script_id"] == after["scripts"][1]["id"]


def test_legacy_backup_omitted_fields_use_schema_defaults(client):
    response = client.post("/api/export/import", json={"data": {
        "scripts": [{"title": "旧脚本"}], "articles": [{"title": "旧知识"}],
        "customers": [{"name": "旧客户"}], "resources": [{"name": "旧资源"}],
    }})
    assert response.status_code == 200, response.text
    data = client.get("/api/export/all").json()
    assert data["scripts"][0]["wb_type"] == "其他"
    assert data["scripts"][0]["version"] == 1
    assert data["articles"][0]["wb_db"] == data["resources"][0]["wb_db"] == "通用"
    assert data["customers"][0]["wb_person"] == data["customers"][0]["wb_contact"] == ""


def test_import_error_rolls_back_every_table_and_never_links_existing_parent(client):
    assert client.post("/api/export/import", json={"data": {"customers": [{"id": 1, "name": "原客户"}]}}).status_code == 200
    response = client.post("/api/export/import", json={"data": {
        "scripts": [{"id": 5, "title": "不得保留"}],
        "tasks": [{"title": "错误关系", "customer_id": 1}],
    }})
    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["imported"] == {}
    with get_db_ctx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM scripts").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 1


def test_malformed_and_duplicate_backup_rows_fail_without_partial_writes(client):
    for payload in ({}, {"scripts": {}}, {"scripts": [None]}, {"scripts": [{"id": 1, "title": "a"}, {"id": 1, "title": "b"}]}, {"scripts": [{"title": "a"}, {"title": "b", "version": "bad"}]}):
        response = client.post("/api/export/import", json={"data": payload})
        assert response.status_code == 400, response.text
        assert response.json()["ok"] is False
        assert client.get("/api/export/all").json()["scripts"] == []
