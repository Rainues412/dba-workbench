from backend.database import get_db_ctx


def create_customer(client, name, status="活跃", **fields):
    response = client.post("/api/customers/", json={"name": name, "status": status, **fields})
    assert response.status_code == 200, response.text
    return response.json()


def test_customers_follow_names_ascending_regardless_of_status(client):
    for name, status in [("Zulu", "活跃"), ("Alpha", "进行中"), ("beta", "活跃"), ("Aardvark", "已结束"), ("alpha", "活跃"), ("Abacus", "已暂停")]:
        create_customer(client, name, status)
    # Modification times must not override name/status order.
    with get_db_ctx() as conn:
        conn.execute("UPDATE customers SET updated_at = '2999-01-01' WHERE name = 'Zulu'")
        conn.commit()
    result = client.get("/api/customers/").json()
    assert [row["name"] for row in result["items"]] == ["Aardvark", "Abacus", "alpha", "Alpha", "beta", "Zulu"]


def test_customer_sorting_is_stable_across_pages_and_duplicate_names(client):
    statuses = ["活跃", "进行中", "已暂停", "已结束"]
    records = [create_customer(client, f"客户-{index:02d}", statuses[index % 4]) for index in reversed(range(15))]
    records += [create_customer(client, "客户-00")]
    expected = sorted(records, key=lambda row: (row["name"].lower(), -row["id"]))
    found = []
    for page in range(1, 5):
        result = client.get("/api/customers/", params={"page": page, "page_size": 4}).json()
        assert result["total"] == 16 and result["pages"] == 4
        found.extend(row["id"] for row in result["items"])
    assert found == [row["id"] for row in expected]
    assert len(set(found)) == 16


def test_name_sort_respects_status_and_customer_or_project_name_search(client):
    active = create_customer(client, "B 客户", notes="完整备注")
    paused = create_customer(client, "A 客户", "已暂停")
    create_customer(client, "C 客户", "已暂停")
    create_customer(client, "D 公司", project_name="客户", notes="客户")
    result = client.get("/api/customers/", params={"keyword": "客户", "status": "已暂停"}).json()
    assert [row["name"] for row in result["items"]] == ["A 客户", "C 客户"]
    response = client.put(f"/api/customers/{paused['id']}", json={"status": "活跃"}, headers={"If-Match": str(paused["revision"])})
    assert response.status_code == 200
    result = client.get("/api/customers/", params={"keyword": "客户"}).json()
    assert [row["name"] for row in result["items"]] == ["A 客户", "B 客户", "C 客户", "D 公司"]
    assert client.get(f"/api/customers/{active['id']}").json()["notes"] == "完整备注"


def test_locate_customer_uses_filtered_order_without_changing_totals(client):
    records = [
        create_customer(client, f"客户 {i}", project_name="迁移" if i % 2 else "巡检")
        for i in range(7)
    ]
    result = client.get("/api/customers/", params={"page_size": 2, "locate_id": records[5]["id"]}).json()
    assert (result["page"], result["total"]) == (3, 7)
    assert [row["id"] for row in result["items"]] == [records[4]["id"], records[5]["id"]]
    result = client.get("/api/customers/", params={"keyword": "迁移", "page_size": 2, "locate_id": records[5]["id"]}).json()
    assert (result["page"], result["total"]) == (2, 3)
    assert [row["id"] for row in result["items"]] == [records[5]["id"]]
    result = client.get("/api/customers/", params={"keyword": "迁移", "page_size": 2, "locate_id": records[6]["id"]}).json()
    assert (result["page"], result["total"]) == (1, 3)
    assert [row["id"] for row in result["items"]] == [records[1]["id"], records[3]["id"]]
