"""Category suggestions use only an isolated vault with synthetic entries."""
import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import OWNER, _api_client, _edge, _login


@pytest.mark.browser
def test_vault_category_suggestions_and_free_entry(live_server, tmp_path):
    client, _ = _api_client(live_server)
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="密码保险箱", exact=True).click()
            page.get_by_placeholder("登录密码", exact=True).fill(OWNER["password"])
            page.get_by_role("button", name="验证 30 分钟", exact=True).click()
            page.get_by_text("已验证", exact=True).wait_for()
            page.get_by_label("保险箱主密码", exact=True).fill("test-only-master-password")
            page.get_by_label("确认主密码", exact=True).fill("test-only-master-password")
            page.get_by_role("button", name="创建保险箱", exact=True).click()
            page.get_by_role("heading", name="请备份管理员恢复密钥").wait_for(timeout=20_000)

            for name, category in [("分类验收一", "工作"), ("分类验收二", "个人")]:
                page.get_by_role("button", name="新增条目", exact=True).click()
                editor = page.get_by_role("dialog", name="新增保险箱条目", exact=True)
                editor.get_by_label("名称或备注", exact=True).fill(name)
                editor.get_by_label("密码", exact=True).fill("test-only-entry-password")
                editor.get_by_role("combobox", name="分类", exact=True).fill(category)
                editor.get_by_role("button", name="保存", exact=True).click()
                expect(editor).to_have_count(0)
                expect(page.get_by_role("heading", name=name, exact=True)).to_be_visible()

            # A list filter must not restrict the editor's suggestions.
            page.get_by_role("group", name="保险箱分类分组").get_by_role("button", name="工作，1 条", exact=True).click()
            page.get_by_role("button", name="新增条目", exact=True).click()
            editor = page.get_by_role("dialog", name="新增保险箱条目", exact=True)
            category = editor.get_by_role("combobox", name="分类", exact=True)
            expect(category).to_have_value("")
            editor.get_by_role("button", name="选择已有分类", exact=True).click()
            expect(editor.get_by_role("option")).to_have_text(["个人", "工作"])
            category.focus()
            category.press("ArrowDown")
            category.press("Enter")
            expect(category).to_have_value("个人")
            expect(editor).to_be_visible()
            editor.get_by_role("button", name="取消", exact=True).click()

            card = page.locator(".vault-card").filter(has=page.get_by_role("heading", name="分类验收一", exact=True))
            card.get_by_role("button", name="编辑", exact=True).click()
            editor = page.get_by_role("dialog", name="编辑保险箱条目", exact=True)
            category = editor.get_by_role("combobox", name="分类", exact=True)
            expect(category).to_have_value("工作")
            editor.get_by_role("button", name="选择已有分类", exact=True).click()
            expect(editor.get_by_role("option")).to_have_text(["个人", "工作"])
            editor.get_by_role("option", name="个人", exact=True).click()
            expect(category).to_have_value("个人")
            category.fill("测试新分类")
            expect(editor.get_by_text("无匹配分类，可直接输入新分类", exact=True)).to_be_visible()
            editor.get_by_role("button", name="保存", exact=True).click()
            expect(editor).to_have_count(0)
            page.get_by_role("group", name="保险箱分类分组").get_by_role("button", name="全部分类，2 条", exact=True).click()
            expect(page.get_by_role("group", name="保险箱分类分组").get_by_role("button", name="测试新分类，1 条", exact=True)).to_be_visible()
            page.get_by_role("button", name="新增条目", exact=True).click()
            editor = page.get_by_role("dialog", name="新增保险箱条目", exact=True)
            category = editor.get_by_role("combobox", name="分类", exact=True)
            editor.get_by_role("button", name="选择已有分类", exact=True).click()
            expect(editor.get_by_role("option")).to_have_count(2)
            expect(editor.get_by_role("option", name="个人", exact=True)).to_be_visible()
            expect(editor.get_by_role("option", name="测试新分类", exact=True)).to_be_visible()
            category.fill("测试新分类")
            for width, theme in [(1440, "light"), (1440, "dark"), (390, "light"), (390, "dark")]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                category.focus()
                expect(category).to_be_focused()
                if category.get_attribute("aria-expanded") == "true":
                    editor.get_by_role("button", name="选择已有分类", exact=True).click()
                editor.get_by_role("button", name="选择已有分类", exact=True).click()
                expect(editor.get_by_role("option")).to_have_count(2)
                menu_bounds = editor.get_by_role("listbox").bounding_box()
                input_bounds = category.bounding_box()
                assert abs(menu_bounds["x"] - input_bounds["x"]) < 1
                assert abs(menu_bounds["width"] - input_bounds["width"]) < 1
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                editor.screenshot(path=str(tmp_path / f"category-{width}-{theme}.png"))
            editor.get_by_role("button", name="取消", exact=True).click()
        finally:
            browser.close()
            client.close()
