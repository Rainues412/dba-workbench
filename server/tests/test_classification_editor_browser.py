import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login, _select_database


@pytest.mark.browser
@pytest.mark.parametrize("module,label,current,target", [
    ("articles", "分类", "安装部署", "性能优化"),
    ("scripts", "类型", "巡检", "备份"),
])
def test_editor_lists_all_categories_in_production(live_server, tmp_path, module, label, current, target):
    client, csrf = _api_client(live_server)
    category_field = "category" if module == "articles" else "wb_type"
    database_field = "wb_db" if module == "articles" else "db_type"
    headers = {"X-CSRF-Token": csrf}
    original = client.post(f"/api/{module}/", json={
        "title": "编辑分类测试", category_field: current, database_field: "Oracle", "content": "原始正文",
    }, headers=headers).json()
    other_category = "跨数据库自定义分类-" + "长名称" * 30
    client.post(f"/api/{module}/", json={
        "title": "其他数据库", category_field: other_category, database_field: "MySQL",
    }, headers=headers).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page()
            page.set_default_timeout(10_000)
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="知识库" if module == "articles" else "脚本库", exact=True).click()
            _select_database(page, "Oracle")
            expect(page.get_by_role("button", name="查看/编辑")).to_have_count(1)
            page.get_by_role("button", name="查看/编辑").click()
            select = page.get_by_role("dialog").get_by_role("combobox", name=label, exact=True)
            expect(select).to_have_value(current)
            assert select.evaluate("element => element.tagName") == "SELECT"
            options = select.locator("option").all_text_contents()
            assert current in options and target in options and other_category in options
            assert len(options) == len(set(options))
            for theme, width in [("light", 1440), ("dark", 1440), ("light", 390), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                select.select_option(other_category)
                expect(select).to_have_attribute("title", other_category)
                assert select.bounding_box()["width"] <= width
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                select.select_option(current)
                select.focus()
                # A retained legacy value is appended after the current taxonomy.
                # Start at the first option before testing keyboard selection.
                select.press("Home")
                select.press("ArrowDown")
                select.press("Enter")
                assert select.input_value() != current
                page.screenshot(path=str(tmp_path / f"{module}-{theme}-{width}.png"))
            select.select_option(target)
            page.get_by_role("dialog").get_by_role("button", name="保存", exact=True).click()
            expect(page.get_by_role("dialog")).to_have_count(0)
            updated = client.get(f"/api/{module}/{original['id']}").json()
            assert updated[category_field] == target
            assert updated["content"] == "原始正文"
            assert updated["revision"] == original["revision"] + 1
        finally:
            browser.close()
            client.close()
