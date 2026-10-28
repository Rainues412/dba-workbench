"""Idle deadline and reload behavior, using only isolated synthetic vault data."""
import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import OWNER, _api_client, _edge, _login


@pytest.mark.browser
def test_vault_uses_fifteen_minute_idle_deadline_and_locks_on_reload(live_server, tmp_path):
    client, _ = _api_client(live_server)
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="密码保险箱", exact=True).click()
            page.get_by_placeholder("登录密码", exact=True).fill(OWNER["password"])
            page.get_by_role("button", name="验证 30 分钟", exact=True).click()
            expect(page.get_by_text("已验证", exact=True)).to_be_visible()
            page.get_by_label("保险箱主密码", exact=True).fill("test-only-master-password")
            page.get_by_label("确认主密码", exact=True).fill("test-only-master-password")
            page.get_by_role("button", name="创建保险箱", exact=True).click()
            expect(page.get_by_role("button", name="立即锁定", exact=True)).to_be_visible()

            # Simulate elapsed wall time on resume, without shortening the product timeout.
            page.evaluate("""() => {
                const realNow = Date.now;
                window.testIdleOffset = 6 * 60 * 1000;
                Date.now = () => realNow() + window.testIdleOffset;
                window.dispatchEvent(new Event('focus'));
            }""")
            expect(page.get_by_role("button", name="立即锁定", exact=True)).to_be_visible()
            expect(page.get_by_role("heading", name="保险箱已锁定", exact=True)).to_have_count(0)
            page.evaluate("window.testIdleOffset = 15 * 60 * 1000 + 1000; window.dispatchEvent(new Event('focus'))")
            expect(page.get_by_role("heading", name="保险箱已锁定", exact=True)).to_be_visible()
            expect(page.get_by_text("保险箱已因闲置自动锁定", exact=True)).to_be_visible()
            expect(page.get_by_text("刷新页面后需重新解锁；连续 15 分钟无操作将自动锁定。", exact=True)).to_be_visible()
            expect(page.get_by_text("已验证", exact=True)).to_be_visible()

            page.get_by_label("保险箱主密码", exact=True).fill("test-only-master-password")
            page.get_by_role("button", name="解锁", exact=True).click()
            expect(page.get_by_role("button", name="立即锁定", exact=True)).to_be_visible()
            page.reload()
            expect(page.get_by_role("heading", name="保险箱已锁定", exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="立即锁定", exact=True)).to_have_count(0)
            for width, theme in [(1440, "light"), (390, "dark")]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                expect(page.get_by_text("刷新页面后需重新解锁；连续 15 分钟无操作将自动锁定。", exact=True)).to_be_visible()
                hint = page.locator(".vault-lock-hint").bounding_box()
                unlock = page.get_by_role("button", name="解锁", exact=True).bounding_box()
                assert hint["y"] >= unlock["y"] + unlock["height"]
                assert abs(hint["x"] - unlock["x"]) < 1
                assert abs(hint["width"] - unlock["width"]) < 1
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.locator(".vault-gate").screenshot(path=str(tmp_path / f"idle-policy-{width}-{theme}.png"))
        finally:
            browser.close()
            client.close()
