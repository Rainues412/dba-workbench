import sqlite3

import backend.migrations as migrations


def test_customer_upgrade_keeps_legacy_fields_and_relations(tmp_path, monkeypatch):
    # Build a real version-six database, then run the forward upgrade.
    path = tmp_path / "before-upgrade.db"
    files = migrations._migration_files()
    with monkeypatch.context() as patch:
        patch.setattr(migrations, "_migration_files", lambda: files[:6])
        migrations.migrate(path)
    with sqlite3.connect(path) as conn:
        conn.execute("""INSERT INTO customers(name, project_name, group_name, wb_person, wb_contact, notes)
                        VALUES ('示例客户', '数据库升级', '升级协作群', '张三', '企业微信', '原始备注')""")
        conn.execute("INSERT INTO contacts(customer_id, name) VALUES (1, '李四')")
        conn.execute("INSERT INTO communications(customer_id, date, content) VALUES (1, '2026-01-01', '历史记录')")
        conn.execute("INSERT INTO tasks(customer_id, title) VALUES (1, '已有任务')")
        before = conn.execute("SELECT * FROM customers").fetchone()
    migrations.migrate(path)
    migrations.migrate(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT * FROM customers").fetchone() == (*before, None)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT customer_id, name FROM contacts").fetchall() == [(1, "李四")]
        assert conn.execute("SELECT customer_id, content FROM communications").fetchall() == [(1, "历史记录")]
        assert conn.execute("SELECT customer_id, title FROM tasks").fetchall() == [(1, "已有任务")]


def test_profile_save_revision_and_backup_round_trip(client):
    legacy = {"name": "示例客户", "group_name": "客户公共群", "wb_contact": "企业微信", "wb_person": "王经理", "notes": "原始备注"}
    created = client.post("/api/customers/", json=legacy).json()
    profile = created["project_profile"]
    assert profile == {"chat": {"name": "客户公共群", "platform": "企业微信"}, "owners": [{"name": "王经理", "label": ""}], "projects": []}
    cid = created["id"]
    url = f"/api/customers/{cid}"
    client.post(f"{url}/communications", json={"date": "2026-01-01", "content": "历史记录"}).raise_for_status()
    profile["projects"] = [
        {"name": "数据库迁移", "chat": {"name": "迁移群", "platform": "钉钉"}, "owners": [
            {"name": "张三", "label": "资源开通"}, {"name": "李四", "label": "技术支持"},
        ]},
        {"name": "例行巡检", "chat": {"name": "", "platform": ""}, "owners": []},
    ]
    headers = {"If-Match": str(created["revision"])}
    assert client.put(url, json={"project_profile": {"projects": [{"name": "   "}]}}, headers=headers).status_code == 422
    response = client.put(url, json={"name": legacy["name"], "project_profile": profile}, headers=headers)
    assert response.status_code == 200, response.text
    assert client.put(url, json={"project_profile": {}}, headers=headers).status_code == 409
    assert client.post("/api/customers/", json={"name": "示例客户 ", "project_profile": {}}).status_code == 409
    assert client.get("/api/customers/").json()["items"][0]["project_profile"] == profile
    saved = client.get(url).json()
    assert all(saved[key] == value for key, value in legacy.items())
    assert saved["communications"][0]["content"] == "历史记录"
    backup = client.get("/api/export/all").json()
    client.post("/api/export/import", json={"data": backup}).raise_for_status()
    restored = next(row for row in client.get("/api/customers/").json()["items"] if row["id"] != cid)
    assert restored["project_profile"] == profile
    assert client.get(f"/api/customers/{restored['id']}").json()["communications"][0]["content"] == "历史记录"


def test_search_finds_current_project_names_and_preserves_customer_pagination(client):
    legacy = client.post("/api/customers/", json={"name": "A 公司", "project_name": "电鳗数据库迁移"}).raise_for_status().json()
    current = client.post("/api/customers/", json={
        "name": "B 公司", "project_name": "过期项目",
        "project_profile": {"projects": [
            {"name": "迁移演练"}, {"name": "迁移验收"}, {"name": "巡检", "chat": {"name": "仅群聊"}},
        ]},
    }).raise_for_status().json()

    for page, record, titles in [(1, legacy, ["电鳗数据库迁移"]), (2, current, ["迁移演练", "迁移验收"])]:
        result = client.get("/api/customers/", params={"keyword": "迁移", "page": page, "page_size": 1}).raise_for_status().json()
        assert result["total"] == 2 and result["pages"] == 2
        assert [item["id"] for item in result["items"]] == [record["id"]]
        assert result["items"][0]["matched_projects"] == titles

    found = client.get("/api/search/", params={"q": "迁移"}).raise_for_status().json()
    assert not found["customers"]
    assert {(row["id"], row["customer_name"], row["title"]) for row in found["customer_projects"]} == {
        (legacy["id"], "A 公司", "电鳗数据库迁移"), (current["id"], "B 公司", "迁移演练"), (current["id"], "B 公司", "迁移验收"),
    }
    for query in ["过期项目", "仅群聊"]:
        assert client.get("/api/customers/", params={"keyword": query}).json()["total"] == 0
        assert not client.get("/api/search/", params={"q": query}).json()["customer_projects"]
    for query in ["电", "电鳗"]:
        assert client.get("/api/customers/", params={"keyword": query}).json()["items"][0]["id"] == legacy["id"]
        assert client.get("/api/search/", params={"q": query}).json()["customer_projects"][0]["id"] == legacy["id"]
