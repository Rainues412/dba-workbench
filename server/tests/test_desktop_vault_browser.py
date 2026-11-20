"""The desktop vault uses a single master password across create, lock and unlock."""
import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _edge


@pytest.mark.browser
def test_device_auto_unlock_survives_navigation_but_respects_lock_and_disable(client, live_server, monkeypatch):
    from backend import auth, vault_device
    from test_vault import MASTER_PASSWORD, desktop_unlock, initialize_vault

    if not vault_device.available():
        pytest.skip("Windows Credential Manager is required")
    monkeypatch.setattr(auth, "_desktop_token", "test-only-auto-unlock-navigation")
    initialize_vault(client, [{"question": "测试问题", "answer": "test-only-answer"}])
    grant = {"X-DBA-Vault-Token": desktop_unlock(client, MASTER_PASSWORD).json()["token"]}
    route = "/api/vault/auto-unlock"
    try:
        assert client.put(route, json={"enabled": True}, headers=grant).status_code == 200
        with sync_playwright() as playwright:
            browser = _edge(playwright)
            try:
                page = browser.new_page(viewport={"width": 1320, "height": 820})
                page.goto(f"{live_server}/#desktop=test-only-auto-unlock-navigation")
                nav = page.get_by_role("navigation", name="主导航")
                vault = nav.get_by_role("link", name="密码保险箱", exact=True)

                # A manually unlocked vault must remain convenient to revisit.
                vault.click()
                unlocked = page.get_by_role("button", name="立即锁定")
                expect(unlocked).to_be_visible()
                for _ in range(2):
                    nav.get_by_role("link", name="工作台", exact=True).click()
                    vault.click()
                    expect(unlocked).to_be_visible()

                unlocked.click()
                gate = page.get_by_role("region", name="解锁保险箱")
                expect(gate).to_be_visible()
                nav.get_by_role("link", name="工作台", exact=True).click()
                vault.click()
                expect(gate).to_be_visible()
                expect(unlocked).to_have_count(0)
                gate.get_by_label("保险箱主密码").fill(MASTER_PASSWORD)
                gate.get_by_role("button", name="解锁", exact=True).click()
                expect(unlocked).to_be_visible()
                nav.get_by_role("link", name="工作台", exact=True).click()
                vault.click()
                expect(unlocked).to_be_visible()

                page.keyboard.press("Control+,")
                settings = page.get_by_role("dialog", name="设置")
                settings.get_by_role("button", name="密码库安全").click()
                auto = settings.get_by_role("switch", name="在这台电脑上自动解锁")
                expect(auto).to_be_checked()
                auto.click()
                expect(settings.get_by_role("status")).to_contain_text("已保存")
                expect(auto).not_to_be_checked()
                page.keyboard.press("Escape")
                nav.get_by_role("link", name="工作台", exact=True).click()
                vault.click()
                expect(gate).to_be_visible()
                expect(unlocked).to_have_count(0)
            finally:
                browser.close()
    finally:
        vault_device.delete_key(1)


@pytest.mark.browser
def test_desktop_vault_uses_only_the_master_password(live_server, monkeypatch):
    from backend import auth

    monkeypatch.setattr(auth, "_desktop_token", "test-only-desktop-vault-launch")
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1320, "height": 820})
            page.goto(f"{live_server}/#desktop=test-only-desktop-vault-launch")
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="密码保险箱", exact=True).click()
            gate = page.get_by_role("region", name="创建本地保险箱")
            master = gate.get_by_label("保险箱主密码")
            expect(master).to_be_focused()
            expect(page.get_by_role("heading", name="敏感操作验证")).to_have_count(0)
            for width, theme in [(1320, "light"), (980, "dark"), (390, "dark")]:
                page.set_viewport_size({"width": width, "height": 820})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                assert gate.evaluate("gate => gate.getBoundingClientRect().right <= innerWidth")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            master.fill("test-only-desktop-master")
            gate.get_by_label("确认主密码").fill("test-only-desktop-master")
            gate.get_by_label("问题 1").fill("测试问题一")
            gate.get_by_label("答案 1").fill("测试答案一")
            gate.get_by_role("button", name="添加问题").click()
            gate.get_by_label("问题 2", exact=True).fill("测试问题二")
            gate.get_by_label("答案 2").fill("测试答案二")
            gate.get_by_role("button", name="显示主密码").click()
            expect(master).to_have_attribute("type", "text")
            gate.get_by_role("button", name="创建并解锁").click()
            expect(page.get_by_role("heading", name="请备份管理员恢复密钥")).to_be_visible(timeout=20_000)
            page.get_by_role("button", name="新增条目").click()
            editor = page.get_by_role("dialog", name="新增保险箱条目")
            editor.get_by_label("名称或备注").fill("桌面保险箱测试条目")
            editor.get_by_label("密码", exact=True).fill("test-only-desktop-secret")
            editor.get_by_role("button", name="保存", exact=True).click()
            expect(page.get_by_role("heading", name="桌面保险箱测试条目")).to_be_visible()

            page.get_by_role("button", name="立即锁定").click()
            gate = page.get_by_role("region", name="解锁保险箱")
            expect(page.get_by_role("heading", name="桌面保险箱测试条目")).to_have_count(0)
            gate.get_by_role("button", name="忘记主密码").click()
            dialog = page.get_by_role("dialog", name="恢复保险箱主密码")
            dialog.get_by_label("测试问题一").fill("测试答案一")
            dialog.get_by_label("测试问题二").fill("错误答案")
            dialog.get_by_role("button", name="验证答案").click()
            expect(dialog.get_by_role("alert")).to_contain_text("密保答案有误")
            dialog.get_by_label("测试问题二").fill("测试答案二")
            dialog.get_by_role("button", name="验证答案").click()
            dialog.get_by_label("新主密码", exact=True).fill("test-only-reset-master")
            dialog.get_by_label("确认新主密码").fill("test-only-reset-master")
            dialog.get_by_role("button", name="确认重置").click()
            expect(dialog).to_have_count(0)
            master = gate.get_by_label("保险箱主密码")
            master.fill("test-only-incorrect-master")
            gate.get_by_role("button", name="解锁", exact=True).click()
            expect(page.get_by_role("alert")).to_contain_text("主密码错误")
            master.fill("test-only-reset-master")
            gate.get_by_role("button", name="解锁", exact=True).click()
            expect(page.get_by_role("heading", name="桌面保险箱测试条目")).to_be_visible()

            page.keyboard.press("Control+,")
            settings = page.get_by_role("dialog", name="设置")
            settings.get_by_role("button", name="密码库安全").click()
            settings.get_by_role("button", name="修改", exact=True).click()
            settings.get_by_label("当前主密码").fill("test-only-reset-master")
            settings.get_by_label("新主密码", exact=True).fill("test-only-changed-master")
            settings.get_by_label("确认新主密码").fill("test-only-changed-master")
            settings.get_by_role("button", name="保存新主密码").click()
            expect(settings.get_by_role("status")).to_contain_text("已保存")
            page.keyboard.press("Escape")
            expect(gate).to_be_visible()
            gate.get_by_label("保险箱主密码").fill("test-only-changed-master")
            gate.get_by_role("button", name="解锁", exact=True).click()
            expect(page.get_by_role("heading", name="桌面保险箱测试条目")).to_be_visible()
        finally:
            browser.close()
