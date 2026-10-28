"""Foreground refresh and expiring grants, with isolated sessions and vault data."""
import datetime as dt
import re
import sqlite3

import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import OWNER, _api_client, _edge, _login


@pytest.mark.browser
def test_server_reauth_rejection_updates_badge_without_refresh(live_server, isolated_app):
    _, database = isolated_app
    client, _ = _api_client(live_server)
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="密码保险箱", exact=True).click()
            page.get_by_placeholder("登录密码", exact=True).fill(OWNER["password"])
            page.get_by_role("button", name="验证 30 分钟", exact=True).click()
            expect(page.locator(".reauth-state .badge")).to_have_text("已验证")
            page.get_by_label("保险箱主密码", exact=True).fill("test-only-master-password")
            page.get_by_label("确认主密码", exact=True).fill("test-only-master-password")
            page.get_by_role("button", name="创建保险箱", exact=True).click()
            page.get_by_role("heading", name="请备份管理员恢复密钥").wait_for(timeout=20_000)
            # Only the server knows about this expiry; no focus event, reload or clock change.
            with sqlite3.connect(database) as conn:
                conn.execute("UPDATE sessions SET reauthenticated_until = ?", ("2000-01-01T00:00:00+00:00",))
            with page.expect_response(lambda response: response.url.endswith("/api/vault/backup")) as rejected:
                page.get_by_role("button", name="加密备份", exact=True).click()
            assert rejected.value.status == 403
            expect(page.locator(".reauth-state .badge")).to_have_text("已过期", timeout=5000)
            expect(page.get_by_label("验证剩余时间", exact=True)).to_have_count(0)
            expect(page.get_by_role("status").filter(has_text="敏感操作验证已过期")).to_be_visible()
        finally:
            browser.close()
            client.close()


@pytest.mark.browser
def test_grant_expiry_refresh_preserves_draft_and_updates_login(live_server, isolated_app, tmp_path):
    _, database = isolated_app
    client, _ = _api_client(live_server)
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="密码保险箱", exact=True).click()
            page.get_by_placeholder("登录密码", exact=True).fill(OWNER["password"])
            page.get_by_role("button", name="验证 30 分钟", exact=True).click()
            expect(page.get_by_label("验证剩余时间", exact=True)).to_have_text(re.compile(r"剩余 (29:|30:)[0-9]{2}"))
            page.get_by_label("保险箱主密码", exact=True).fill("test-only-master-password")
            page.get_by_label("确认主密码", exact=True).fill("test-only-master-password")
            page.get_by_role("button", name="创建保险箱", exact=True).click()
            page.get_by_role("heading", name="请备份管理员恢复密钥").wait_for(timeout=20_000)
            page.get_by_role("button", name="新增条目", exact=True).click()
            editor = page.get_by_role("dialog", name="新增保险箱条目", exact=True)
            editor.get_by_label("名称或备注", exact=True).fill("自动刷新保留草稿")
            editor.get_by_label("密码", exact=True).fill("test-only-draft-secret")
            editor.get_by_role("button", name="显示密码", exact=True).click()
            navigations = []
            page.on("framenavigated", lambda frame: navigations.append(frame.url) if frame == page.main_frame else None)

            # Failed background reads must not unmount the editor or discard its draft.
            page.route("**/api/vault/profile", lambda route: route.fulfill(status=503, json={"detail": "synthetic temporary outage"}))
            page.evaluate("() => { window.testOriginalNow = Date.now; Date.now = () => window.testOriginalNow() + 16000; }")
            page.evaluate("window.dispatchEvent(new Event('focus'))")
            expect(page.get_by_text("保险箱状态暂未同步，恢复连接后会自动重试。", exact=True)).to_be_visible()
            expect(editor.get_by_label("名称或备注", exact=True)).to_have_value("自动刷新保留草稿")
            page.unroute("**/api/vault/profile")
            page.evaluate("window.dispatchEvent(new Event('focus'))")
            expect(page.get_by_text("保险箱状态暂未同步，恢复连接后会自动重试。", exact=True)).to_have_count(0)
            page.evaluate("Date.now = window.testOriginalNow; window.dispatchEvent(new Event('pageshow'))")
            expect(page.get_by_label("验证剩余时间", exact=True)).to_have_text(re.compile(r"剩余 (29:|30:)[0-9]{2}"))
            expect(editor.get_by_label("密码", exact=True)).to_have_attribute("type", "text")

            # Shorten only the isolated database's grant instead of waiting 30 minutes.
            until = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=5)).isoformat()
            with sqlite3.connect(database) as conn:
                conn.execute("UPDATE sessions SET reauthenticated_until = ?", (until,))
            with page.expect_response(lambda response: response.url.endswith("/api/auth/status")):
                page.evaluate("window.dispatchEvent(new Event('focus'))")
            expect(page.get_by_label("验证剩余时间", exact=True)).to_have_text(re.compile(r"剩余 00:0[1-5]"))
            expect(editor.get_by_label("名称或备注", exact=True)).to_have_value("自动刷新保留草稿")
            expect(editor.get_by_role("alert")).to_contain_text("敏感操作验证已过期", timeout=10_000)
            expect(editor.get_by_label("密码", exact=True)).to_have_attribute("type", "password")
            expect(editor.get_by_label("密码", exact=True)).to_have_value("test-only-draft-secret")
            expect(editor.get_by_role("button", name="保存", exact=True)).to_be_disabled()
            expect(page.locator(".reauth-state .badge")).to_have_text("已过期")
            assert not navigations
            editor.screenshot(path=str(tmp_path / "expired-draft-preserved.png"))

            # Renew inside the open editor without discarding its fields.
            editor.get_by_label("重新验证登录密码", exact=True).fill("test-only-incorrect-password")
            with page.expect_response(lambda response: response.url.endswith("/api/auth/reauthenticate")):
                editor.get_by_role("button", name="重新验证", exact=True).click()
            expect(editor.get_by_role("button", name="重新验证", exact=True)).to_be_enabled()
            expect(editor.get_by_role("button", name="保存", exact=True)).to_be_disabled()
            expect(editor.get_by_label("名称或备注", exact=True)).to_have_value("自动刷新保留草稿")
            editor.get_by_label("重新验证登录密码", exact=True).fill(OWNER["password"])
            editor.get_by_label("重新验证登录密码", exact=True).press("Enter")
            expect(editor.get_by_role("button", name="保存", exact=True)).to_be_enabled()
            expect(editor.get_by_label("名称或备注", exact=True)).to_have_value("自动刷新保留草稿")
            editor.get_by_role("button", name="保存", exact=True).click()
            expect(page.get_by_role("heading", name="自动刷新保留草稿", exact=True)).to_be_visible()
            expect(page.get_by_text("敏感操作验证已过期，请重新输入登录密码验证。", exact=True)).to_have_count(0)

            for width, theme in [(1440, "light"), (1440, "dark"), (390, "light"), (390, "dark")]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                expect(page.get_by_label("验证剩余时间", exact=True)).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.locator(".reauth-panel").screenshot(path=str(tmp_path / f"reauth-{width}-{theme}.png"))

            # Revoked login must leave the vault automatically, without a browser reload.
            with sqlite3.connect(database) as conn:
                conn.execute("UPDATE sessions SET expires_at = ?", ("2000-01-01T00:00:00+00:00",))
            page.evaluate("window.dispatchEvent(new Event('focus'))")
            expect(page.get_by_label("用户名", exact=True)).to_be_visible()
            expect(page.locator(".vault-page")).to_have_count(0)
            assert not navigations
        finally:
            browser.close()
            client.close()


@pytest.mark.browser
def test_focus_refetches_stale_library_without_resetting_editor(live_server):
    client, csrf = _api_client(live_server)
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="知识库", exact=True).click()
            page.get_by_role("button", name="新增", exact=True).click()
            editor = page.get_by_role("dialog")
            editor.get_by_label("标题", exact=True).fill("未保存的知识库草稿")
            created = client.post("/api/articles/", json={"title": "后台新增后自动出现", "wb_db": "Oracle", "category": "日常管理"}, headers={"X-CSRF-Token": csrf})
            created.raise_for_status()
            # Simulate a suspended clock past the app's 15-second stale threshold.
            page.evaluate("""() => { const originalNow = Date.now; Date.now = () => originalNow() + 16000; }""")
            with page.expect_response(lambda response: "/api/articles/?" in response.url):
                page.evaluate("window.dispatchEvent(new Event('focus'))")
            expect(editor.get_by_label("标题", exact=True)).to_have_value("未保存的知识库草稿")
            editor.get_by_role("button", name="取消", exact=True).click()
            expect(page.get_by_role("button", name="预览：后台新增后自动出现", exact=True)).to_be_visible()
        finally:
            browser.close()
            client.close()
