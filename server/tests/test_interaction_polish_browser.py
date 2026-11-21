"""Exercise input protection and drag cancellation in the production build."""
import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login


@pytest.mark.browser
def test_input_drag_and_filename_polish(live_server, tmp_path):
    client, csrf = _api_client(live_server)
    title = "生产数据库巡检与恢复操作说明" * 8 + ".pdf"
    result = client.post("/api/articles/", headers={"X-CSRF-Token": csrf}, json={
        "title": title, "file_path": str(tmp_path / title), "wb_db": "Oracle", "category": "技术文档",
    })
    result.raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1920, "height": 1000})
            page.route("**/api/articles/*/visual-preview", lambda route: route.fulfill(json={
                "filename": title, "viewer": "kkFileView", "viewer_url": "http://127.0.0.1:8012/polish-frame",
            }))
            page.route("**/polish-frame", lambda route: route.fulfill(content_type="text/html", body="<body><h1>Preview</h1><div style='height:2000px'>iframe boundary</div></body>"))
            _login(page, live_server)
            search = page.get_by_role("combobox", name="跨模块搜索关键词")
            search.fill("生产数据库")
            expect(page.get_by_role("option")).to_have_count(1)
            search.press("ArrowDown")
            before = page.url
            search.dispatch_event("compositionstart", {"data": "sheng"})
            search.press("Enter")
            assert page.url == before
            search.dispatch_event("compositionend", {"data": "生"})
            search.press("Enter")
            assert page.url == before
            page.wait_for_timeout(550)
            search.press("Enter")
            expect(page.locator(".library-preview")).to_be_visible()
            expect(page.frame_locator(".library-visual-frame").get_by_role("heading", name="Preview")).to_be_visible()
            group = page.locator(".library-panels")
            pane = page.locator(".library-list-pane")
            handle = page.get_by_role("separator", name="调整文件列表和预览宽度")
            page.wait_for_timeout(300)
            original = pane.bounding_box()["width"]
            bounds = handle.bounding_box()
            x, y = bounds["x"] + 2, bounds["y"] + 140
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x + 180, y, steps=10)
            expect(page.locator(".library-drag-shield")).to_be_visible()
            assert pane.bounding_box()["width"] > original + 100
            page.keyboard.press("Escape")
            expect(page.locator(".library-drag-shield")).to_have_count(0)
            page.mouse.move(x + 230, y)
            page.mouse.up()
            page.wait_for_timeout(300)
            assert abs(pane.bounding_box()["width"] - original) < 2
            expect(page.locator(".library-preview")).to_be_visible()

            bounds = handle.bounding_box()
            page.mouse.move(bounds["x"] + 2, y)
            page.mouse.down()
            rect = group.bounding_box()
            page.mouse.move(rect["x"] + rect["width"] * .85, y, steps=15)
            expect(page.get_by_role("status").filter(has_text="松开收起预览")).to_be_visible()
            page.mouse.up()
            expect(group).to_have_attribute("data-preview-open", "false")
            expect(page.locator(".library-drag-shield")).to_have_count(0)
            page.get_by_role("button", name="预览", exact=True).click()
            expect(group).to_have_attribute("data-preview-open", "true")
            handle.dblclick(position={"x": 2, "y": 140})
            page.wait_for_timeout(300)
            assert abs(pane.bounding_box()["width"] - page.locator(".library-preview-pane").bounding_box()["width"]) < 2

            for theme, width, zoom in [("light", 1920, 1), ("dark", 1920, 1.25), ("light", 1920, 1.5), ("dark", 390, 1)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("([theme, zoom]) => { document.documentElement.dataset.theme = theme; document.documentElement.style.zoom = zoom; }", [theme, zoom])
                expect(page.locator(".library-preview-heading .filename-extension").last).to_have_text(".pdf")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(tmp_path / f"polish-{theme}-{width}-{zoom}.png"), animations="disabled")
        finally:
            browser.close()
            client.close()
