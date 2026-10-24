"""List filtering must not replace, reload or clear the document being read."""
import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login, _select_database


@pytest.mark.browser
@pytest.mark.parametrize(("module", "label"), [("articles", "知识库"), ("scripts", "脚本库")])
def test_preview_survives_classification_pagination_and_empty_results(live_server, tmp_path, monkeypatch, module, label):
    from backend import local_capabilities
    from backend.config import Settings
    from backend.file_visual_preview import VIEWER_ORIGIN

    monkeypatch.setattr(local_capabilities, "_enrolled_roots", set())
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true", "DBA_ALLOWED_ROOTS": str(tmp_path), "DBA_ALLOWED_LOCAL_ACTIONS": "open,folder",
    }))
    target = tmp_path / ("保持阅读.md" if module == "articles" else "保持阅读.pdf")
    target.write_text("# 阅读位置\n\n" + "保持文档阅读位置。\n\n" * 120, encoding="utf-8")
    database_field, category_field = ("wb_db", "category") if module == "articles" else ("db_type", "wb_type")
    client, csrf = _api_client(live_server)
    title = "保持预览的原记录"
    client.post(f"/api/{module}/", json={
        "title": title, "file_path": str(target), database_field: "Oracle", category_field: "原分类",
    }, headers={"X-CSRF-Token": csrf}).raise_for_status()
    for index in range(12):
        client.post(f"/api/{module}/", json={
            "title": f"其他类型记录-{index}", database_field: "MySQL", category_field: "其他",
        }, headers={"X-CSRF-Token": csrf}).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1680, "height": 1000})
            if module == "scripts":
                page.route("**/api/scripts/*/visual-preview", lambda route: route.fulfill(json={
                    "filename": target.name, "viewer": "kkFileView", "viewer_url": VIEWER_ORIGIN + "/retained-preview",
                }))
                page.route("**/retained-preview", lambda route: route.fulfill(content_type="text/html; charset=utf-8", body="<body style='height:4500px'><h1>原文件阅读</h1><script>window.instance=Math.random()</script></body>"))
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name=label, exact=True).click()
            search = page.get_by_placeholder(f"按标题搜索{label}")
            search.fill(title)
            page.get_by_role("button", name=f"预览：{title}", exact=True).click()
            preview = page.get_by_role("complementary", name="记录预览")
            expect(preview.get_by_role("heading", name=title, exact=True)).to_be_visible()
            if module == "articles":
                document = page.locator(".library-markdown")
                expect(document.get_by_role("heading", name="阅读位置", exact=True)).to_be_visible()
                document.evaluate("element => element.scrollTop = 180")
                read_position = lambda: document.evaluate("element => element.scrollTop")
                instance = None
            else:
                document = page.frame_locator(".library-visual-frame").locator("body")
                expect(document.get_by_role("heading", name="原文件阅读")).to_be_visible()
                document.evaluate("element => element.ownerDocument.defaultView.scrollTo(0, 180)")
                read_position = lambda: document.evaluate("element => element.ownerDocument.defaultView.scrollY")
                instance = document.evaluate("element => element.ownerDocument.defaultView.instance")
            position = read_position()
            assert position > 100
            page.evaluate("window.__activeReader = document.querySelector('.library-reader')")
            reads = []
            page.on("request", lambda request: reads.append(request.url) if "/visual-preview" in request.url or "/preview-file/" in request.url or "/retained-preview" in request.url else None)

            def unchanged():
                expect(preview.get_by_role("heading", name=title, exact=True)).to_be_visible()
                assert page.evaluate("window.__activeReader === document.querySelector('.library-reader')")
                assert abs(read_position() - position) < 2
                if instance is not None:
                    assert document.evaluate("element => element.ownerDocument.defaultView.instance") == instance
                assert not reads, reads

            search.fill("")
            expect(page.locator(".library-record")).to_have_count(10)
            expect(page.get_by_role("button", name=f"预览：{title}", exact=True)).to_have_count(0)
            unchanged()
            page.get_by_role("region", name="分类浏览").get_by_role("button", name="其他", exact=False).click()
            expect(page.get_by_role("group", name="当前分类筛选")).to_contain_text("其他")
            unchanged()
            _select_database(page, "MySQL")
            expect(page.get_by_role("combobox", name="筛选数据库")).to_contain_text("MySQL")
            unchanged()
            page.get_by_role("button", name="第 2 页", exact=True).click()
            expect(page.locator(".library-record")).to_have_count(2)
            unchanged()
            page.get_by_role("checkbox", name="只看收藏").check()
            expect(page.locator(".library-record")).to_have_count(0)
            unchanged()
            search.fill("完全没有匹配结果")
            page.wait_for_timeout(250)
            unchanged()
            page.evaluate("document.documentElement.dataset.theme = 'dark'")
            page.screenshot(path=str(tmp_path / f"{module}-filtered-list-retains-preview.png"))
            preview.get_by_role("button", name="关闭预览", exact=True).click()
            expect(page.locator(".library-preview")).to_have_count(0)
            expect(page.get_by_role("button", name="预览", exact=True)).to_be_focused()
            page.get_by_role("button", name="预览", exact=True).click()
            expect(preview.get_by_role("heading", name=title, exact=True)).to_be_visible()
        finally:
            browser.close()
            client.close()
