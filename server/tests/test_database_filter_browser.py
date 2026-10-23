import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login, _select_database


@pytest.mark.browser
@pytest.mark.parametrize("module,label", [("articles", "知识库"), ("scripts", "脚本库"), ("resources", "资源中心")])
def test_database_icons_and_keyboard_filter(live_server, tmp_path, module, label):
    client, csrf = _api_client(live_server)
    headers = {"X-CSRF-Token": csrf}
    db_field = "db_type" if module == "scripts" else "wb_db"
    title_field = "name" if module == "resources" else "title"
    category_field = "wb_type" if module == "scripts" else "kind" if module == "resources" else "category"
    category_label = "脚本类型" if module == "scripts" else "资源类型" if module == "resources" else "文档分类"
    category = "巡检" if module == "scripts" else "安装包" if module == "resources" else "安装部署"
    custom = "自定义数据库-" + "长名称" * 18
    custom_category = "自定义分类-" + "长类别" * 18
    for database in ["Oracle", "MySQL", "MongoDB", "其他", custom]:
        client.post(f"/api/{module}/", json={title_field: f"{database}记录", db_field: database, category_field: custom_category if database == custom else category}, headers=headers).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name=label, exact=True).click()
            combo = page.get_by_role("combobox", name="筛选数据库")
            _select_database(page, "Oracle")
            group = page.get_by_role("group", name="数据库分类")
            expect(group.get_by_text("Oracle", exact=True)).to_have_count(1)
            expect(group.locator(".database-label")).to_have_count(1)
            categories = page.get_by_role("group", name=category_label, exact=True)
            categories.get_by_role("button", name=category + " 1", exact=True).click()
            active = page.get_by_role("group", name="当前分类筛选", exact=True)
            expect(active.locator(".database-label")).to_have_text("Oracle")
            expect(active.locator(".active-classification-category")).to_have_text(category)
            expect(active.locator("img")).to_have_js_property("complete", True)
            assert active.locator("img").evaluate("image => image.naturalWidth > 0")
            for theme, width in [("light", 1440), ("dark", 1440), ("light", 390), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                combo.click()
                popup = page.get_by_role("listbox", name="数据库", exact=True)
                for database in ["Oracle", "MySQL", "PostgreSQL", "SQL Server", "Linux", "Redis", "MongoDB", "其他", custom]:
                    count = 1 if database in ["Oracle", "MySQL", "MongoDB", "其他", custom] else 0
                    option = popup.get_by_role("option", name=f"{database}（{count}）", exact=True)
                    expect(option.locator(".database-logo")).to_have_count(1)
                    assert option.locator(".database-logo img, .database-logo svg").count() == 1
                mysql = popup.get_by_role("option", name="MySQL（1）", exact=True)
                expect(mysql.locator("img")).to_have_js_property("complete", True)
                assert mysql.locator("img").evaluate("image => image.naturalWidth > 0")
                if theme == "dark":
                    sql_server = popup.get_by_role("option", name="SQL Server（0）", exact=True)
                    assert sql_server.locator("strong").evaluate("element => getComputedStyle(element).color") == popup.evaluate("element => getComputedStyle(element).color")
                bounds = popup.bounding_box()
                assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width
                assert bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= 1001
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(animations="disabled", path=str(tmp_path / f"{module}-database-icons-{theme}-{width}.png"))
                combo.press("Escape")
                expect(popup).to_have_count(0)
                expect(combo).to_have_attribute("title", "Oracle（1）")
                active.get_by_role("button", name="清除分类", exact=True).hover()
                page.screenshot(animations="disabled", path=str(tmp_path / f"{module}-active-filters-{theme}-{width}.png"))
            combo.press("ArrowDown")
            combo.press("ArrowDown")
            combo.press("Enter")
            expect(combo).to_have_attribute("title", "MySQL（1）")
            expect(page.locator(".library-record-list")).to_contain_text("MySQL记录")
            expect(page.locator(".library-record-list")).not_to_contain_text("Oracle记录")
            expect(active.locator(".active-classification-category")).to_have_count(0)
            expect(combo).to_be_focused()
            combo.press("Home")
            combo.press("Enter")
            expect(combo).to_have_attribute("title", "全部数据库（5）")
            combo.click()
            popup = page.get_by_role("listbox", name="数据库", exact=True)
            popup.get_by_role("option", name=f"{custom}（1）", exact=True).click()
            expect(combo).to_have_attribute("title", f"{custom}（1）")
            expect(page.locator(".library-record-list")).to_contain_text(custom + "记录")
            categories.get_by_role("button", name=custom_category + " 1", exact=True).click()
            expect(active.locator(".active-classification-category")).to_have_attribute("title", custom_category)
            expect(active.locator(".active-classification-database")).to_have_attribute("title", custom)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            combo.click()
            page.get_by_role("heading", name=label, exact=True).click()
            expect(page.get_by_role("listbox")).to_have_count(0)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            active.get_by_role("button", name="清除分类", exact=True).click()
            expect(active).to_have_count(0)
            expect(combo).to_have_attribute("title", "全部数据库（5）")
            expect(page.locator(".library-record")).to_have_count(5)
            categories.get_by_role("button", name=category + " 4", exact=True).click()
            expect(active.locator(".database-label")).to_have_count(0)
            expect(active.locator(".active-classification-category")).to_have_text(category)
            clear = active.get_by_role("button", name="清除分类", exact=True)
            clear.focus()
            clear.press("Shift+Tab")
            page.keyboard.press("Tab")
            expect(clear).to_be_focused()
            assert clear.evaluate("button => button.matches(':focus-visible')")
            page.screenshot(animations="disabled", path=str(tmp_path / f"{module}-clear-keyboard-focus.png"))
            clear.press("Enter")
            expect(active).to_have_count(0)
            page.set_viewport_size({"width": 1440, "height": 360})
            combo.click()
            popup = page.get_by_role("listbox", name="数据库", exact=True)
            bounds = popup.bounding_box()
            assert bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= 361
            combo.press("Escape")
        finally:
            browser.close()
            client.close()


@pytest.mark.browser
@pytest.mark.parametrize("module,label", [("articles", "知识库"), ("scripts", "脚本库"), ("resources", "资源中心")])
def test_database_dropdown_keeps_page_position_on_long_lists(live_server, tmp_path, module, label):
    client, csrf = _api_client(live_server)
    headers = {"X-CSRF-Token": csrf}
    db_field = "db_type" if module == "scripts" else "wb_db"
    title_field = "name" if module == "resources" else "title"
    for index in range(35):
        payload = {title_field: f"长列表滚动验证-{index:03d}", db_field: f"自定义数据库-{index:03d}"}
        if module == "resources":
            payload["path"] = str(tmp_path / f"只保留快捷路径-{index}.txt")
        else:
            payload["summary" if module == "articles" else "description"] = "保留列表位置的回归验证"
        client.post(f"/api/{module}/", json=payload, headers=headers).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 800})
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name=label, exact=True).click()
            expect(page.locator(".library-record")).to_have_count(10)
            combo = page.get_by_role("combobox", name="筛选数据库")
            position = """() => ({ x: scrollX, y: scrollY,
                sidebar: document.querySelector('.library-categories').scrollTop })"""
            settle = "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
            # A tall record list and many options exercise the portal and nested scrolling.
            assert page.evaluate("document.documentElement.scrollHeight > innerHeight + 200")
            for theme, width in [("light", 1440), ("dark", 1440), ("light", 390), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 800})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                combo.scroll_into_view_if_needed()
                page.evaluate(settle)
                before = page.evaluate(position)
                combo.click()
                popup = page.get_by_role("listbox", name="数据库", exact=True)
                expect(popup).to_be_visible()
                page.evaluate(settle)
                page.screenshot(animations="disabled", path=str(tmp_path / f"{module}-stable-scroll-{theme}-{width}.png"))
                assert page.evaluate(position) == before, "Opening the database dropdown moved the page"
                combo.press("End")
                page.evaluate(settle)
                assert page.evaluate(position) == before, "Keyboard navigation moved the page"
                assert popup.evaluate("element => element.scrollTop > 0")
                active = page.locator("[role='option'].active")
                assert active.evaluate("element => { const item = element.getBoundingClientRect(); const list = element.parentElement.getBoundingClientRect(); return item.top >= list.top && item.bottom <= list.bottom; }")
                combo.press("Home")
                page.evaluate(settle)
                assert page.evaluate(position) == before
                assert popup.evaluate("element => element.scrollTop < 10")
                popup.hover()
                page.mouse.wheel(0, 120)
                page.wait_for_function("document.querySelector('.database-filter-popup').scrollTop > 0")
                assert page.evaluate(position) == before, "Scrolling the dropdown moved the page"
                combo.press("Escape")
                expect(popup).to_have_count(0)
                assert page.evaluate(position) == before
                expect(combo).to_be_focused()
                # Confirming the existing selection must not scroll to the trigger.
                combo.press("Home")
                combo.press("Enter")
                page.evaluate(settle)
                assert page.evaluate(position) == before
            combo.press("End")
            combo.press("Enter")
            expect(combo).to_have_attribute("title", "自定义数据库-034（1）")
            expect(page.locator(".library-record")).to_have_count(1)
            combo.scroll_into_view_if_needed()
            page.evaluate(settle)
            before = page.evaluate(position)
            combo.click()
            page.evaluate(settle)
            assert page.evaluate(position) == before
            popup = page.get_by_role("listbox", name="数据库", exact=True)
            assert popup.evaluate("element => element.scrollTop > 0")
            assert page.locator("[role='option'].active").evaluate("element => { const item = element.getBoundingClientRect(); const list = element.parentElement.getBoundingClientRect(); return item.top >= list.top && item.bottom <= list.bottom; }")
        finally:
            browser.close()
            client.close()
