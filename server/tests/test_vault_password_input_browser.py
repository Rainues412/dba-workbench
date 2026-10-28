"""Password reveal in the entry editor, using only isolated synthetic secrets."""
import json

import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import OWNER, _api_client, _edge, _login


@pytest.mark.browser
def test_entry_password_toggle_preserves_encryption_and_editor_privacy(live_server, tmp_path):
    client, _ = _api_client(live_server)
    first_password = "test-only-entry-password-42!"
    updated_password = "test-only-updated-password-84!"
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="密码保险箱", exact=True).click()
            page.get_by_placeholder("登录密码", exact=True).fill(OWNER["password"])
            page.get_by_role("button", name="验证 30 分钟", exact=True).click()
            page.get_by_text("已验证", exact=True).wait_for()
            page.get_by_label("保险箱主密码", exact=True).fill("test-only-master-password")
            page.get_by_label("确认主密码", exact=True).fill("test-only-master-password")
            page.get_by_role("button", name="创建保险箱", exact=True).click()
            page.get_by_role("heading", name="请备份管理员恢复密钥").wait_for(timeout=20_000)
            writes = []
            page.on("request", lambda request: writes.append({"method": request.method, "body": request.post_data or ""})
                    if request.method in {"POST", "PUT"} and "/api/vault/items" in request.url else None)
            page.get_by_role("button", name="新增条目", exact=True).click()
            editor = page.get_by_role("dialog", name="新增保险箱条目", exact=True)
            expect(editor.get_by_label("账号名", exact=True)).to_have_value("")
            expect(editor.get_by_label("密码", exact=True)).to_have_value("")
            expect(editor.locator("form")).to_have_attribute("autocomplete", "off")
            expect(editor.get_by_label("账号名", exact=True)).to_have_attribute("autocomplete", "off")
            expect(editor.get_by_label("密码", exact=True)).to_have_attribute("autocomplete", "new-password")
            editor.get_by_label("名称或备注", exact=True).fill("录入查看按钮验收")
            editor.get_by_label("账号名", exact=True).fill("test-user")
            password = editor.get_by_label("密码", exact=True)
            expect(password).to_have_attribute("type", "password")
            password.fill(first_password)

            for width, theme in [(1440, "light"), (1440, "dark"), (390, "light"), (390, "dark")]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                password.focus()
                page.keyboard.press("Tab")
                reveal = editor.get_by_role("button", name="显示密码", exact=True)
                expect(reveal).to_be_focused()
                expect(reveal).to_have_attribute("type", "button")
                expect(reveal).to_have_attribute("aria-pressed", "false")
                page.keyboard.press("Space")
                expect(password).to_have_attribute("type", "text")
                expect(password).to_have_value(first_password)
                hide = editor.get_by_role("button", name="隐藏密码", exact=True)
                expect(hide).to_have_attribute("aria-pressed", "true")
                bounds, input_bounds = hide.bounding_box(), password.bounding_box()
                assert abs(bounds["y"] + bounds["height"] / 2 - input_bounds["y"] - input_bounds["height"] / 2) < 1
                assert bounds["x"] + bounds["width"] <= input_bounds["x"] + input_bounds["width"]
                assert password.evaluate("el => parseFloat(getComputedStyle(el).paddingRight)") > bounds["width"]
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                editor.screenshot(path=str(tmp_path / f"entry-reveal-{width}-{theme}.png"))
                page.keyboard.press("Enter")
                expect(password).to_have_attribute("type", "password")
                expect(password).to_have_value(first_password)
                assert not writes
                password.focus()
                editor.get_by_role("button", name="显示密码", exact=True).click()
                expect(password).to_be_focused()
                expect(password).to_have_attribute("type", "text")
                editor.get_by_role("button", name="隐藏密码", exact=True).click()
                expect(password).to_have_attribute("type", "password")
                assert not writes

            # Saving while visible must still use the existing browser encryption.
            editor.get_by_role("button", name="显示密码", exact=True).click()
            editor.get_by_role("button", name="保存", exact=True).click()
            expect(editor).to_have_count(0)
            card = page.locator(".vault-card").filter(has=page.get_by_role("heading", name="录入查看按钮验收", exact=True))
            expect(card).to_be_visible()
            expect(card.locator(".secret-value code")).not_to_have_text(first_password)
            card.get_by_role("button", name="编辑", exact=True).click()
            editor = page.get_by_role("dialog", name="编辑保险箱条目", exact=True)
            password = editor.get_by_label("密码", exact=True)
            expect(password).to_have_attribute("type", "password")
            expect(password).to_have_value(first_password)
            editor.get_by_role("button", name="显示密码", exact=True).click()
            password.fill(updated_password)
            editor.get_by_role("button", name="保存", exact=True).click()
            expect(editor).to_have_count(0)
            assert [write["method"] for write in writes] == ["POST", "PUT"]
            for write in writes:
                payload = json.loads(write["body"])
                assert payload["ciphertext"]
                assert "password" not in payload and "site" not in payload
                assert first_password not in write["body"] and updated_password not in write["body"]
            assert json.loads(writes[1]["body"])["revision"] == 1
            card.get_by_role("button", name="编辑", exact=True).click()
            editor = page.get_by_role("dialog", name="编辑保险箱条目", exact=True)
            expect(editor.get_by_label("密码", exact=True)).to_have_attribute("type", "password")
            expect(editor.get_by_label("密码", exact=True)).to_have_value(updated_password)
            editor.get_by_role("button", name="显示密码", exact=True).click()
            editor.get_by_role("button", name="取消", exact=True).click()
            page.get_by_role("button", name="新增条目", exact=True).click()
            editor = page.get_by_role("dialog", name="新增保险箱条目", exact=True)
            expect(editor.get_by_label("密码", exact=True)).to_have_attribute("type", "password")
            expect(editor.get_by_label("密码", exact=True)).to_have_value("")
            expect(editor.get_by_label("账号名", exact=True)).to_have_value("")
            editor.get_by_role("button", name="取消", exact=True).click()
            page.get_by_role("button", name="立即锁定", exact=True).click()
            expect(page.get_by_role("heading", name="保险箱已锁定")).to_be_visible()
        finally:
            browser.close()
            client.close()
