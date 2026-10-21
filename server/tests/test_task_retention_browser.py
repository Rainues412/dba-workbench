import sqlite3

import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login


@pytest.mark.browser
def test_completed_order_automatic_archive_and_restore(live_server, isolated_app, tmp_path):
    client, csrf = _api_client(live_server)
    headers = {"X-CSRF-Token": csrf}
    rows = []
    for title, priority in [("最早创建", "高"), ("较晚创建", "中"), ("最新创建", "低")]:
        response = client.post("/api/tasks/", json={"title": title, "description": "任务说明完整保留", "status": "已完成", "priority": priority}, headers=headers)
        response.raise_for_status()
        rows.append(response.json())
    _, test_db = isolated_app
    with sqlite3.connect(test_db) as conn:
        for index, row in enumerate(rows):
            conn.execute("UPDATE tasks SET created_at = ? WHERE id = ?", (f"2020-01-0{index + 1}", row["id"]))
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(10_000)
            page.clock.install()
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="任务管理", exact=True).click()
            expect(page.get_by_role("button", name="旧任务归档", exact=True)).to_have_count(0)
            expect(page.get_by_label("筛选任务状态").locator("option")).to_have_text(["全部状态", "待处理", "进行中", "已完成"])
            page.get_by_label("筛选任务状态").select_option("已完成")
            titles = page.locator(".task-title-cell strong")
            expect(titles).to_have_text(["最新创建", "较晚创建", "最早创建"])
            expect(page.locator(".data-panel")).to_have_attribute("aria-busy", "false")
            page.screenshot(path=str(tmp_path / "initial-tasks.png"))
            expect(page.locator("thead th").filter(has_text="创建时间")).to_be_visible()
            # Move completions across the threshold while the page stays open.
            with sqlite3.connect(test_db) as conn:
                conn.execute("UPDATE tasks SET completed_at = datetime('now', '-16 days') WHERE id IN (?, ?)", (rows[0]["id"], rows[2]["id"]))
            page.clock.fast_forward(61_000)
            expect(titles).to_have_text(["较晚创建"])
            page.get_by_role("button", name="查看归档", exact=True).click()
            expect(titles).to_have_text(["最新创建", "最早创建"])
            expect(page.get_by_role("heading", name="归档任务", exact=True)).to_be_visible()
            expect(page.get_by_label("筛选任务状态")).to_have_count(0)
            expect(page.get_by_role("button", name="新增", exact=True)).to_have_count(0)
            expect(page.locator(".task-state-cell .badge")).to_have_text(["已归档", "已归档"])
            for theme, width in [("light", 1440), ("dark", 1440), ("light", 390), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.get_by_role("button", name="返回任务列表", exact=True).focus()
                expect(page.get_by_role("button", name="返回任务列表", exact=True)).to_be_focused()
                page.screenshot(path=str(tmp_path / f"archive-{theme}-{width}.png"))
            row = page.locator(".task-table tbody tr").filter(has_text="最新创建")
            row.get_by_role("button", name="查看/编辑", exact=True).click()
            expect(page.get_by_role("dialog").locator('textarea[name="description"]')).to_have_value("任务说明完整保留")
            page.get_by_role("dialog").get_by_role("button", name="取消", exact=True).click()
            row.get_by_role("button", name="恢复", exact=True).click()
            expect(titles).to_have_text(["最早创建"])
            page.get_by_role("button", name="返回任务列表", exact=True).click()
            page.get_by_label("筛选任务状态").select_option("待处理")
            expect(titles).to_have_text(["最新创建"])
            page.get_by_role("button", name="完成", exact=True).click()
            expect(page.get_by_text("没有任务数据", exact=True)).to_be_visible()
            current = client.get(f"/api/tasks/{rows[2]['id']}").json()
            assert current["is_archived"] == 0 and current["completed_at"] is not None
        finally:
            browser.close()
            client.close()
