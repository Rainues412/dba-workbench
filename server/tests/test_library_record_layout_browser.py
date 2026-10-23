import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login, _select_database


@pytest.mark.browser
@pytest.mark.parametrize("module,label", [("articles", "知识库"), ("scripts", "脚本库"), ("resources", "资源中心")])
def test_record_icons_tags_and_actions_stay_inside_rows(live_server, tmp_path, module, label):
    client, csrf = _api_client(live_server)
    database_field = "db_type" if module == "scripts" else "wb_db"
    category_field = "wb_type" if module == "scripts" else "kind" if module == "resources" else "category"
    title_field = "name" if module == "resources" else "title"
    path_field = "path" if module == "resources" else "file_path"
    databases = ["Oracle", "MySQL", "PostgreSQL", "SQL Server", "Linux", "Redis", "MongoDB", "其他", "自定义数据库" + "长名称" * 12]
    category = "长分类名称" * 12
    for index, database in enumerate(databases):
        record_category = category if index else "技术文档"
        record_title = "UnlinkedFileName" * 30 if index == 7 else f"记录-{index}-" + "很长的文件标题" * 15 if index else "表空间扩容"
        payload = {title_field: record_title, database_field: database,
                   category_field: record_category, path_field: "" if index == 7 else str(tmp_path / ("长文件路径" * 15 + ".sql")),
                   "tags": f"{database},{record_category}," + ("" if module == "articles" else "v1,") + "RAC,RAC,ASM,备份,恢复"}
        payload.update({"version": "1"} if module == "resources" else {"summary" if module == "articles" else "description": "" if index == 7 else "来自 Oracle\\表空间\\" + ("文件说明" * 40 if index else "表空间扩容.md")})
        client.post(f"/api/{module}/", json=payload, headers={"X-CSRF-Token": csrf}).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name=label, exact=True).click()
            records = page.locator(".library-record")
            expect(records).to_have_count(9)
            if module != "resources":
                expect(records.first.locator(".library-record-path")).to_have_attribute("title", str(tmp_path / ("长文件路径" * 15 + ".sql")))
            for theme, width in [("light", 1440), ("dark", 1440), ("light", 1024), ("light", 390), ("dark", 390), ("light", 320)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                errors = records.evaluate_all("""rows => rows.flatMap(row => {
                    const errors = [], bounds = row.getBoundingClientRect();
                    for (const element of row.querySelectorAll('.database-label, .badge, .library-tag, .library-record-actions, .library-record-path, .record-title-link, .record-path-link, .record-copy-path, .library-resource-links .compact-file-links > span:not(.record-path-line)')) {
                        const rect = element.getBoundingClientRect();
                        if (rect.left < bounds.left - 1 || rect.right > bounds.right + 1) errors.push('element overflows row');
                    }
                    const logo = row.querySelector('.database-logo'), glyph = logo.querySelector('img, svg');
                    const a = logo.getBoundingClientRect(), b = glyph.getBoundingClientRect();
                    if (b.left < a.left - 0.5 || b.right > a.right + 0.5 || b.top < a.top - 0.5 || b.bottom > a.bottom + 0.5) errors.push('glyph overflows logo');
                    if (Math.abs(a.x + a.width / 2 - b.x - b.width / 2) > 0.5 || Math.abs(a.y + a.height / 2 - b.y - b.height / 2) > 0.5) errors.push('glyph is not centered');
                    const chips = [...row.querySelector('.library-record-meta').children].map(el => el.getBoundingClientRect());
                    if (chips.some(rect => Math.abs(rect.height - chips[0].height) > 0.5)) errors.push('chip heights differ');
                    const title = row.querySelector('.library-record-summary'), actions = row.querySelector('.library-record-actions');
                    if (title.getBoundingClientRect().right > actions.getBoundingClientRect().left) errors.push('title overlaps actions');
                    return errors;
                })""")
                assert not errors, errors
                expect(records.first.locator(".library-tag")).to_have_text(["RAC", "ASM", "备份", "+1"])
                for image in records.locator(".database-logo img").all():
                    expect(image).to_have_js_property("complete", True)
                    assert image.evaluate("image => image.complete && image.naturalWidth > 0")
                page.screenshot(animations="disabled", path=str(tmp_path / f"{module}-records-{theme}-{width}.png"))
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.evaluate("document.documentElement.dataset.theme = 'light'")
            _select_database(page, "Oracle")
            expect(records).to_have_count(1)
            first = records.first
            first.screenshot(animations="disabled", path=str(tmp_path / f"{module}-single-record.png"))
            page.set_viewport_size({"width": 320, "height": 1000})
            first.get_by_role("button", name="查看/编辑", exact=True).focus()
            page.keyboard.press("Tab")
            more = first.locator(".library-more summary")
            expect(more).to_be_focused()
            more.press("Enter")
            expect(first.get_by_role("button", name="删除记录")).to_be_visible()
            menu = first.locator(".library-more > div").bounding_box()
            assert menu["x"] >= 0 and menu["x"] + menu["width"] <= 320
            page.screenshot(animations="disabled", path=str(tmp_path / f"{module}-record-menu-keyboard.png"))
        finally:
            browser.close()
            client.close()
