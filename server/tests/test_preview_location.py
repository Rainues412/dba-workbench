"""Locate search results with the same filters, ordering and pagination as the list."""
import math

import pytest


@pytest.mark.parametrize("module", ["articles", "scripts"])
def test_locate_exact_duplicate_title_across_pages(client, module):
    ids = []
    for _ in range(23):
        created = client.post(f"/api/{module}/", json={"title": "同名文件", "content": "正文不能出现在摘要列表中"})
        assert created.status_code == 200
        ids.append(created.json()["id"])
    # Equal timestamps deliberately exercise the unique ID tie-breaker.
    from backend.database import get_db_ctx
    with get_db_ctx() as conn:
        conn.execute(f"UPDATE {module} SET updated_at = ?", ("2026-10-25 00:00:00",))
        conn.commit()
    for size in [1, 5, 10, 20]:
        response = client.get(f"/api/{module}/", params={"locate_id": ids[0], "page_size": size})
        assert response.status_code == 200
        page = response.json()
        assert page["page"] == math.ceil(23 / size)
        assert page["total"] == 23
        assert ids[0] in [row["id"] for row in page["items"]]
        assert len(page["items"]) <= size
        assert all("content" not in row for row in page["items"])
        normal = client.get(f"/api/{module}/", params={"page": page["page"], "page_size": size}).json()
        assert normal == page
    if module == "articles":
        with get_db_ctx() as conn:
            conn.execute("UPDATE articles SET is_pinned = 1 WHERE id = ?", (ids[0],))
            conn.commit()
        pinned = client.get("/api/articles/", params={"locate_id": ids[0], "page_size": 10}).json()
        assert pinned["page"] == 1 and pinned["items"][0]["id"] == ids[0]


@pytest.mark.parametrize("module,field", [("articles", "category"), ("scripts", "wb_type")])
def test_location_keeps_filters_and_handles_missing_or_invalid_targets(client, module, field):
    target = client.post(f"/api/{module}/", json={"title": "RAC 手册", field: "目标分类"}).json()["id"]
    other = client.post(f"/api/{module}/", json={"title": "其他手册", field: "其他分类"}).json()["id"]
    filtered = client.get(f"/api/{module}/", params={field: "其他分类", "locate_id": target}).json()
    assert [row["id"] for row in filtered["items"]] == [other]
    assert filtered["total"] == 1
    empty = client.get(f"/api/{module}/", params={"keyword": "不存在的标题", "locate_id": target}).json()
    assert empty["items"] == [] and empty["total"] == 0
    favorites = client.get(f"/api/{module}/", params={"favorite_only": 1, "locate_id": target}).json()
    assert favorites["items"] == []
    normal = client.get(f"/api/{module}/").json()
    assert client.get(f"/api/{module}/", params={"locate_id": 999999}).json() == normal
    for value in [0, -1, "invalid", "1 OR 1=1"]:
        assert client.get(f"/api/{module}/", params={"locate_id": value}).status_code == 422
