"""Production UI checks for independent categories and resizable file previews."""
import json

import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login, _select_database


def _sizes(page):
    # Toggle tests sample intermediate frames separately; layout assertions need the settled sizes.
    page.locator(".library-panels").evaluate("""async group => {
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      await Promise.all(group.getAnimations({subtree: true})
        .filter(animation => animation.effect?.target?.parentElement === group)
        .map(animation => animation.finished.catch(() => {})));
    }""")
    return {name: page.locator(selector).bounding_box()["width"] for name, selector in {
        "categories": ".library-categories", "list": ".library-list-pane", "preview": ".library-preview",
    }.items()}


def _drag(page, delta, offset=0):
    handle = page.get_by_role("separator", name="调整文件列表和预览宽度")
    bounds = handle.bounding_box()
    x, y = bounds["x"] + bounds["width"] / 2 + offset, max(100, bounds["y"] + 150)
    target = page.evaluate("([x,y]) => document.elementFromPoint(x,y)?.outerHTML.slice(0,300)", [x, y])
    page.mouse.move(x, y)
    page.mouse.down()
    started = handle.get_attribute("data-separator")
    page.mouse.move(x + delta, y, steps=20)
    page.mouse.up()
    return {"target": target, "bounds": bounds, "started": started, "finished": handle.get_attribute("data-separator")}


@pytest.mark.browser
@pytest.mark.parametrize("module,label", [("articles", "知识库"), ("scripts", "脚本库")])
def test_resizable_preview_preserves_categories_filters_and_file_actions(live_server, tmp_path, monkeypatch, module, label):
    from backend import local_capabilities
    from backend.config import Settings
    from backend.file_visual_preview import VIEWER_ORIGIN

    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true", "DBA_ALLOWED_ROOTS": str(tmp_path),
        "DBA_ALLOWED_LOCAL_ACTIONS": "open,folder",
    }))
    target = tmp_path / ("布局验收.md" if module == "articles" else "布局验收.pdf")
    target.write_text("# 原文件阅读\n\n| 数据库 | 检查项 |\n| --- | --- |\n| Oracle | 表格应随预览区重新排布 |\n", encoding="utf-8")
    title = "文件列表随宽度调整-" + "保留完整标题" * 8
    client, csrf = _api_client(live_server)
    database_field, category_field = ("wb_db", "category") if module == "articles" else ("db_type", "wb_type")
    for index in range(12):
        client.post(f"/api/{module}/", json={
            "title": f"{title}-{index}", database_field: "Oracle", category_field: "技术文档" if module == "articles" else "巡检",
            "file_path": str(target), "content": "SELECT 1;", "tags": "Oracle,RAC,ASM,备份,恢复",
        }, headers={"X-CSRF-Token": csrf}).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1680, "height": 1000})
            page.set_default_timeout(10_000)
            page.add_init_script("Object.defineProperty(navigator, 'clipboard', {value: {writeText: async value => {window.__copied = value;}}})")
            if module == "scripts":
                # Exercise a real iframe boundary without starting or modifying the formal viewer.
                page.route("**/api/scripts/*/visual-preview", lambda route: route.fulfill(json={
                    "filename": target.name, "viewer": "kkFileView", "viewer_url": VIEWER_ORIGIN + "/test-preview-frame",
                }))
                page.route("**/test-preview-frame", lambda route: route.fulfill(content_type="text/html; charset=utf-8", body="<html><meta charset='utf-8'><body style='margin:0;height:1500px;background:#eef2ff'><h1>原文件阅读</h1><table border='1'><tr><td>表格</td><td>图片与表格区域</td></tr></table></body></html>"))
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name=label, exact=True).click()
            _select_database(page, "Oracle")
            page.get_by_role("region", name="分类浏览").get_by_role("button", name="技术文档" if module == "articles" else "巡检", exact=False).click()
            page.get_by_role("button", name="第 2 页", exact=True).click()
            expect(page.locator(".library-record")).to_have_count(2)
            trigger = page.get_by_role("button", name=f"预览：{title}-1", exact=True)
            trigger.click()
            if module == "articles":
                expect(page.locator(".library-markdown table")).to_be_visible()
            else:
                expect(page.frame_locator(".library-visual-frame").get_by_role("heading", name="原文件阅读")).to_be_visible()
            reads = []
            page.on("request", lambda request: reads.append(request.url) if "/api/" in request.url else None)
            before, url = _sizes(page), page.url
            assert page.get_by_role("separator").bounding_box()["width"] <= 4.1
            # The library still accepts grabs just outside the thinner visible separator.
            _drag(page, -180, offset=4)
            after = _sizes(page)
            assert abs(after["categories"] - before["categories"]) < 1
            assert after["preview"] > before["preview"] + 150
            assert after["list"] < before["list"] - 150
            assert abs(after["list"] + after["preview"] - before["list"] - before["preview"]) < 2
            expect(trigger).to_have_attribute("aria-pressed", "true")
            expect(page.get_by_role("button", name="第 2 页", exact=True)).to_have_attribute("aria-current", "page")
            assert page.url == url and not reads
            handle = page.get_by_role("separator", name="调整文件列表和预览宽度")
            handle.focus()
            page.keyboard.press("ArrowRight")
            assert _sizes(page)["list"] > after["list"]
            _drag(page, -2000)
            compact = _sizes(page)
            assert 279 <= compact["list"] <= 282
            assert abs(compact["categories"] - before["categories"]) < 1
            first = page.locator(".library-record").first
            assert first.locator(".library-record-actions").evaluate("element => getComputedStyle(element).display") == "grid"
            expect(first.locator(".library-record-path")).to_have_attribute("title", str(target))
            expect(first.get_by_role("button", name="复制路径：" + first.locator(".library-record-title").get_attribute("title"), exact=True)).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(tmp_path / f"{module}-compact-light.png"), animations="disabled")
            page.get_by_role("button", name="收起分类浏览", exact=True).click()
            expect(page.get_by_role("button", name="展开分类浏览", exact=True)).to_have_attribute("aria-expanded", "false")
            assert abs(_sizes(page)["categories"] - 44) < 1
            expect(page.get_by_role("button", name="第 2 页", exact=True)).to_have_attribute("aria-current", "page")
            expect(trigger).to_have_attribute("aria-pressed", "true")
            collapsed = _sizes(page)
            drag = _drag(page, 130)
            assert _sizes(page)["list"] > collapsed["list"] + 100, drag
            assert abs(_sizes(page)["categories"] - 44) < 1
            key = f"dba-library-layout:{module}"
            saved = page.evaluate("key => JSON.parse(localStorage.getItem(key))", key)
            assert saved == {"collapsed": True}
            page.evaluate("document.documentElement.dataset.theme = 'dark'")
            page.screenshot(path=str(tmp_path / f"{module}-collapsed-dark.png"), animations="disabled")
            preview = page.locator(".library-preview")
            preview.get_by_role("button", name=f"复制路径：{title}-1", exact=True).click()
            assert page.evaluate("window.__copied") == str(target)
            preview.get_by_role("button", name="关闭预览", exact=True).click()
            expect(trigger).to_be_focused()
            page.get_by_role("button", name="预览", exact=True).click()
            reopened = _sizes(page)
            assert abs(reopened["list"] / (reopened["list"] + reopened["preview"]) * 100 - 50) < 1
            page.reload()
            expect(page.get_by_role("button", name="展开分类浏览", exact=True)).to_be_visible()
            expect(page.get_by_role("group", name="当前分类筛选")).to_contain_text("Oracle")
            expect(page.locator(".library-preview")).to_have_count(0)
            page.locator(".library-record-title").first.click()
            restored = _sizes(page)
            assert abs(restored["list"] / (restored["list"] + restored["preview"]) * 100 - 50) < 1
            page.get_by_role("button", name="展开分类浏览", exact=True).click()
            assert abs(_sizes(page)["categories"] - before["categories"]) < 1
            page.evaluate("window.scrollTo(0, 550)")
            expect(page.locator(".library-preview")).to_have_css("position", "sticky")
            assert abs(page.locator(".library-preview").bounding_box()["y"] - 78) < 2
            scroll = page.evaluate("scrollY")
            _drag(page, -30)
            assert abs(page.evaluate("scrollY") - scroll) < 2
            assert abs(_sizes(page)["categories"] - before["categories"]) < 1
            page.evaluate("window.scrollTo(0, 0)")
            page.get_by_role("separator", name="调整文件列表和预览宽度").dblclick(position={"x": 4, "y": 100})
            reset = _sizes(page)
            assert abs(reset["list"] - reset["preview"]) < 2
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="脚本库" if module == "articles" else "知识库", exact=True).click()
            expect(page.get_by_role("button", name="收起分类浏览", exact=True)).to_be_visible()
            page.get_by_role("navigation", name="主导航").get_by_role("link", name=label, exact=True).click()
            for theme, width in [("light", 1024), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 900})
                page.evaluate("value => document.documentElement.dataset.theme = value", theme)
                expect(page.get_by_role("separator")).to_have_count(0)
                page.get_by_role("button", name="收起分类浏览", exact=True).click()
                page.get_by_role("button", name="展开分类浏览", exact=True).click()
                page.locator(".library-record-title").first.click()
                expect(page.get_by_role("dialog")).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(tmp_path / f"{module}-{theme}-{width}.png"), animations="disabled")
                page.keyboard.press("Escape")
            (tmp_path / "layout-result.json").write_text(json.dumps({"before": before, "after": after, "minimum": compact, "persisted": saved}, indent=2), encoding="utf-8")
        finally:
            browser.close()
            client.close()
