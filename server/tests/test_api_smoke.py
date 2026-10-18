from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient


def test_home_and_empty_dashboard(client: TestClient) -> None:
    home = client.get("/")
    assert home.status_code == 200
    assert "<title>DBA 工作台</title>" in home.text
    assert '<script src="/static/workbench.js"></script>' in home.text
    assert "object-src 'none'" in home.headers["content-security-policy"]
    assert "base-uri 'none'" in home.headers["content-security-policy"]
    assert home.headers["x-content-type-options"] == "nosniff"

    stats = client.get("/api/dashboard/stats")
    assert stats.status_code == 200
    assert stats.json() == {
        "script_count": 0,
        "article_count": 0,
        "task_total": 0,
        "task_pending": 0,
        "task_overdue": 0,
        "customer_count": 0,
        "resource_count": 0,
        "password_count": 0,
    }


def test_script_crud_and_version_history(client: TestClient) -> None:
    created = client.post(
        "/api/scripts/",
        json={
            "title": "Backup smoke script",
            "description": "created by isolated test",
            "db_type": "Oracle",
            "wb_type": "备份",
            "tags": "smoke,isolated",
            "content": "select 1 from dual;",
            "file_path": r"D:\tests\backup.sql",
        },
    )
    assert created.status_code == 200
    script_id = created.json()["id"]

    listing = client.get("/api/scripts/?page_size=500")
    assert listing.status_code == 200
    assert listing.json()["page_size"] == 200
    assert listing.json()["total"] == 1
    assert "content" not in listing.json()["items"][0]

    detail = client.get(f"/api/scripts/{script_id}")
    assert detail.status_code == 200
    assert detail.json()["content"] == "select 1 from dual;"
    assert detail.json()["version"] == 1

    updated = client.put(
        f"/api/scripts/{script_id}",
        json={"title": "Backup smoke script v2", "content": "select 2 from dual;"},
        headers={"If-Match": str(detail.json()["revision"])},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2

    versioned = client.get(f"/api/scripts/{script_id}")
    assert versioned.json()["versions"][0]["version"] == 1

    deleted = client.delete(
        f"/api/scripts/{script_id}",
        headers={"If-Match": str(updated.json()["revision"])},
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    assert client.get(f"/api/scripts/{script_id}").status_code == 404


def test_article_list_and_detail_contract(client: TestClient) -> None:
    created = client.post(
        "/api/articles/",
        json={
            "title": "Recovery note",
            "summary": "isolated article",
            "content": "full body must only be returned by detail",
            "category": "备份恢复",
            "tags": "smoke",
            "wb_db": "PostgreSQL",
        },
    )
    assert created.status_code == 200
    article_id = created.json()["id"]

    listing = client.get("/api/articles/?page_size=1000")
    assert listing.status_code == 200
    assert listing.json()["page_size"] == 200
    assert "content" not in listing.json()["items"][0]

    detail = client.get(f"/api/articles/{article_id}")
    assert detail.status_code == 200
    assert detail.json()["content"] == "full body must only be returned by detail"
    assert detail.json()["view_count"] == 1


def test_task_validation_and_crud(client: TestClient) -> None:
    invalid = client.post(
        "/api/tasks/",
        json={"title": "invalid customer", "customer_id": 999999},
    )
    assert invalid.status_code == 400

    created = client.post(
        "/api/tasks/",
        json={"title": "Test backup", "priority": "高", "status": "待处理"},
    )
    assert created.status_code == 200
    task_id = created.json()["id"]

    updated = client.put(
        f"/api/tasks/{task_id}",
        json={"status": "已完成"},
        headers={"If-Match": str(created.json()["revision"])},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "已完成"
    assert updated.json()["completed_at"] is not None

    assert client.delete(
        f"/api/tasks/{task_id}",
        headers={"If-Match": str(updated.json()["revision"])},
    ).json() == {"ok": True}


def test_resource_crud(client: TestClient) -> None:
    created = client.post(
        "/api/resources/",
        json={
            "name": "PostgreSQL package",
            "kind": "安装包",
            "path": r"D:\packages\postgresql.exe",
            "version": "test",
            "wb_db": "PostgreSQL",
        },
    )
    assert created.status_code == 200
    resource_id = created.json()["id"]

    listing = client.get("/api/resources/?wb_db=PostgreSQL")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["name"] == "PostgreSQL package"

    assert client.delete(
        f"/api/resources/{resource_id}",
        headers={"If-Match": str(created.json()["revision"])},
    ).json() == {"ok": True}


def test_optimistic_concurrency_rejects_missing_and_stale_revision(client: TestClient) -> None:
    created = client.post("/api/articles/", json={"title": "Concurrent edit"})
    assert created.status_code == 200
    article = created.json()
    path = f"/api/articles/{article['id']}"

    missing = client.put(path, json={"summary": "no precondition"})
    assert missing.status_code == 428

    first = client.put(
        path,
        json={"summary": "first writer"},
        headers={"If-Match": str(article["revision"])},
    )
    assert first.status_code == 200
    assert first.json()["revision"] == article["revision"] + 1

    stale = client.put(
        path,
        json={"summary": "stale writer"},
        headers={"If-Match": str(article["revision"])},
    )
    assert stale.status_code == 409
    assert client.get(path).json()["summary"] == "first writer"

    stale_delete = client.delete(
        path,
        headers={"If-Match": str(article["revision"])},
    )
    assert stale_delete.status_code == 409


def test_pagination_and_detail_after_two_hundred_rows(client: TestClient, isolated_app) -> None:
    _, test_db = isolated_app
    with sqlite3.connect(test_db) as conn:
        conn.executemany(
            """INSERT INTO scripts (title, content, db_type, wb_type)
               VALUES (?, ?, 'Oracle', '巡检')""",
            [(f"Paged script {index:03d}", f"body {index:03d}") for index in range(205)],
        )

    page = client.get("/api/scripts/?page=5&page_size=50&db_type=Oracle&wb_type=巡检")
    assert page.status_code == 200
    data = page.json()
    assert data["total"] == 205
    assert data["page"] == 5
    assert data["pages"] == 5
    assert data["has_previous"] is True
    assert data["has_next"] is False
    assert len(data["items"]) == 5
    assert "content" not in data["items"][0]

    record = data["items"][0]
    detail = client.get(f"/api/scripts/{record['id']}")
    assert detail.status_code == 200
    original_body = detail.json()["content"]
    updated = client.put(
        f"/api/scripts/{record['id']}",
        json={"title": "Edited beyond row 200"},
        headers={"If-Match": str(record["revision"])},
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == original_body
