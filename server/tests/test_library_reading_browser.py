"""Use real browser fullscreen and the production Tocbot/Marked integration."""
import hashlib
import json
import re

from PIL import Image
import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login
from test_library_resizable_browser import _drag


@pytest.mark.browser
def test_widening_preview_shows_existing_outline_on_the_right(live_server, tmp_path, monkeypatch):
    from backend import local_capabilities
    from backend.config import Settings

    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true", "DBA_ALLOWED_ROOTS": str(tmp_path), "DBA_ALLOWED_LOCAL_ACTIONS": "open,folder",
    }))
    source = tmp_path / "有目录.md"
    source.write_text("# 维护说明\n\n## 环境检查\n\n" + "检查实例与备份。\n\n" * 30 + "## 验证结果\n\n" + "确认业务运行正常。\n\n" * 30, encoding="utf-8")
    plain = tmp_path / "无目录.md"
    plain.write_text("这是一篇没有标题的正文。\n\n" * 20, encoding="utf-8")
    client, csrf = _api_client(live_server)
    for title, path in [("有目录文章", source), ("无目录文章", plain)]:
        client.post("/api/articles/", json={"title": title, "file_path": str(path)}, headers={"X-CSRF-Token": csrf}).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1680, "height": 1000})
            page.set_default_timeout(10_000)
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="知识库", exact=True).click()
            trigger = page.get_by_role("button", name="预览：有目录文章", exact=True)
            trigger.click()
            markdown = page.get_by_role("region", name="原文件预览：有目录.md", exact=True)
            expect(markdown.get_by_role("heading", name="维护说明", exact=True)).to_be_visible()
            toc = page.get_by_role("navigation", name="文章目录", exact=True)
            expect(toc).to_have_count(0)
            reads = []
            page.on("request", lambda request: reads.append(request.url) if "visual-preview" in request.url or "/preview-file/" in request.url else None)
            url = page.url
            _drag(page, -260)
            expect(toc).to_be_visible()
            expect(toc.get_by_role("link")).to_have_count(3)
            assert page.locator(".library-visual-preview").bounding_box()["width"] >= 800
            assert abs(toc.bounding_box()["width"] - 220) < 1
            assert toc.bounding_box()["x"] >= markdown.bounding_box()["x"] + markdown.bounding_box()["width"]
            assert not page.evaluate("Boolean(document.fullscreenElement)")
            toc.get_by_role("link", name="验证结果", exact=True).click()
            expect(toc.get_by_role("link", name="验证结果", exact=True)).to_have_class(re.compile(r"\bis-active-link\b"))
            assert markdown.evaluate("element => element.scrollTop") > 500
            assert page.url == url and not reads
            expect(trigger).to_have_attribute("aria-pressed", "true")
            page.screenshot(path=str(tmp_path / "wide-preview-right-outline-light.png"), animations="disabled")
            page.evaluate("document.documentElement.dataset.theme = 'dark'")
            page.screenshot(path=str(tmp_path / "wide-preview-right-outline-dark.png"), animations="disabled")
            _drag(page, 160)
            expect(toc).to_have_count(0)
            expect(page.get_by_role("button", name="展开目录")).to_have_count(0)
            assert page.locator(".library-visual-preview").bounding_box()["width"] < 800
            _drag(page, -160)
            expect(toc).to_be_visible()
            assert not reads
            page.get_by_role("button", name="预览：无目录文章", exact=True).click()
            plain_preview = page.get_by_role("region", name="原文件预览：无目录.md", exact=True)
            expect(plain_preview).to_be_visible()
            expect(toc).to_have_count(0)
            expect(page.get_by_role("button", name="展开目录")).to_have_count(0)
            bounds = plain_preview.bounding_box()
            assert abs(bounds["width"] - page.locator(".library-visual-preview").bounding_box()["width"]) < 2
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(tmp_path / "wide-preview-without-outline.png"), animations="disabled")
        finally:
            browser.close()
            client.close()


@pytest.mark.browser
def test_fullscreen_markdown_outline_and_compact_reading(live_server, tmp_path, monkeypatch):
    from backend import local_capabilities
    from backend.config import Settings

    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true", "DBA_ALLOWED_ROOTS": str(tmp_path),
        "DBA_ALLOWED_LOCAL_ACTIONS": "open,folder",
    }))
    source = tmp_path / "数据库维护手册.md"
    Image.new("RGB", (640, 180), "#4f6bed").save(tmp_path / "流程图.png")
    source.write_text("# 数据库维护手册\n\n![维护流程](流程图.png)\n\n" + "\n\n".join(
        f"## {index}. {heading}\n\n" + "维护前请核对实例、备份和操作窗口。\n\n" * 16
        for index, heading in enumerate(["环境检查", "备份确认", "执行维护", "验证结果", "回滚说明"], 1)
    ) + "\n\n## 重复标题\n\n## 重复标题\n\n<table><tr><th>项目</th><th>状态</th></tr><tr><td>表格与图片</td><td>保留</td></tr></table>", encoding="utf-8")
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    client, csrf = _api_client(live_server)
    client.post("/api/articles/", json={"title": "数据库维护手册", "file_path": str(source), "wb_db": "Oracle", "category": "技术文档", "tags": "Oracle,安装,维护"}, headers={"X-CSRF-Token": csrf}).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1680, "height": 1000})
            page.set_default_timeout(10_000)
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="知识库", exact=True).click()
            page.get_by_role("button", name="预览：数据库维护手册", exact=True).click()
            markdown = page.get_by_role("region", name=f"原文件预览：{source.name}", exact=True)
            expect(markdown.locator("img")).to_be_visible()
            expect(markdown).to_have_css("font-size", "16px")
            assert abs(markdown.bounding_box()["x"] - page.locator(".library-preview").bounding_box()["x"]) < 2
            expect(markdown).to_have_css("padding-left", "8px")
            expect(page.get_by_role("navigation", name="文章目录")).to_have_count(0)
            before = {"url": page.url, "scroll": page.evaluate("scrollY"), "list": page.locator(".library-list-pane").bounding_box()["width"]}
            reads = []
            page.on("request", lambda request: reads.append(request.url) if "visual-preview" in request.url or "/preview-file/" in request.url else None)
            page.screenshot(path=str(tmp_path / "compact-preview-light.png"), animations="disabled")
            page.get_by_role("button", name="大屏阅读", exact=True).click()
            expect(page.locator(".library-reader:fullscreen")).to_be_visible()
            expect(page.get_by_role("button", name="退出大屏阅读", exact=True)).to_be_visible()
            toc = page.get_by_role("navigation", name="文章目录", exact=True)
            expect(toc.get_by_role("link")).to_have_count(8)
            assert toc.bounding_box()["x"] >= markdown.bounding_box()["x"] + markdown.bounding_box()["width"]
            expect(markdown).to_have_css("font-size", "17px")
            assert markdown.bounding_box()["height"] > page.evaluate("innerHeight") * .75
            assert page.locator(".library-preview-body").evaluate("element => element.scrollHeight <= element.clientHeight + 1")
            assert markdown.locator("img").evaluate("image => image.complete && image.naturalWidth > 0")
            url = page.url
            toc.get_by_role("link", name="4. 验证结果", exact=True).click()
            expect(toc.get_by_role("link", name="4. 验证结果", exact=True)).to_have_class(re.compile(r"\bis-active-link\b"))
            assert markdown.evaluate("element => element.scrollTop") > 500
            chapter = markdown.get_by_role("heading", name="4. 验证结果", exact=True).bounding_box()
            assert abs(chapter["y"] - markdown.bounding_box()["y"] - 12) < 3
            assert page.url == url and not reads
            page.screenshot(path=str(tmp_path / "fullscreen-outline-light.png"), animations="disabled")
            page.get_by_role("button", name="收起文章目录", exact=True).click()
            expect(toc).to_have_count(0)
            page.get_by_role("button", name="展开目录", exact=True).click()
            expect(page.get_by_role("navigation", name="文章目录")).to_be_visible()
            page.evaluate("document.documentElement.dataset.theme = 'dark'")
            page.screenshot(path=str(tmp_path / "fullscreen-outline-dark.png"), animations="disabled")
            page.keyboard.press("Escape")
            expect(page.locator(":fullscreen")).to_have_count(0)
            expect(page.get_by_role("button", name="大屏阅读", exact=True)).to_be_focused()
            assert page.url == before["url"] and abs(page.evaluate("scrollY") - before["scroll"]) < 2
            assert abs(page.locator(".library-list-pane").bounding_box()["width"] - before["list"]) < 1
            expect(page.get_by_role("button", name="预览：数据库维护手册", exact=True)).to_have_attribute("aria-pressed", "true")
            expect(markdown).to_have_css("font-size", "16px")
            # A narrow preview remains a modal; fullscreen must not remount the reader on resize.
            page.set_viewport_size({"width": 390, "height": 900})
            expect(page.get_by_role("dialog")).to_be_visible()
            page.get_by_role("button", name="大屏阅读", exact=True).click()
            expect(page.locator(".library-reader:fullscreen")).to_be_visible()
            expect(page.get_by_role("navigation", name="文章目录")).to_have_count(0)
            assert markdown.evaluate("element => element.scrollWidth <= element.clientWidth + 1")
            page.screenshot(path=str(tmp_path / "fullscreen-outline-dark-narrow.png"), animations="disabled")
            page.get_by_role("button", name="退出大屏阅读", exact=True).click()
            expect(page.locator(":fullscreen")).to_have_count(0)
            expect(page.get_by_role("dialog")).to_be_visible()
            page.keyboard.press("Escape")
            expect(page.get_by_role("dialog")).to_have_count(0)
            assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
            (tmp_path / "reading-result.json").write_text(json.dumps({"fullscreen_api": True, "toc_links": 8, "original_unchanged": True, "preview_reloaded_on_fullscreen": bool(reads)}, indent=2), encoding="utf-8")
        finally:
            browser.close()
            client.close()


@pytest.mark.browser
def test_fullscreen_keeps_the_embedded_viewer_loaded(live_server, tmp_path):
    from backend.file_visual_preview import VIEWER_ORIGIN

    client, csrf = _api_client(live_server)
    client.post("/api/articles/", json={"title": "内置文件查看器", "file_path": str(tmp_path / "layout.pdf")}, headers={"X-CSRF-Token": csrf}).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1680, "height": 1000})
            page.route("**/api/articles/*/visual-preview", lambda route: route.fulfill(json={"filename": "layout.pdf", "viewer": "kkFileView", "viewer_url": VIEWER_ORIGIN + "/reading-fixture"}))
            loads = []

            def frame(route):
                loads.append(route.request.url)
                route.fulfill(content_type="text/html; charset=utf-8", body="<html><meta charset='utf-8'><body><h1>嵌入文档</h1><p>原件页面保留</p></body></html>")

            page.route("**/reading-fixture", frame)
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="知识库", exact=True).click()
            page.get_by_role("button", name="预览：内置文件查看器", exact=True).click()
            expect(page.frame_locator(".library-visual-frame").get_by_role("heading", name="嵌入文档")).to_be_visible()
            page.get_by_role("button", name="大屏阅读", exact=True).click()
            expect(page.locator(".library-reader:fullscreen")).to_be_visible()
            assert page.locator(".library-visual-frame").bounding_box()["height"] > page.evaluate("innerHeight") * .75
            expect(page.frame_locator(".library-visual-frame").get_by_role("heading", name="嵌入文档")).to_be_visible()
            page.screenshot(path=str(tmp_path / "fullscreen-embedded-viewer.png"), animations="disabled")
            page.get_by_role("button", name="退出大屏阅读", exact=True).click()
            expect(page.locator(":fullscreen")).to_have_count(0)
            assert len(loads) == 1
            page.get_by_role("complementary", name="记录预览").get_by_role("button", name="编辑", exact=True).click()
            expect(page.get_by_role("dialog").get_by_label("标题", exact=True)).to_have_value("内置文件查看器")
        finally:
            browser.close()
            client.close()
