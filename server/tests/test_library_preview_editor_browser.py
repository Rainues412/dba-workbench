from contextlib import closing

import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login, _select_database


@pytest.mark.browser
@pytest.mark.parametrize(("width", "theme"), [(1680, "light"), (390, "dark")])
def test_article_preview_survives_editor_and_reload(live_server, tmp_path, monkeypatch, width, theme):
    from backend import local_capabilities
    from backend.config import Settings

    source = tmp_path / "article.md"
    source.write_text("# 原文件正文\n\n" + "继续阅读原文。\n\n" * 120, encoding="utf-8")
    monkeypatch.setattr(local_capabilities, "_enrolled_roots", set())
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true", "DBA_ALLOWED_ROOTS": str(tmp_path), "DBA_ALLOWED_LOCAL_ACTIONS": "open,folder",
    }))
    title = "正在阅读的文章"
    client, csrf = _api_client(live_server)
    with closing(client):
        for payload in [{"title": title, "file_path": str(source), "wb_db": "Oracle"}, {"title": "另一篇文章", "wb_db": "Oracle"}]:
            client.post("/api/articles/", json=payload, headers={"X-CSRF-Token": csrf}).raise_for_status()

    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": width, "height": 940})
            page.add_init_script(f"localStorage.setItem('dba-ui-theme', '{theme}')")
            _login(page, live_server)
            page.get_by_role("link", name="知识库", exact=True).click()
            page.get_by_role("button", name=f"预览：{title}", exact=True).click()
            preview = page.locator(".library-preview")
            document = preview.locator(".library-markdown")
            original = document.get_by_role("heading", name="原文件正文", include_hidden=True)
            expect(original).to_be_visible()
            page.evaluate("window.originalPreview = document.querySelector('.library-markdown')")
            document.evaluate("element => element.scrollTop = 180")
            position = document.evaluate("element => element.scrollTop")
            assert position > 100
            reads = []
            page.on("request", lambda request: reads.append(request.url) if "/visual-preview" in request.url or "/preview-file/" in request.url else None)

            def preview_unchanged():
                expect(original).to_be_visible()
                assert document.evaluate("element => element === window.originalPreview")
                assert abs(document.evaluate("element => element.scrollTop") - position) < 2
                assert not reads, reads

            if width >= 1400:
                _select_database(page, "Oracle")
                create = page.get_by_role("button", name="新增", exact=True)
                create.click()
                new_editor = page.get_by_role("dialog", name="新增知识库")
                expect(new_editor).to_be_visible()
                preview_unchanged()
                new_editor.get_by_role("button", name="取消", exact=True).click()
                expect(create).to_be_focused()
                create.click()
                new_editor.get_by_label("标题", exact=True).fill("新增的知识库记录")
                new_editor.get_by_role("button", name="保存", exact=True).click()
                expect(page.get_by_role("button", name="预览：新增的知识库记录")).to_be_visible()
                preview_unchanged()

                other = page.locator(".library-record", has=page.get_by_role("button", name="预览：另一篇文章"))
                other.get_by_role("button", name="查看/编辑", exact=True).click()
                other_editor = page.get_by_role("dialog", name="编辑知识库")
                expect(other_editor.get_by_label("标题", exact=True)).to_have_value("另一篇文章")
                other_editor.get_by_role("button", name="取消", exact=True).click()
                preview_unchanged()

            edit = preview.get_by_role("button", name="编辑", exact=True)
            edit.click()
            editor = page.get_by_role("dialog", name="编辑知识库", exact=True)
            expect(editor.get_by_label("标题", exact=True)).to_have_value(title)
            preview_unchanged()
            page.keyboard.press("Escape")
            expect(editor).to_have_count(0)
            expect(edit).to_be_focused()
            preview_unchanged()

            edit.click()
            new_title = "修改标题后继续阅读"
            editor.get_by_label("标题", exact=True).fill(new_title)
            editor.get_by_role("button", name="保存", exact=True).click()
            expect(preview.get_by_role("heading", name=new_title, exact=True)).to_be_visible()
            preview_unchanged()

            edit.click()
            expect(editor).to_be_visible()
            page.reload()
            expect(editor).to_have_count(0)
            expect(preview.get_by_role("heading", name=new_title, exact=True)).to_be_visible()
            expect(original).to_be_visible()
            if width >= 1400:
                edit.click()
                page.set_viewport_size({"width": 390, "height": 940})
                expect(editor.get_by_label("标题", exact=True)).to_have_value(new_title)
                editor.get_by_role("button", name="取消", exact=True).click()
                expect(original).to_be_visible()
            preview.get_by_role("button", name="关闭预览", exact=True).click()
            page.reload()
            expect(page.get_by_role("button", name=f"预览：{new_title}", exact=True)).to_have_attribute("aria-pressed", "false")
            expect(preview).to_have_count(0)
        finally:
            browser.close()
