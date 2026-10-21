import re
import json

import pytest
from playwright.sync_api import sync_playwright

from test_browser_smoke import _api_client, _edge, _login


@pytest.mark.browser
@pytest.mark.parametrize("status", [404, 500])
def test_detail_failure_never_becomes_create_and_retry_uses_put(live_server, status):
    client, csrf = _api_client(live_server)
    original = client.post("/api/scripts/", json={"title": "详情保护", "content": "select 1"}, headers={"X-CSRF-Token": csrf}).json()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page()
            page.set_default_timeout(10_000)
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="脚本库").click()
            pattern = re.compile(r"/api/scripts/\d+$")
            page.route(pattern, lambda route: route.fulfill(status=status, content_type="application/json", body='{"error":{"message":"模拟详情失败"}}'))
            requests = []
            page.on("request", lambda request: requests.append((request.method, request.url)))
            page.get_by_role("button", name="查看/编辑").click()
            dialog = page.get_by_role("dialog")
            dialog.get_by_role("heading", name="编辑脚本库", exact=True).wait_for()
            dialog.get_by_text("详情加载失败，未进入新增模式，请重试", exact=True).wait_for()
            assert dialog.get_by_label("名称", exact=True).count() == 0
            assert dialog.get_by_role("button", name="保存", exact=True).count() == 0
            page.unroute(pattern)
            dialog.get_by_role("button", name="重试", exact=True).click()
            dialog.get_by_label("名称", exact=True).fill("已安全更新")
            with page.expect_request(lambda request: request.method == "PUT" and request.url.endswith(f"/api/scripts/{original['id']}")) as saved:
                dialog.get_by_role("button", name="保存", exact=True).click()
            assert saved.value.headers["if-match"] == str(original["revision"])
            page.get_by_text("已安全更新", exact=True).wait_for()
            assert not any(method == "POST" and "/api/scripts/" in url for method, url in requests)
            assert client.get("/api/scripts/").json()["total"] == 1
        finally:
            browser.close()
            client.close()


@pytest.mark.browser
def test_tasks_filters_complete_restore(live_server):
    client, csrf = _api_client(live_server)
    for title, priority in [("重点任务", "高"), ("普通任务", "低")]:
        client.post("/api/tasks/", json={"title": title, "priority": priority}, headers={"X-CSRF-Token": csrf}).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page()
            page.set_default_timeout(10_000)
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="任务管理").click()
            page.get_by_label("筛选任务优先级").select_option("高")
            page.get_by_text("重点任务", exact=True).wait_for()
            assert page.get_by_text("普通任务", exact=True).count() == 0
            page.get_by_role("button", name="完成", exact=True).click()
            page.get_by_role("button", name="恢复", exact=True).wait_for()
            page.get_by_label("筛选任务状态").select_option("已完成")
            page.get_by_role("button", name="恢复", exact=True).click()
            page.get_by_text("没有任务数据", exact=True).wait_for()
        finally:
            browser.close()
            client.close()


@pytest.mark.browser
def test_backup_dialog_append_and_atomic_error(live_server):
    client, csrf = _api_client(live_server)
    client.post("/api/scripts/", json={"title": "分类备份测试", "wb_type": "备份", "db_type": "Oracle"}, headers={"X-CSRF-Token": csrf}).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        context = browser.new_context(accept_downloads=True)
        try:
            page = context.new_page()
            page.set_default_timeout(10_000)
            _login(page, live_server)
            page.get_by_role("button", name="普通数据备份", exact=True).click()
            dialog = page.get_by_role("dialog")
            dialog.get_by_role("heading", name="普通模块备份与导入", exact=True).wait_for()
            assert dialog.bounding_box()["height"] > 300
            # Download logic has a dedicated frontend unit test. Use the real
            # export endpoint for this import fixture: Playwright 1.48 crashes
            # its Node driver while tearing down current Edge blob downloads.
            backup = client.get("/api/export/all").json()
            assert backup["scripts"][0]["wb_type"] == "备份"
            assert "vault_items" not in backup and "users" not in backup
            page.on("dialog", lambda alert: alert.accept())
            upload = dialog.get_by_label("选择备份文件")
            upload.set_input_files({"name": "roundtrip.json", "mimeType": "application/json", "buffer": json.dumps(backup).encode()})
            dialog.get_by_text(re.compile("待追加：脚本 1 条")).wait_for()
            dialog.get_by_role("button", name="确认追加导入", exact=True).click()
            dialog.get_by_text(re.compile("追加导入完成：.*脚本 1 条")).wait_for()
            rows = client.get("/api/scripts/").json()["items"]
            assert len(rows) == 2 and all(row["wb_type"] == "备份" for row in rows)
            invalid = {"scripts": [{"title": "不得保留"}, {"title": None}]}
            upload.set_input_files({"name": "invalid.json", "mimeType": "application/json", "buffer": json.dumps(invalid).encode()})
            dialog.get_by_text(re.compile("待追加：脚本 2 条")).wait_for()
            dialog.get_by_role("button", name="确认追加导入", exact=True).click()
            dialog.get_by_role("alert").filter(has_text="未写入任何记录").wait_for()
            assert client.get("/api/scripts/").json()["total"] == 2
        finally:
            context.close()
            browser.close()
            client.close()
