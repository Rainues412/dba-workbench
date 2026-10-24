"""Exercise title toggling and real panel transitions in the production build."""
import json

import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login
from test_library_resizable_browser import _drag


def _sample_widths(page):
    page.evaluate("""() => {
      window.__previewWidths = [];
      const panel = document.querySelector('.library-panels > [data-panel]:has(> .library-preview-pane)');
      const started = performance.now();
      function sample(now) {
        window.__previewWidths.push(panel.getBoundingClientRect().width);
        if (now - started < 320) requestAnimationFrame(sample);
      }
      requestAnimationFrame(sample);
    }""")


@pytest.mark.browser
@pytest.mark.parametrize(("module", "label"), [("articles", "知识库"), ("scripts", "脚本库")])
def test_title_toggles_animate_reset_width_and_keep_list_state(live_server, tmp_path, monkeypatch, module, label):
    from backend import local_capabilities
    from backend.config import Settings
    monkeypatch.setattr(local_capabilities, "_enrolled_roots", set())
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true", "DBA_ALLOWED_ROOTS": str(tmp_path), "DBA_ALLOWED_LOCAL_ACTIONS": "open,folder",
    }))
    client, csrf = _api_client(live_server)
    for number in (1, 2):
        sample = tmp_path / f"toggle-{number}.md"
        sample.write_text(f"# 第{number}条正文\n\n保持原文件预览。", encoding="utf-8")
        client.post(f"/api/{module}/", json={"title": f"切换预览-{number}", "file_path": str(sample)}, headers={"X-CSRF-Token": csrf}).raise_for_status()
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1680, "height": 1000})
            page.add_init_script(f"localStorage.setItem({json.dumps(f'dba-library-layout:{module}')}, JSON.stringify({{collapsed:false,list:20}}))")
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name=label, exact=True).click()
            first = page.get_by_role("button", name="预览：切换预览-1", exact=True)
            second = page.get_by_role("button", name="预览：切换预览-2", exact=True)
            first.click()
            expect(page.locator(".library-markdown").get_by_role("heading", name="第1条正文")).to_be_visible()
            pane = page.locator(".library-panels > [data-panel]:has(> .library-preview-pane)")
            default_width = pane.bounding_box()["width"]
            list_width = page.locator(".library-list-pane").bounding_box()["width"]
            assert abs(default_width / (default_width + list_width) * 100 - 50) < 1
            _drag(page, -120)
            page.wait_for_timeout(250)
            width = pane.bounding_box()["width"]
            categories = page.locator(".library-categories").bounding_box()["width"]
            saved = page.evaluate("key => localStorage.getItem(key)", f"dba-library-layout:{module}")
            page.evaluate("window.__originalList = document.querySelector('.library-record-list')")
            address = page.url
            _sample_widths(page)
            first.click()
            expect(first).to_have_attribute("aria-pressed", "false")
            expect(page.locator(".library-preview")).to_have_count(0)
            page.wait_for_timeout(100)
            closing = page.evaluate("window.__previewWidths")
            assert any(3 < value < width - 3 for value in closing), closing
            assert pane.bounding_box()["width"] < 1
            assert page.locator(".library-resize-handle").bounding_box()["width"] < 1
            assert page.evaluate("window.__originalList === document.querySelector('.library-record-list')")
            assert page.url == address
            assert page.evaluate("key => localStorage.getItem(key)", f"dba-library-layout:{module}") == saved
            _sample_widths(page)
            first.focus()
            page.keyboard.press("Enter")
            expect(page.locator(".library-markdown").get_by_role("heading", name="第1条正文")).to_be_visible()
            page.wait_for_timeout(350)
            opening = page.evaluate("window.__previewWidths")
            assert any(3 < value < width - 3 for value in opening), opening
            assert abs(pane.bounding_box()["width"] - default_width) < 2
            assert abs(page.locator(".library-categories").bounding_box()["width"] - categories) < 1
            second.click()
            expect(page.locator(".library-markdown").get_by_role("heading", name="第2条正文")).to_be_visible()
            expect(second).to_have_attribute("aria-pressed", "true")
            expect(first).to_have_attribute("aria-pressed", "false")
            # Rapid reversal keeps the same viewer mounted and cancels the pending removal.
            page.evaluate("""() => { const title = document.querySelector('.library-record-title[aria-pressed=true]'); title.click(); title.click(); }""")
            page.wait_for_timeout(300)
            expect(second).to_have_attribute("aria-pressed", "true")
            expect(page.locator(".library-markdown").get_by_role("heading", name="第2条正文")).to_be_visible()
            page.evaluate("document.documentElement.dataset.theme = 'dark'")
            page.screenshot(path=str(tmp_path / f"{module}-toggle-dark.png"))
            page.emulate_media(reduced_motion="reduce")
            duration = pane.evaluate("element => getComputedStyle(element).transitionDuration")
            assert float(duration.removesuffix("s")) < 0.001
            second.click()
            expect(page.locator(".library-preview")).to_have_count(0)
            page.set_viewport_size({"width": 390, "height": 844})
            page.emulate_media(reduced_motion="no-preference")
            first.click()
            dialog = page.get_by_role("dialog")
            expect(dialog).to_be_visible()
            expect(dialog.locator(".library-markdown").get_by_role("heading", name="第1条正文")).to_be_visible()
            dialog.get_by_role("button", name="关闭预览", exact=True).click()
            expect(page.locator(".library-preview")).to_have_count(0)
            expect(first).to_be_focused()
            first.click()
            expect(page.get_by_role("dialog")).to_be_visible()
            page.keyboard.press("Escape")
            expect(page.locator(".library-preview")).to_have_count(0)
            assert page.evaluate("document.body.style.overflow") != "hidden"
            (tmp_path / "motion-widths.json").write_text(json.dumps({"closing": closing, "opening": opening}), encoding="utf-8")
        finally:
            browser.close()
            client.close()
