"""API contracts used by the restored global-search and directory-import UI."""
from backend.config import Settings


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
