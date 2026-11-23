import re

import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login


@pytest.mark.browser
def test_task_date_picker_layout_keyboard_and_save(live_server, tmp_path):
    client, csrf = _api_client(live_server)
    created = client.post("/api/tasks/", headers={"X-CSRF-Token": csrf}, json={
        "title": "日期选择测试", "due_date": "2026-11-19", "status": "进行中",
    })
    created.raise_for_status()
    task_url = f"/api/tasks/{created.json()['id']}"
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900}, timezone_id="Asia/Shanghai")
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="任务管理", exact=True).click()
            page.get_by_role("button", name="编辑", exact=True).click()
            editor = page.get_by_role("dialog", name="编辑任务", exact=True)
            calendar = page.get_by_role("dialog", name="选择日期", exact=True)
            deadline = editor.get_by_label("截止日期", exact=True)
            expect(deadline).to_have_value("2026-11-19")

            for width, height, theme in [(1440, 900, "light"), (1440, 700, "dark"), (390, 740, "light"), (320, 568, "dark")]:
                page.set_viewport_size({"width": width, "height": height})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                deadline.click()
                expect(calendar).to_be_visible()
                selected = calendar.get_by_role("gridcell", name=re.compile("2026年11月19日"))
                expect(selected).to_have_attribute("aria-selected", "true")
                box = calendar.bounding_box()
                assert box["x"] >= -1 and box["y"] >= -1
                assert box["x"] + box["width"] <= width + 1 and box["y"] + box["height"] <= height + 1
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(animations="disabled", path=str(tmp_path / f"date-picker-{theme}-{width}.png"))
                selected.focus()
                page.keyboard.press("Escape")
                expect(calendar).to_have_count(0)
                expect(editor).to_be_visible()
                expect(deadline).to_be_focused()

            page.set_viewport_size({"width": 1440, "height": 900})
            deadline.press("ArrowDown")
            expect(calendar).to_be_visible()
            deadline.press("ArrowDown")
            expect(calendar.get_by_role("gridcell", name=re.compile("2026年11月19日"))).to_be_focused()
            page.keyboard.press("ArrowRight")
            page.keyboard.press("Enter")
            expect(deadline).to_have_value("2026-11-20")

            deadline.click()
            calendar.get_by_role("button", name="上个月", exact=True).click()
            expect(calendar.get_by_role("combobox", name="月份")).to_have_value("9")
            calendar.get_by_role("combobox", name="年份").select_option("2028")
            calendar.get_by_role("combobox", name="月份").select_option("1")
            calendar.get_by_role("gridcell", name=re.compile("2028年2月29日")).click()
            expect(deadline).to_have_value("2028-02-29")
            editor.get_by_role("button", name="保存", exact=True).click()
            expect(editor).to_have_count(0)
            assert client.get(task_url).json()["due_date"] == "2028-02-29"

            page.get_by_role("button", name="编辑", exact=True).click()
            expect(deadline).to_have_value("2028-02-29")
            deadline.fill("2026-02-30")
            editor.get_by_role("button", name="保存", exact=True).click()
            expect(editor).to_be_visible()
            expect(deadline).to_have_value("2026-02-30")
            assert not deadline.evaluate("input => input.validity.valid")
            assert client.get(task_url).json()["due_date"] == "2028-02-29"

            deadline.click()
            calendar.get_by_role("button", name="今天", exact=True).click()
            expect(deadline).to_have_value(page.evaluate("new Date().toLocaleDateString('sv-SE')"))
            editor.get_by_role("button", name="清除日期", exact=True).click()
            expect(deadline).to_have_value("")
            editor.get_by_role("button", name="保存", exact=True).click()
            expect(editor).to_have_count(0)
            saved = client.get(task_url).json()
            assert saved["due_date"] == "" and saved["is_overdue"] == 0
        finally:
            browser.close()
            client.close()
