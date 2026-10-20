"""API contracts used by the restored global-search and directory-import UI."""
from backend.config import Settings


def test_global_search_excludes_tasks(client):
    created = client.post("/api/tasks/", json={"title": "global-search-excluded-task"})
    assert created.status_code == 200, created.text
    found = client.get("/api/search/", params={"q": "global-search-excluded-task", "limit": 0}).json()
    assert found["tasks"] == []
    assert all(not records for key, records in found.items() if key != "tasks")


def test_all_searches_match_primary_titles_only_and_escape_wildcards(client):
    created = {
        "scripts": client.post("/api/scripts/", json={"title": "script-title-hit", "description": "secondary-only-token"}),
        "articles": client.post("/api/articles/", json={"title": "article-title-hit", "summary": "secondary-only-token"}),
        "resources": client.post("/api/resources/", json={"name": "resource-title-hit", "notes": "secondary-only-token"}),
        "tasks": client.post("/api/tasks/", json={"title": "task-title-hit", "description": "secondary-only-token"}),
        "customers": client.post("/api/customers/", json={"name": "customer-title-hit", "project_name": "secondary-only-token"}),
    }
    assert all(response.status_code == 200 for response in created.values())

    for module in created:
        assert client.get(f"/api/{module}/", params={"keyword": "secondary-only-token"}).json()["total"] == 0
        assert client.get(f"/api/{module}/", params={"keyword": f"{module[:-1] if module.endswith('s') else module}-title-hit"}).json()["total"] == 1
        assert client.get(f"/api/{module}/", params={"keyword": "%"}).json()["total"] == 0

    global_secondary = client.get("/api/search/", params={"q": "secondary-only-token", "limit": 0}).json()
    assert all(not records for records in global_secondary.values())
    global_wildcard = client.get("/api/search/", params={"q": "%", "limit": 0}).json()
    assert all(not records for records in global_wildcard.values())


def test_ascii_search_matches_word_prefix_without_matching_inside_oracle(client):
    client.post("/api/articles/", json={"title": "Oracle 正式参数"})
    rac = client.post("/api/articles/", json={"title": "Oracle RAC11g 正式参数"}).json()
    client.post("/api/articles/", json={"title": "optimize trace 分析"})

    module_results = client.get("/api/articles/", params={"keyword": "rac"}).json()
    assert [item["id"] for item in module_results["items"]] == [rac["id"]]
    global_results = client.get("/api/search/", params={"q": "rac", "limit": 0}).json()
    assert [item["id"] for item in global_results["articles"]] == [rac["id"]]
    assert client.get("/api/articles/", params={"keyword": "ora"}).json()["total"] == 2


def test_scan_preview_commit_and_search_roundtrip(client, tmp_path, monkeypatch):
    from backend import local_capabilities

    allowed = tmp_path / "allowed" / "MySQL"
    allowed.mkdir(parents=True)
    script = allowed / "roundtrip-mysql.sql"
    script.write_text("SELECT 42;", encoding="utf-8")
    article = allowed / "roundtrip-备份恢复.md"
    article.write_text("# Backup", encoding="utf-8")
    resource = allowed / "roundtrip-package.zip"
    resource.write_bytes(b"test-index-only")
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true",
        "DBA_ALLOWED_ROOTS": str(allowed),
        "DBA_ALLOWED_LOCAL_ACTIONS": "scan",
    }))

    preview = client.post("/api/scan/run", json={"paths": [str(allowed)]})
    assert preview.status_code == 200, preview.text
    items = preview.json()["items"]
    assert {item["kind"] for item in items} == {"script", "article", "resource"}
    assert all(item["db_type"] == "MySQL" for item in items)
    assert client.get("/api/search/", params={"q": "roundtrip"}).json()["scripts"] == []

    committed = client.post("/api/scan/commit", json={"items": items})
    assert committed.status_code == 200, committed.text
    assert committed.json()["imported"] == {"script": 1, "article": 1, "resource": 1, "skipped": 0}
    repeated = client.post("/api/scan/commit", json={"items": items})
    assert repeated.json()["imported"] == {"script": 0, "article": 0, "resource": 0, "skipped": 3}
    assert client.post("/api/scan/run", json={"paths": [str(allowed)]}).json()["items"] == []

    found = client.get("/api/search/", params={"q": "roundtrip"}).json()
    for module in ("scripts", "articles", "resources"):
        assert len(found[module]) == 1
        record = client.get(f"/api/{module}/{found[module][0]['id']}").json()
        assert record["db_type" if module == "scripts" else "wb_db"] == "MySQL"
    assert found["passwords"] == []
    assert script.read_text(encoding="utf-8") == "SELECT 42;"
    assert resource.read_bytes() == b"test-index-only"


def test_scan_requires_action_and_rechecks_allowed_paths(client, tmp_path, monkeypatch):
    from backend import local_capabilities

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.sql"
    outside.write_text("SELECT 1;", encoding="utf-8")
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true",
        "DBA_ALLOWED_ROOTS": str(allowed),
        "DBA_ALLOWED_LOCAL_ACTIONS": "scan",
    }))
    assert client.post("/api/scan/run", json={"paths": [str(tmp_path)]}).status_code == 403
    assert client.post("/api/scan/commit", json={"items": [{"kind": "script", "name": "outside", "path": str(outside)}]}).status_code == 403
    assert client.get("/api/search/", params={"q": "outside"}).json()["scripts"] == []
