"""Exercise vault disclosures and restore only against an isolated synthetic vault."""
import json

import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import OWNER, _api_client, _edge, _login


@pytest.mark.browser
def test_vault_daily_ui_csv_and_restore_confirmation(live_server, tmp_path):
    client, _ = _api_client(live_server)
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        try:
            page = context.new_page()
            # Verify the generated download without leaving a download target in the old Edge driver.
            page.add_init_script("""const originalClick = HTMLAnchorElement.prototype.click;
                HTMLAnchorElement.prototype.click = function () {
                    if (this.download) { window.__vaultDownloadName = this.download; return; }
                    return originalClick.call(this);
                };""")
            page.set_default_timeout(10_000)
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="密码保险箱", exact=True).click()
            page.get_by_placeholder("登录密码", exact=True).fill(OWNER["password"])
            page.get_by_role("button", name="验证 30 分钟", exact=True).click()
            expect(page.get_by_text("已验证", exact=True)).to_be_visible()
            page.get_by_label("保险箱主密码", exact=True).fill("test-only-ui-master")
            page.get_by_label("确认主密码", exact=True).fill("test-only-ui-master")
            page.get_by_role("button", name="创建保险箱", exact=True).click()
            expect(page.get_by_text("恢复密钥待备份", exact=True)).to_be_visible(timeout=20_000)
            lock = page.get_by_role("button", name="立即锁定", exact=True)
            assert lock.bounding_box()["x"] > page.get_by_role("heading", name="密码保险箱", exact=True).bounding_box()["x"] + 500
            recovery = page.locator(".vault-recovery-status")
            expect(recovery.locator(".vault-recovery-command")).not_to_be_visible()
            recovery.locator("summary").focus()
            page.keyboard.press("Enter")
            expect(recovery.locator(".vault-recovery-command")).to_be_visible()
            recovery.locator("summary").press("Enter")
            expect(recovery.locator(".vault-recovery-command")).not_to_be_visible()

            for theme, width in [("light", 1440), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(animations="disabled", path=str(tmp_path / f"vault-daily-{theme}-{width}.png"))
                page.get_by_role("button", name="导入 Edge 密码", exact=True).click()
                importer = page.get_by_role("dialog", name="导入 Edge 密码", exact=True)
                expect(importer.get_by_text("CSV 含明文密码。核对导入结果后，请自行删除原文件。", exact=True)).to_be_visible()
                expect(importer.get_by_text("只在本机浏览器内解析和加密", exact=False)).not_to_be_visible()
                importer.locator("summary").filter(has_text="导入规则").click()
                expect(importer.get_by_text("相同网址、账号和密码会跳过", exact=False)).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(animations="disabled", path=str(tmp_path / f"edge-import-{theme}-{width}.png"))
                importer.get_by_role("button", name="取消", exact=True).click()

            page.get_by_role("button", name="导入 Edge 密码", exact=True).click()
            importer = page.get_by_role("dialog", name="导入 Edge 密码", exact=True)
            importer.get_by_label("CSV 文件", exact=True).set_input_files({
                "name": "edge-demo.csv", "mimeType": "text/csv",
                "buffer": "name,url,username,password\n导入演示条目,https://example.test,demo_user,synthetic-secret\n无密码,https://empty.test,demo_empty,\n".encode("utf-8"),
            })
            expect(importer.locator(".import-counts")).to_contain_text("待处理 1 条")
            expect(importer.locator(".import-counts")).to_contain_text("无密码 1 条")
            expect(importer.get_by_text("synthetic-secret", exact=True)).to_have_count(0)
            importer.get_by_role("button", name="确认加密导入", exact=True).click()
            expect(importer.get_by_role("status")).to_contain_text("新增 1 条", timeout=20_000)
            importer.get_by_role("button", name="取消", exact=True).click()
            expect(page.get_by_role("heading", name="导入演示条目", exact=True)).to_be_visible()

            with page.expect_response(lambda response: response.url.endswith("/api/vault/backup")) as backup_response:
                page.get_by_role("button", name="加密备份", exact=True).click()
            backup = tmp_path / "vault-ui-encrypted.json"
            backup.write_text(json.dumps(backup_response.value.json()), encoding="utf-8")
            assert page.evaluate("window.__vaultDownloadName").startswith("dba-vault-encrypted-")
            assert "synthetic-secret" not in backup.read_text(encoding="utf-8")
            restore_requests = []
            page.on("request", lambda request: restore_requests.append(request) if "/api/vault/backup/restore" in request.url else None)
            page.get_by_label("选择加密备份", exact=True).set_input_files(str(backup))
            restore = page.get_by_role("dialog", name="恢复加密备份", exact=True)
            expect(restore.get_by_text("恢复会替换当前保险箱全部密文，现有条目将被备份内容覆盖。", exact=True)).to_be_visible()
            restore.get_by_role("button", name="确认恢复", exact=True).focus()
            page.keyboard.press("Tab")
            expect(restore.get_by_role("button", name="关闭恢复", exact=True)).to_be_focused()
            page.keyboard.press("Shift+Tab")
            expect(restore.get_by_role("button", name="确认恢复", exact=True)).to_be_focused()
            assert not restore_requests
            for theme, width in [("light", 1440), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(animations="disabled", path=str(tmp_path / f"vault-restore-{theme}-{width}.png"))
            restore.get_by_role("button", name="取消", exact=True).click()
            assert not restore_requests
            page.get_by_label("选择加密备份", exact=True).set_input_files(str(backup))
            restore.get_by_role("button", name="确认恢复", exact=True).click()
            expect(page.get_by_role("heading", name="保险箱已锁定", exact=True)).to_be_visible()
            assert len(restore_requests) == 1
            page.get_by_label("保险箱主密码", exact=True).fill("test-only-ui-master")
            page.get_by_role("button", name="解锁", exact=True).click()
            expect(page.get_by_role("heading", name="导入演示条目", exact=True)).to_be_visible()
            page.get_by_role("button", name="立即锁定", exact=True).click()
            expect(page.get_by_role("heading", name="保险箱已锁定", exact=True)).to_be_visible()
        finally:
            context.close()
            browser.close()
            client.close()


@pytest.mark.browser
def test_import_disclosures_and_security_risks_on_small_screens(live_server, tmp_path, monkeypatch):
    client, _ = _api_client(live_server)
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="知识库", exact=True).click()
            page.route("**/api/scan/run", lambda route: route.fulfill(json={"items": [
                {"kind": "article", "name": "锁等待", "path": "D:/demo/MySQL/锁等待.md", "db_type": "MySQL", "category": "排障手册"},
                {"kind": "article", "name": "备份恢复", "path": "D:/demo/MySQL/备份恢复.pdf", "db_type": "MySQL", "category": "备份恢复"},
            ], "already_indexed": {"article": 1}}))
            page.get_by_role("button", name="目录批量导入", exact=True).click()
            importer = page.get_by_role("dialog", name="批量导入文档", exact=True)
            importer.get_by_role("textbox", name="扫描目录", exact=True).fill("D:/demo/MySQL")
            importer.get_by_role("button", name="扫描预览", exact=True).click()
            expect(importer.get_by_text("已选 2 / 2 个文件", exact=True)).to_be_visible()
            importer.get_by_role("checkbox", name="导入：备份恢复.pdf", exact=True).uncheck()
            expect(importer.get_by_text("已选 1 / 2 个文件", exact=True)).to_be_visible()
            expect(importer.get_by_text("根据目录识别数据库与分类。", exact=False)).not_to_be_visible()
            importer.locator("summary").click()
            expect(importer.get_by_text("根据目录识别数据库与分类。", exact=False)).to_be_visible()
            for theme, width in [("light", 1440), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(animations="disabled", path=str(tmp_path / f"directory-import-{theme}-{width}.png"))
            importer.get_by_role("button", name="关闭批量导入", exact=True).click()
            from backend import auth
            monkeypatch.setattr(auth, "_desktop_token", "test-only-ui-settings")
            page.goto(f"{live_server}/#desktop=test-only-ui-settings")
            page.locator(".sidebar-foot").get_by_role("button", name="设置", exact=True).click()
            settings = page.get_by_role("dialog", name="设置", exact=True)
            settings.get_by_role("button", name="密码库安全", exact=True).click()
            expect(settings.get_by_text("使用此 Windows 账户的人可自动访问保险箱。", exact=True)).to_be_visible()
            expect(settings.get_by_text("主密码通过 Argon2id", exact=False)).not_to_be_visible()
            expect(settings.locator(".vault-recovery-command")).not_to_be_visible()
            settings.locator("summary").filter(has_text="恢复密钥与备份方法").click()
            expect(settings.locator(".vault-recovery-command")).to_be_visible()
            for theme, width in [("light", 1440), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(animations="disabled", path=str(tmp_path / f"vault-security-{theme}-{width}.png"))
        finally:
            browser.close()
            client.close()
