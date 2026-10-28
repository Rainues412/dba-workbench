"""Library navigation starts with the list; reading starts on title selection."""
import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login


@pytest.mark.browser
@pytest.mark.parametrize("module,label", [("articles", "知识库"), ("scripts", "脚本库")])
@pytest.mark.parametrize("width,theme", [(1800, "light"), (1800, "dark"), (390, "dark")])
def test_dashboard_to_library_waits_for_a_title(live_server, tmp_path, monkeypatch, module, label, width, theme):
    from backend import local_capabilities
    from backend.config import Settings

    source = tmp_path / "entry-preview.md"
    source.write_text("# 单击标题后阅读\n\n原文件预览正文。", encoding="utf-8")
    monkeypatch.setattr(local_capabilities, "_enrolled_roots", set())
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true", "DBA_ALLOWED_ROOTS": str(tmp_path),
        "DBA_ALLOWED_LOCAL_ACTIONS": "open,folder",
    }))
    client, csrf = _api_client(live_server)
    database, category = ("wb_db", "category") if module == "articles" else ("db_type", "wb_type")
    created = client.post(f"/api/{module}/", json={
        "title": "按需展开文件预览", "file_path": str(source), database: "Oracle", category: "日常管理" if module == "articles" else "巡检",
    }, headers={"X-CSRF-Token": csrf})
    created.raise_for_status()
    record_id = created.json()["id"]
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": width, "height": 1000})
            page.add_init_script("localStorage.setItem('dba-ui-theme', '" + theme + "')")
            _login(page, live_server)
            reads = []
            page.on("request", lambda request: reads.append(request.url) if f"/api/{module}/{record_id}" in request.url else None)
            nav = page.get_by_role("navigation", name="主导航")

            def enter_closed():
                nav.get_by_role("link", name=label, exact=True).click()
                expect(page.get_by_role("button", name="预览：按需展开文件预览", exact=True)).to_be_visible()
                expect(page.locator(".library-preview")).to_have_count(0)
                expect(page.get_by_role("dialog")).to_have_count(0)
                expect(page.get_by_role("button", name="预览", exact=True)).to_be_disabled()
                expect(page.locator(".library-panels")).to_have_attribute("data-preview-open", "false")
                if width >= 1400:
                    pane = page.locator(".library-panels > [data-panel]:has(> .library-preview-pane)")
                    expect(pane).to_have_css("flex-grow", "0")
                    group_width = page.locator(".library-panels").bounding_box()["width"]
                    list_width = page.locator(".library-list-pane").bounding_box()["width"]
                    assert group_width - list_width < 2
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

            enter_closed()
            assert not reads
            page.get_by_role("button", name="收起分类浏览", exact=True).click()
            expect(page.locator(".library-preview")).to_have_count(0)
            page.screenshot(path=str(tmp_path / f"{module}-entry-closed-{width}-{theme}.png"))
            title = page.get_by_role("button", name="预览：按需展开文件预览", exact=True)
            title.focus()
            page.keyboard.press("Enter")
            expect(page.locator(".library-markdown").get_by_role("heading", name="单击标题后阅读", exact=True)).to_be_visible()
            expect(title).to_have_attribute("aria-pressed", "true")
            if width >= 1400:
                page.wait_for_timeout(300)
                listing = page.locator(".library-list-pane").bounding_box()["width"]
                preview = page.locator(".library-preview-pane").bounding_box()["width"]
                assert abs(listing / (listing + preview) * 100 - 50) < 1
            page.screenshot(path=str(tmp_path / f"{module}-entry-open-{width}-{theme}.png"))
            page.get_by_role("button", name="关闭预览", exact=True).click()
            expect(page.locator(".library-preview")).to_have_count(0)
            expect(title).to_be_focused()
            title.click()
            expect(page.locator(".library-markdown")).to_be_visible()
            if width < 1400:
                page.get_by_role("button", name="关闭预览", exact=True).click()
            nav.get_by_role("link", name="工作台", exact=True).click()
            expect(page.get_by_role("heading", name="今天的工作台")).to_be_visible()
            enter_closed()
            page.reload()
            expect(page.get_by_role("button", name="预览：按需展开文件预览", exact=True)).to_be_visible()
            expect(page.locator(".library-preview")).to_have_count(0)
            expect(page.get_by_role("button", name="预览", exact=True)).to_be_disabled()
        finally:
            browser.close()
            client.close()
