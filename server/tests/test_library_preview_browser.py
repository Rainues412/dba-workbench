from types import SimpleNamespace

import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login


@pytest.mark.browser
@pytest.mark.parametrize("module,label,path_field,open_label,mode", [
    ("resources", "资源中心", "path", "打开资源", "open"),
    ("articles", "知识库", "file_path", "打开文档", "open"),
    ("scripts", "脚本库", "file_path", "打开脚本", "edit"),
])
def test_classification_list_preview_and_shortcuts(live_server, tmp_path, monkeypatch, module, label, path_field, open_label, mode):
    from backend import local_capabilities
    from backend.config import Settings
    from backend.routers import launcher

    target = tmp_path / "保留快捷访问.sql"
    target.write_text("select 'local file is not modified';", encoding="utf-8")
    settings = Settings.from_env({"DBA_LOCAL_CAPABILITIES": "true", "DBA_ALLOWED_ROOTS": str(tmp_path), "DBA_ALLOWED_LOCAL_ACTIONS": "open,edit,folder"})
    monkeypatch.setattr(local_capabilities, "settings", settings)
    monkeypatch.setattr(launcher, "settings", settings)
    monkeypatch.setattr(launcher, "EDITORS", [])
    commands, opened = [], []
    monkeypatch.setattr(launcher, "subprocess", SimpleNamespace(Popen=lambda args: commands.append(args)))
    monkeypatch.setattr(launcher.os, "startfile", lambda path: opened.append(path))
    client, csrf = _api_client(live_server)
    headers = {"X-CSRF-Token": csrf}
    title = "数据库部署与运维说明-" + "长标题" * 18
    body = "一、操作前检查\n保留完整正文与换行。\nSELECT '" + "x" * 280 + "';\n<img src=x onerror=alert(1)>"
    title_field = "name" if module == "resources" else "title"
    database_field = "db_type" if module == "scripts" else "wb_db"
    category_field = "wb_type" if module == "scripts" else "kind" if module == "resources" else "category"
    category = "巡检" if module == "scripts" else "软件工具" if module == "resources" else "安装部署"
    payload = {title_field: title, database_field: "Oracle", category_field: category, path_field: str(target)}
    payload.update({"notes": body} if module == "resources" else {"content": body, "description" if module == "scripts" else "summary": "运维说明摘要"})
    created = client.post(f"/api/{module}/", json=payload, headers=headers)
    created.raise_for_status()
    original = created.json()
    custom_category = "自定义分类-" + "长名称" * 14
    client.post(f"/api/{module}/", json={title_field: "其他数据库记录", database_field: "达梦", category_field: custom_category}, headers=headers).raise_for_status()
    if module == "resources":
        client.post("/api/resources/", json={"name": "网站快捷入口", "url": "https://example.test/db-docs"}, headers=headers).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(10_000)
            page.add_init_script("Object.defineProperty(navigator, 'clipboard', {value: {writeText: async value => {window.__copied = value;}}})")
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name=label, exact=True).click()
            if module == "resources":
                expect(page.get_by_role("link", name="打开网址：网站快捷入口", exact=True)).to_have_attribute("href", "https://example.test/db-docs")
            database = page.get_by_role("combobox", name="筛选数据库")
            database.click()
            expect(page.get_by_role("option", name="达梦（1）", exact=True)).to_have_count(1)
            page.get_by_role("option", name="Oracle（1）", exact=True).click()
            expect(page.get_by_role("button", name="预览：其他数据库记录")).to_have_count(0)
            if module == "resources":
                expect(page.get_by_role("button", name="预览", exact=True)).to_have_count(0)
                expect(page.get_by_role("button", name=f"{open_label}：{title}", exact=True)).to_have_attribute("title", title)
            else:
                expect(page.get_by_role("button", name="预览：" + title, exact=True)).to_have_attribute("title", title)
            assert not commands and not opened  # Selecting/filtering never launches files.
            for theme, width in [("light", 1440), ("dark", 1440), ("light", 1024), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("value => document.documentElement.dataset.theme = value", theme)
                trigger = page.get_by_role("button", name="预览：" + title, exact=True)
                if module == "resources":
                    preview = page.locator(".library-record").filter(has_text=title)
                else:
                    trigger.click()
                    preview = page.locator(".library-preview")
                    if module == "articles":
                        expect(preview.get_by_role("region", name="正文预览", exact=True)).to_have_count(0)
                        expect(preview).not_to_contain_text(body)
                        expect(preview).not_to_contain_text("运维说明摘要")
                    else:
                        expect(preview).to_contain_text(body)
                        expect(preview).to_contain_text("运维说明摘要")
                expect(preview.locator(".library-code img")).to_have_count(0)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                if module == "resources":
                    expect(page.locator(".library-preview")).to_have_count(0)
                    assert preview.locator(".record-title-link").evaluate("element => element.getBoundingClientRect().right <= element.closest('.library-record-copy').getBoundingClientRect().right + 1")
                elif width >= 1400:
                    assert preview.evaluate("element => element.tagName") == "ASIDE"
                    assert preview.bounding_box()["x"] > page.locator(".data-panel").bounding_box()["x"]
                    expect(page.get_by_role("group", name="数据库分类")).to_be_visible()
                else:
                    assert preview.evaluate("element => element.open && element.matches(':modal')")
                    assert preview.bounding_box()["width"] <= width
                page.screenshot(animations="disabled", path=str(tmp_path / f"{module}-preview-{theme}-{width}.png"))
                preview.get_by_role("button", name=f"{open_label}：{title}", exact=True).click()
                notice = page.get_by_role("status").filter(has_text=f"已{open_label}") if module == "resources" else preview.locator(".library-inline-notice")
                expect(notice).to_contain_text(f"已{open_label}")
                if mode == "edit":
                    assert commands[-1] == ["notepad.exe", str(target.resolve())]
                else:
                    assert opened[-1] == str(target.resolve())
                preview.get_by_role("button", name=f"打开所在文件夹：{title}", exact=True).click()
                notice = page.get_by_role("status").filter(has_text="已打开所在文件夹") if module == "resources" else preview.locator(".library-inline-notice")
                expect(notice).to_contain_text("已打开所在文件夹")
                assert commands[-1] == ["explorer", "/select,", str(target.resolve())]
                preview.get_by_role("button", name=f"复制路径：{title}", exact=True).click()
                notice = page.get_by_role("status").filter(has_text="路径已复制") if module == "resources" else preview.locator(".library-inline-notice")
                expect(notice).to_contain_text("路径已复制")
                assert page.evaluate("window.__copied") == str(target)
                if module == "scripts":
                    preview.get_by_role("button", name="复制正文", exact=True).click()
                    assert page.evaluate("window.__copied") == body
                if module == "resources":
                    continue
                if width < 1400:
                    page.keyboard.press("Escape")
                else:
                    preview.get_by_role("button", name="关闭预览", exact=True).click()
                expect(preview).to_have_count(0)
                expect(trigger).to_be_focused()
            page.set_viewport_size({"width": 1440, "height": 1000})
            if module == "resources":
                page.get_by_role("button", name="查看/编辑", exact=True).click()
            else:
                page.get_by_role("button", name="预览：" + title, exact=True).click()
                page.locator(".library-preview").get_by_role("button", name="编辑", exact=True).click()
            dialog = page.get_by_role("dialog")
            page.screenshot(animations="disabled", path=str(tmp_path / f"{module}-editor-after-preview.png"))
            expect(dialog.get_by_role("heading", name=f"编辑{label}", exact=True)).to_be_visible()
            field = "备注" if module == "resources" else "脚本正文" if module == "scripts" else "正文"
            expect(dialog.get_by_label(field, exact=True)).to_have_value(body)
            if module == "articles":
                expect(dialog.get_by_label("摘要", exact=True)).to_have_value("运维说明摘要")
            dialog.get_by_label("名称" if module != "articles" else "标题", exact=True).fill("已验证完整保存")
            dialog.get_by_role("button", name="保存", exact=True).click()
            expect(dialog).to_have_count(0)
            saved = client.get(f"/api/{module}/{original['id']}").json()
            assert saved["notes" if module == "resources" else "content"] == body
            if module == "articles":
                assert saved["summary"] == "运维说明摘要"
            assert saved["revision"] == original["revision"] + 1
            assert target.read_text(encoding="utf-8") == "select 'local file is not modified';"
        finally:
            browser.close()
            client.close()


@pytest.mark.browser
@pytest.mark.parametrize("module,label,suffix,encoding", [
    ("scripts", "脚本库", ".sql", "gb18030"),
    ("articles", "知识库", ".pdf", "utf-8"),
])
def test_path_only_records_preview_real_file_when_viewer_unavailable(live_server, tmp_path, monkeypatch, module, label, suffix, encoding):
    from backend import file_visual_preview, local_capabilities
    from backend.config import Settings

    monkeypatch.setattr(file_visual_preview, "_viewer_available", lambda: False)
    monkeypatch.setattr(local_capabilities, "_enrolled_roots", set())
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true", "DBA_ALLOWED_ROOTS": str(tmp_path),
        "DBA_ALLOWED_LOCAL_ACTIONS": "open,edit,folder",
    }))
    target = tmp_path / ("仅关联路径的中文文件" + suffix)
    body = "-- 健康检查脚本\nSELECT '中文内容';\n<img src=x onerror=alert(1)>"
    target.write_bytes(body.encode(encoding))
    client, csrf = _api_client(live_server)
    original = client.post(f"/api/{module}/", json={"title": "仅路径记录", "file_path": str(target)}, headers={"X-CSRF-Token": csrf}).json()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.add_init_script("Object.defineProperty(navigator, 'clipboard', {value: {writeText: async value => {window.__copied = value;}}})")
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name=label, exact=True).click()
            page.get_by_role("button", name="预览：仅路径记录", exact=True).click()
            preview = page.locator(".library-preview")
            changed_body = body
            if module == "scripts":
                expect(preview).to_contain_text(body)
                expect(preview).to_contain_text("预览来源：关联文件")
                expect(preview.locator(".library-code img")).to_have_count(0)
                preview.get_by_role("button", name="复制正文", exact=True).click()
                assert page.evaluate("window.__copied") == body
            else:
                expect(preview).to_contain_text("原文件预览失败：内置文件预览服务正在启动或不可用，请稍后重试")
                expect(preview.get_by_role("region", name="正文预览", exact=True)).to_have_count(0)
                expect(preview).not_to_contain_text(body)
            page.screenshot(animations="disabled", path=str(tmp_path / f"{module}-linked-file-light-1600.png"))
            # Reading again reflects the linked file without changing its database record.
            if module == "scripts":
                changed_body = body + "\n-- 原文件更新后重新读取"
                target.write_bytes(changed_body.encode(encoding))
                preview.get_by_role("button", name="重新读取", exact=True).click()
                expect(preview).to_contain_text(changed_body)
            page.set_viewport_size({"width": 390, "height": 900})
            page.evaluate("document.documentElement.dataset.theme = 'dark'")
            if module == "scripts":
                expect(preview).to_contain_text(changed_body)
            else:
                expect(preview.get_by_role("region", name="正文预览", exact=True)).to_have_count(0)
            assert preview.evaluate("element => element.matches(':modal')")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(animations="disabled", path=str(tmp_path / f"{module}-linked-file-dark-390.png"))
            preview.get_by_role("button", name="编辑", exact=True).click()
            editor = page.get_by_role("dialog")
            expect(editor.get_by_label("脚本正文" if module == "scripts" else "正文", exact=True)).to_have_value("")
            editor.get_by_role("button", name="取消", exact=True).click()
            saved = client.get(f"/api/{module}/{original['id']}").json()
            assert saved["content"] == ""
            assert saved["revision"] == original["revision"]
            assert target.read_bytes() == changed_body.encode(encoding)
        finally:
            browser.close()
            client.close()
