"""Production-bundle interactions using an isolated DB and synthetic local files."""
import json
import re
import time

import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login
from test_library_resizable_browser import _drag


def _settled_indicator(page):
    # Poll through evaluate: Playwright's waitForFunction uses eval under CSP.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if page.evaluate("""() => {
        const link = document.querySelector('.nav-link[aria-current="page"]');
        const mark = link?.querySelector('.nav-active-indicator');
        if (!mark) return false;
        const a = link.getBoundingClientRect(), b = mark.getBoundingClientRect();
        return ['x', 'y', 'width', 'height'].every(k => Math.abs(a[k] - b[k]) < 1);
        }"""):
            return
        page.wait_for_timeout(40)
    raise AssertionError("Menu indicator did not settle on the active link")


@pytest.mark.browser
def test_menu_spring_geometry_interruptions_and_reduced_motion(live_server, tmp_path):
    client, _ = _api_client(live_server)
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1800, "height": 1000}, reduced_motion="no-preference")
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            _login(page, live_server)
            nav = page.get_by_role("navigation", name="主导航")
            # Different target dimensions prove the indicator follows geometry, not fixed offsets.
            nav.get_by_role("link", name="客户项目", exact=True).evaluate("e => {e.style.width='175px'; e.style.minHeight='74px'}")
            frames = page.evaluate("""async () => {
                const target = document.querySelector('.nav-link[href="/customers"]');
                const start = document.querySelector('.nav-active-indicator').getBoundingClientRect().toJSON();
                target.click();
                const frames = []; const begun = performance.now();
                await new Promise(resolve => {
                    function sample() {
                        const mark = document.querySelector('.nav-link.active .nav-active-indicator');
                        if (mark) frames.push({t:performance.now()-begun, ...mark.getBoundingClientRect().toJSON()});
                        if (performance.now()-begun < 1000) requestAnimationFrame(sample); else resolve();
                    }
                    requestAnimationFrame(sample);
                });
                return {start, target:target.getBoundingClientRect().toJSON(), frames};
            }""")
            _settled_indicator(page)
            start, target, samples = frames["start"], frames["target"], frames["frames"]
            assert any(start["y"] + 5 < frame["y"] < target["y"] - 5 for frame in samples), frames
            assert any(target["width"] + 2 < frame["width"] < start["width"] - 2 for frame in samples), frames
            assert any(start["height"] + 1 < frame["height"] < target["height"] - 1 for frame in samples), frames
            assert target["y"] + .2 < max(frame["y"] for frame in samples) < target["y"] + 30, frames
            (tmp_path / "spring-frames.json").write_text(json.dumps(frames, indent=2), encoding="utf-8")
            # Interrupt an active spring with more navigation, then test browser history.
            page.evaluate("""() => {
                document.querySelector('.nav-link[href="/articles"]').click();
                setTimeout(() => document.querySelector('.nav-link[href="/scripts"]').click(), 45);
            }""")
            expect(nav.get_by_role("link", name="脚本库", exact=True)).to_have_attribute("aria-current", "page")
            _settled_indicator(page)
            page.go_back()
            expect(nav.get_by_role("link", name="知识库", exact=True)).to_have_attribute("aria-current", "page")
            _settled_indicator(page)
            page.go_forward()
            _settled_indicator(page)
            page.get_by_role("button", name="收起侧栏", exact=True).click()
            _settled_indicator(page)
            page.screenshot(path=str(tmp_path / "menu-collapsed.png"))
            page.get_by_role("button", name="展开侧栏", exact=True).click()
            _settled_indicator(page)
            for theme, width in [("light", 1800), ("dark", 1800), ("light", 390), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                nav.get_by_role("link", name="知识库", exact=True).focus()
                nav.get_by_role("link", name="知识库", exact=True).press("Enter")
                _settled_indicator(page)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(tmp_path / f"menu-{theme}-{width}.png"))
            page.emulate_media(reduced_motion="reduce")
            nav.get_by_role("link", name="任务管理", exact=True).click()
            _settled_indicator(page)
            assert page.locator('.nav-link.active .nav-active-indicator').evaluate("e => getComputedStyle(e).transform") in {"none", "matrix(1, 0, 0, 1, 0, 0)"}
            assert not errors
        finally:
            browser.close()
            client.close()


@pytest.mark.browser
def test_search_highlights_and_previews_source_off_page(live_server, tmp_path, monkeypatch):
    from backend import local_capabilities
    from backend.config import Settings

    monkeypatch.setattr(local_capabilities, "_enrolled_roots", set())
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true", "DBA_ALLOWED_ROOTS": str(tmp_path),
        "DBA_ALLOWED_LOCAL_ACTIONS": "check,open,folder",
    }))
    client, csrf = _api_client(live_server)
    headers = {"X-CSRF-Token": csrf}
    sources = {}
    for module, suffix, body in [("articles", ".md", "# 原文件阅读验证\n\n来自关联文件。"), ("scripts", ".sql", "SELECT 'source-file-preview';")]:
        source = tmp_path / (module + suffix)
        source.write_text(body, encoding="utf-8")
        created = client.post(f"/api/{module}/", json={"title": f"Oracle RAC 定位-{module}", "file_path": str(source)}, headers=headers)
        created.raise_for_status()
        sources[module] = (created.json()["id"], source, body)
        for index in range(19):
            client.post(f"/api/{module}/", json={"title": f"普通记录{index:02}", "file_path": str(source)}, headers=headers).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1800, "height": 1000})
            _login(page, live_server)
            for module in ["articles", "scripts"]:
                for theme, width in [("light", 1800), ("dark", 1800), ("light", 390), ("dark", 390)]:
                    page.set_viewport_size({"width": width, "height": 1000})
                    page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                    page.keyboard.press("Control+k")
                    search = page.get_by_role("combobox", name="跨模块搜索关键词")
                    search.fill("rac")
                    result = page.get_by_role("option", name=re.compile(f"Oracle RAC 定位-{module}"))
                    expect(result.locator("mark")).to_have_text(["RAC"])
                    expect(result.locator(".global-search-result-title")).to_have_attribute("title", f"Oracle RAC 定位-{module}")
                    page.screenshot(path=str(tmp_path / f"search-{module}-{theme}-{width}.png"), animations="disabled")
                    result.click()
                    page.wait_for_url(f"**/{module}?preview={sources[module][0]}")
                    preview = page.get_by_role("complementary", name="记录预览") if width >= 1400 else page.get_by_role("dialog", name=f"Oracle RAC 定位-{module}", exact=True)
                    expect(preview.get_by_role("heading", name=f"Oracle RAC 定位-{module}", exact=True)).to_be_visible()
                    expect(page.locator('.modal-backdrop')).to_have_count(0)
                    if module == "articles":
                        expect(preview.get_by_role("heading", name="原文件阅读验证", exact=True)).to_be_visible()
                    else:
                        expect(preview.locator(".library-code")).to_contain_text("source-file-preview")
                    # The target starts off page 1; searching must navigate to its actual page.
                    selected = page.locator('.library-record.selected .library-record-title')
                    expect(selected).to_have_attribute("aria-label", f"预览：Oracle RAC 定位-{module}")
                    expect(page.locator('.pagination [aria-current="page"]')).to_have_text("2")
                    expect(page.locator('.record-active-indicator')).to_have_count(1)
                    if width >= 1400:
                        expect(selected).to_be_in_viewport(ratio=1)
                        assert selected.bounding_box()["y"] >= 64
                    page.screenshot(path=str(tmp_path / f"preview-{module}-{theme}-{width}.png"), animations="disabled")
                    preview.get_by_role("button", name="关闭预览", exact=True).click()
                    page.wait_for_url(f"**/{module}")
            # A missing target reports a read failure instead of opening an empty editor.
            page.set_viewport_size({"width": 1800, "height": 1000})
            page.goto(f"{live_server}/articles?preview=999999")
            expect(page.get_by_role("complementary", name="记录预览").get_by_role("alert")).to_be_visible()
            expect(page.locator('.modal-backdrop')).to_have_count(0)
            for _, source, body in sources.values():
                assert source.read_text(encoding="utf-8") == body
        finally:
            browser.close()
            client.close()


def _selection_frames(page, button, indicator):
    return page.evaluate("""async ([button, indicator]) => {
        const initial = document.querySelector(indicator)?.getBoundingClientRect().toJSON();
        document.querySelector(button).click();
        const samples = [], start = performance.now();
        await new Promise(resolve => {
            function frame() {
                const mark = document.querySelector(indicator);
                if (mark) samples.push(mark.getBoundingClientRect().toJSON());
                if (performance.now()-start < 850) requestAnimationFrame(frame); else resolve();
            }
            requestAnimationFrame(frame);
        });
        return {initial, samples};
    }""", [button, indicator])


def _assert_selection_settled(page, indicator, target):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        matches = page.evaluate("""([indicator, target]) => {
            const a = document.querySelector(indicator)?.getBoundingClientRect();
            const b = document.querySelector(target)?.getBoundingClientRect();
            return a && b && ['x','y','width','height'].every(k => Math.abs(a[k]-b[k]) <= 1.5);
        }""", [indicator, target])
        if matches:
            return
        page.wait_for_timeout(40)
    raise AssertionError(f"{indicator} does not match {target}")


@pytest.mark.browser
@pytest.mark.parametrize("module,nav,categories", [
    ("articles", "知识库", ["原理与SQL", "日常管理"]),
    ("scripts", "脚本库", ["巡检", "备份"]),
])
def test_preview_row_categories_and_outline_share_spring(live_server, tmp_path, monkeypatch, module, nav, categories):
    from backend import local_capabilities
    from backend.config import Settings

    source = tmp_path / "动画目录.md"
    source.write_text("# 运维文档\n\n## 环境检查\n\n" + "检查内容。\n\n" * 25
                      + "## 操作步骤\n\n" + "执行内容。\n\n" * 25
                      + "## 验证结果和需要换行展示的长标题\n\n" + "核验内容。\n\n" * 25, encoding="utf-8")
    monkeypatch.setattr(local_capabilities, "_enrolled_roots", set())
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true", "DBA_ALLOWED_ROOTS": str(tmp_path), "DBA_ALLOWED_LOCAL_ACTIONS": "open,folder",
    }))
    client, csrf = _api_client(live_server)
    field = "category" if module == "articles" else "wb_type"
    database = "wb_db" if module == "articles" else "db_type"
    for index in range(2):
        client.post(f"/api/{module}/", json={"title": f"阅读文件{index}", "file_path": str(source), field: categories[index], database: "Oracle"}, headers={"X-CSRF-Token": csrf}).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 2000, "height": 1000}, reduced_motion="no-preference")
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name=nav, exact=True).click()
            page.get_by_role("button", name="预览：阅读文件1", exact=True).click()
            expect(page.get_by_role("region", name="原文件预览：动画目录.md")).to_be_visible()
            frames = _selection_frames(page, '.library-record-title[aria-label="预览：阅读文件0"]', '.record-active-indicator')
            final_y = frames["samples"][-1]["y"]
            assert any(frames["initial"]["y"] + 2 < sample["y"] < final_y - 2 for sample in frames["samples"])
            _assert_selection_settled(page, '.record-active-indicator', '.library-record.selected')
            expect(page.locator('.library-record.selected .library-record-title')).to_have_attribute("aria-label", "预览：阅读文件0")
            expect(page.get_by_text("正在预览", exact=True)).to_have_count(0)
            category_frames = _selection_frames(page, f'.category-filter[title="{categories[1]}"]', '.category-active-indicator')
            assert len({round(sample["y"]) for sample in category_frames["samples"]}) > 3
            _assert_selection_settled(page, '.category-active-indicator', '.category-filter[aria-pressed="true"]')
            assert page.locator('.category-active-indicator').evaluate("e => getComputedStyle(e).backgroundColor === getComputedStyle(document.querySelector('.preview-toggle')).backgroundColor")
            # Filtering must keep the actual document open, without highlighting an unrelated row.
            expect(page.get_by_role("complementary", name="记录预览").get_by_role("heading", name="阅读文件0", exact=True)).to_be_visible()
            expect(page.locator('.record-active-indicator')).to_have_count(0)
            page.locator('.category-filter').first.click()
            expect(page.locator('.library-record.selected .library-record-title')).to_have_attribute("aria-label", "预览：阅读文件0")
            _drag(page, -350)
            toc = page.get_by_role("navigation", name="文章目录", exact=True)
            expect(toc).to_be_visible()
            expect(toc.locator('.toc-active-indicator')).to_have_count(1)
            _assert_selection_settled(page, '.toc-active-indicator', '.library-toc .is-active-link')
            target = '验证结果和需要换行展示的长标题'
            outline_frames = _selection_frames(page, f'.library-toc a[title="{target}"]', '.toc-active-indicator')
            assert len({round(sample["y"]) for sample in outline_frames["samples"]}) > 3
            _assert_selection_settled(page, '.toc-active-indicator', '.library-toc .is-active-link')
            expect(toc.get_by_role("link", name=target, exact=True)).to_have_class(re.compile(r"\bis-active-link\b"))
            for theme in ["light", "dark"]:
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                assert page.locator('.category-active-indicator').evaluate("e => getComputedStyle(e).backgroundColor === getComputedStyle(document.querySelector('.record-active-indicator')).backgroundColor")
                page.screenshot(path=str(tmp_path / f"{module}-row-category-outline-{theme}.png"), animations="disabled")
            # Collapsing and re-expanding the category pane changes the outline width.
            page.get_by_role("button", name="收起分类浏览", exact=True).click()
            _assert_selection_settled(page, '.toc-active-indicator', '.library-toc .is-active-link')
            page.get_by_role("button", name="展开分类浏览", exact=True).click()
            _assert_selection_settled(page, '.toc-active-indicator', '.library-toc .is-active-link')
            page.get_by_role("button", name="大屏阅读", exact=True).click()
            expect(page.get_by_role("button", name="退出大屏阅读", exact=True)).to_be_visible()
            _assert_selection_settled(page, '.toc-active-indicator', '.library-toc .is-active-link')
            page.get_by_role("button", name="退出大屏阅读", exact=True).click()
            page.get_by_role("button", name="关闭预览", exact=True).click()
            expect(page.locator('.record-active-indicator')).to_have_count(0)
            (tmp_path / "selection-frames.json").write_text(json.dumps({"row": frames, "category": category_frames, "outline": outline_frames}, indent=2), encoding="utf-8")
            assert not errors
        finally:
            browser.close()
            client.close()
