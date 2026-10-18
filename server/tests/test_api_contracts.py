from __future__ import annotations

from fastapi.testclient import TestClient


def test_typed_client_core_contracts(client: TestClient) -> None:
    cases = [
        ("/api/scripts/", {"title": "contract script"}, {"id", "title", "revision", "updated_at"}),
        ("/api/articles/", {"title": "contract article"}, {"id", "title", "revision", "updated_at"}),
        ("/api/resources/", {"name": "contract resource"}, {"id", "name", "revision", "updated_at"}),
        ("/api/tasks/", {"title": "contract task"}, {"id", "title", "revision", "updated_at"}),
        ("/api/customers/", {"name": "contract customer"}, {"id", "name", "revision", "updated_at"}),
    ]
    for path, payload, required in cases:
        created = client.post(path, json=payload)
        assert created.status_code == 200, created.text
        assert required.issubset(created.json())
        listing = client.get(path, params={"page": 1, "page_size": 20})
        assert listing.status_code == 200
        assert {"total", "items", "page", "page_size", "pages", "has_next", "has_previous"}.issubset(listing.json())
        assert required.issubset(listing.json()["items"][0])


def test_list_contract_never_includes_large_bodies(client: TestClient) -> None:
    client.post("/api/scripts/", json={"title": "body", "content": "script body"})
    client.post("/api/articles/", json={"title": "body", "content": "article body"})
    assert "content" not in client.get("/api/scripts/").json()["items"][0]
    assert "content" not in client.get("/api/articles/").json()["items"][0]
