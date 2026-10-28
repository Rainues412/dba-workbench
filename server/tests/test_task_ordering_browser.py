"""Verify task-management ordering in the built UI using isolated data."""
import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login


@pytest.mark.browser
def test_task_management_uses_dashboard_order(live_server, tmp_path):
    client, csrf = _api_client(live_server)
    cases = [
        ("低进行中逾期", "低", "进行中", "2000-01-01"),
        ("高待处理逾期", "高", "待处理", "2000-01-01"),
        ("高待处理未来", "高", "待处理", "2098-01-01"),
        ("高进行中未来", "高", "进行中", "2099-01-01"),
        ("中进行中无日期", "中", "进行中", None),
        ("高进行中逾期", "高", "进行中", "2001-01-01"),
        ("高进行中无日期", "高", "进行中", None),
    ]
    for title, priority, status, due_date in cases:
        client.post("/api/tasks/", headers={"X-CSRF-Token": csrf}, json={
            "title": title, "priority": priority, "status": status, "due_date": due_date,
        }).raise_for_status()
    client.post("/api/tasks/", headers={"X-CSRF-Token": csrf}, json={
        "title": "已完成任务", "priority": "高", "status": "已完成",
    }).raise_for_status()
    expected = ["高进行中逾期", "高待处理逾期", "低进行中逾期", "高进行中未来", "高进行中无日期", "高待处理未来", "中进行中无日期"]
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _login(page, live_server)
            expect(page.locator(".task-copy strong")).to_have_text(expected)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="任务管理", exact=True).click()
            titles = page.locator(".task-title-cell strong")
            expect(titles).to_have_text(expected + ["已完成任务"])
            for width, theme in [(1440, "light"), (390, "dark")]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                expect(titles).to_have_text(expected + ["已完成任务"])
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(tmp_path / f"task-order-{width}-{theme}.png"))
            page.get_by_label("筛选任务状态").select_option("进行中")
            expect(titles).to_have_text([title for title in expected if "进行中" in title])
            page.get_by_label("筛选任务状态").select_option("")
            page.get_by_role("button", name="仅看逾期", exact=True).click()
            expect(titles).to_have_text(expected[:3])
        finally:
            browser.close()
            client.close()
