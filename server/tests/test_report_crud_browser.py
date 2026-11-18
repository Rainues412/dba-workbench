import re

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
def test_topbar_has_no_ordinary_backup_entry(live_server):
    client, _ = _api_client(live_server)
    client.close()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page()
            page.set_default_timeout(10_000)
            _login(page, live_server)
            topbar = page.get_by_role("banner")
            topbar.get_by_placeholder("全局搜索标题", exact=True).wait_for()
            assert topbar.get_by_role("button", name="普通数据备份", exact=True).count() == 0
            assert topbar.get_by_role("button", name=re.compile("切换到.*模式")).count() == 1
        finally:
            browser.close()
