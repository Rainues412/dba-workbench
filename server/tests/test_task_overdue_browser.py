import re

import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login


@pytest.mark.browser
def test_blank_deadline_create_filter_and_clear_in_production_ui(live_server, tmp_path):
    client, csrf = _api_client(live_server)
    client.post("/api/tasks/", json={"title": "确实逾期", "due_date": "2000-01-01"}, headers={"X-CSRF-Token": csrf}).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(10_000)
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="任务管理", exact=True).click()
            page.get_by_role("button", name="新增", exact=True).click()
            dialog = page.get_by_role("dialog")
            dialog.get_by_label("任务", exact=True).fill("没有截止日期")
            expect(dialog.get_by_label("截止日期", exact=True)).to_have_value("")
            dialog.get_by_role("button", name="保存", exact=True).click()
            expect(dialog).to_have_count(0)
            blank = page.locator("tbody tr").filter(has_text="没有截止日期")
            expect(blank.get_by_text("未设置", exact=True)).to_be_visible()
            expect(blank.locator(".status-danger")).to_have_count(0)
            overdue = page.get_by_role("button", name="仅看逾期", exact=True)
            expect(overdue).to_have_attribute("aria-pressed", "false")
            for theme, width in [("light", 1440), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                expect(blank).not_to_have_class(re.compile(r"\bis-overdue\b"))
                page.screenshot(animations="disabled", path=str(tmp_path / f"blank-deadline-{theme}-{width}.png"))
            page.set_viewport_size({"width": 1440, "height": 1000})
            overdue.click()
            expect(blank).to_have_count(0)
            past = page.locator("tbody tr").filter(has_text="确实逾期")
            expect(past.get_by_text("已逾期", exact=True)).to_be_visible()
            past.get_by_role("button", name="查看/编辑", exact=True).click()
            dialog.get_by_label("截止日期", exact=True).fill("")
            dialog.get_by_role("button", name="保存", exact=True).click()
            expect(dialog).to_have_count(0)
            expect(past).to_have_count(0)
            overdue.click()
            expect(past.get_by_text("未设置", exact=True)).to_be_visible()
            expect(page.locator(".task-row.is-overdue")).to_have_count(0)
        finally:
            browser.close()
            client.close()
