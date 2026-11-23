"""Exercise vault disclosures and restore only against an isolated synthetic vault."""
import json
import os

import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import OWNER, _api_client, _edge, _login


MASTER = "test-only-ui-master"
BACKUP_PASSWORD = "test-only-portable-backup"


def _backup_settings(page):
    page.locator(".sidebar-foot").get_by_role("button", name="设置", exact=True).click()
    settings = page.get_by_role("dialog", name="设置", exact=True)
    settings.get_by_role("button", name="密码库安全", exact=True).click()
    expect(settings.get_by_role("heading", name="密码库备份", exact=True)).to_be_visible()
    return settings


def _fill_backup_form(dialog):
    dialog.get_by_label("当前密码库主密码", exact=True).fill(MASTER)
    dialog.get_by_label("备份密码", exact=True).fill(BACKUP_PASSWORD)
    dialog.get_by_label("确认备份密码", exact=True).fill(BACKUP_PASSWORD)


def _capture_downloads(page):
    # Older Playwright releases can crash when Edge closes its download target.
    # Read the exact Blob passed to the download anchor before revocation.
    page.add_init_script("""const originalClick = HTMLAnchorElement.prototype.click;
        const originalUrl = URL.createObjectURL;
        const blobs = new Map();
        URL.createObjectURL = function (blob) {
            const url = originalUrl.call(this, blob);
            blobs.set(url, blob);
            return url;
        };
        HTMLAnchorElement.prototype.click = function () {
            if (!this.download) return originalClick.call(this);
            const filename = this.download;
            blobs.get(this.href).text().then(document => {
                window.__vaultDownload = {filename, document};
                window.document.body.setAttribute("data-vault-download", "ready");
            });
        };""")


def _saved_download(page, directory):
    expect(page.locator("body")).to_have_attribute("data-vault-download", "ready")
    value = page.evaluate("() => { document.body.removeAttribute('data-vault-download'); return window.__vaultDownload; }")
    destination = directory / value["filename"]
    destination.write_text(value["document"], encoding="utf-8")
    return destination

@pytest.mark.browser
def test_vault_daily_ui_csv_and_restore_confirmation(live_server, tmp_path):
    client, _ = _api_client(live_server)
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        try:
            page = context.new_page()
            _capture_downloads(page)
            page.set_default_timeout(10_000)
            _login(page, live_server)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="密码保险箱", exact=True).click()
            page.get_by_placeholder("登录密码", exact=True).fill(OWNER["password"])
            page.get_by_role("button", name="验证 30 分钟", exact=True).click()
            expect(page.get_by_text("已验证", exact=True)).to_be_visible()
            page.get_by_label("保险箱主密码", exact=True).fill("test-only-ui-master")
            page.get_by_label("确认主密码", exact=True).fill("test-only-ui-master")
            page.get_by_role("button", name="创建保险箱", exact=True).click()
            expect(page.get_by_role("button", name="立即锁定", exact=True)).to_be_visible(timeout=20_000)
            lock = page.get_by_role("button", name="立即锁定", exact=True)
            assert lock.bounding_box()["x"] > page.get_by_role("heading", name="密码保险箱", exact=True).bounding_box()["x"] + 500
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

            settings = _backup_settings(page)
            settings.get_by_role("button", name="立即备份", exact=True).click()
            dialog = page.get_by_role("dialog", name="立即备份", exact=True)
            _fill_backup_form(dialog)
            dialog.get_by_role("button", name="生成备份", exact=True).click()
            backup = _saved_download(page, tmp_path)
            document = json.loads(backup.read_text(encoding="utf-8"))
            assert document["format"] == "dba-vault-backup-v2"
            assert set(document) == {"format", "source_user_id", "salt", "nonce", "wrapped_keys", "items", "mac"}
            assert "synthetic-secret" not in backup.read_text(encoding="utf-8")

            restore_requests = []
            page.on("request", lambda request: restore_requests.append(request) if "/api/vault/backup/restore" in request.url else None)
            file_input = settings.get_by_label("选择密码库备份文件", exact=True)
            file_input.set_input_files(str(backup))
            verify = page.get_by_role("dialog", name="校验密码库备份", exact=True)
            verify.get_by_label("备份密码", exact=True).fill("wrong-backup-password")
            verify.get_by_label("当前密码库主密码", exact=True).fill(MASTER)
            verify.get_by_role("button", name="校验备份", exact=True).click()
            expect(verify.get_by_role("alert")).to_contain_text("备份密码不正确")
            verify.get_by_label("备份密码", exact=True).fill(BACKUP_PASSWORD)
            verify.get_by_role("button", name="校验备份", exact=True).click()
            restore = page.get_by_role("dialog", name="确认恢复密码库", exact=True)
            expect(restore).to_contain_text("包含 1 条凭据")
            expect(restore).to_contain_text("覆盖前会自动创建安全备份")
            assert not restore_requests
            for theme, width in [("light", 1440), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(animations="disabled", path=str(tmp_path / f"vault-restore-{theme}-{width}.png"))
            restore.get_by_role("button", name="取消", exact=True).click()
            assert not restore_requests

            row = settings.get_by_role("listitem").filter(has_text=backup.name)
            row.get_by_role("button", name="恢复", exact=True).click()
            verify.get_by_label("备份密码", exact=True).fill(BACKUP_PASSWORD)
            verify.get_by_label("当前密码库主密码", exact=True).fill(MASTER)
            verify.get_by_role("button", name="校验备份", exact=True).click()
            restore.get_by_role("button", name="确认恢复", exact=True).click()
            expect(settings.get_by_text("已恢复 1 条。覆盖前的安全备份已保存。", exact=True)).to_be_visible()
            expect(settings.get_by_role("listitem").filter(has_text="恢复前安全备份")).to_be_visible()
            settings.get_by_role("button", name="完成", exact=True).click()
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
            expect(settings.get_by_text("恢复密钥与备份方法", exact=True)).to_have_count(0)
            expect(settings.get_by_label("自动备份间隔", exact=True)).to_have_value("24")
            directory = settings.locator(".preferences-content > :last-child")
            expect(directory.get_by_role("heading", name="数据目录", exact=True)).to_be_visible()
            expect(directory.locator("p")).to_have_text(str(tmp_path.resolve()) + os.sep)
            for theme, width in [("light", 1440), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                directory.scroll_into_view_if_needed()
                assert directory.evaluate("element => element.scrollWidth <= element.clientWidth")
                page.screenshot(animations="disabled", path=str(tmp_path / f"vault-security-{theme}-{width}.png"))
        finally:
            browser.close()
            client.close()


@pytest.mark.browser
def test_manual_and_automatic_files_restore_locally_and_on_a_different_vault(live_server, tmp_path, monkeypatch):
    import sqlite3

    from backend import auth, database

    source_db = database.DB_PATH
    monkeypatch.setattr(auth, "_desktop_token", "isolated-portable-vault")
    sample = "隔离密码库条目"

    def desktop_page(browser):
        context = browser.new_context(viewport={"width": 1320, "height": 900})
        page = context.new_page()
        _capture_downloads(page)
        page.set_default_timeout(12_000)
        page.goto(f"{live_server}/#desktop=isolated-portable-vault")
        return context, page

    def unlock_and_check(page, password):
        page.get_by_role("navigation", name="主导航").get_by_role("link", name="密码保险箱", exact=True).click()
        gate = page.get_by_role("region", name="解锁保险箱")
        gate.get_by_label("保险箱主密码", exact=True).fill(password)
        gate.get_by_role("button", name="解锁", exact=True).click()
        expect(page.get_by_role("heading", name=sample, exact=True)).to_be_visible()

    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            context, page = desktop_page(browser)
            page.get_by_role("navigation", name="主导航").get_by_role("link", name="密码保险箱", exact=True).click()
            gate = page.get_by_role("region", name="创建本地保险箱")
            gate.get_by_label("保险箱主密码", exact=True).fill(MASTER)
            gate.get_by_label("确认主密码", exact=True).fill(MASTER)
            gate.get_by_label("问题 1", exact=True).fill("来源密保")
            gate.get_by_label("答案 1", exact=True).fill("source-answer-test")
            gate.get_by_role("button", name="创建并解锁", exact=True).click()
            page.get_by_role("button", name="新增条目", exact=True).click()
            editor = page.get_by_role("dialog", name="新增保险箱条目", exact=True)
            editor.get_by_label("名称或备注", exact=True).fill(sample)
            editor.get_by_label("密码", exact=True).fill("secret-only-in-ciphertext")
            editor.get_by_role("button", name="保存", exact=True).click()
            expect(page.get_by_role("heading", name=sample, exact=True)).to_be_visible()
            settings = _backup_settings(page)

            settings.get_by_label("自动备份间隔", exact=True).select_option("6")
            expect(settings.get_by_label("自动备份间隔", exact=True)).to_have_value("6")
            settings.get_by_label("备份保留数量", exact=True).select_option("5")
            expect(settings.get_by_label("备份保留数量", exact=True)).to_have_value("5")
            settings.get_by_role("button", name="设置备份密码", exact=True).click()
            dialog = page.get_by_role("dialog", name="设置自动备份密码", exact=True)
            _fill_backup_form(dialog)
            dialog.get_by_role("button", name="保存密码", exact=True).click()
            automatic_row = settings.get_by_role("listitem").filter(has_text="自动备份")
            expect(automatic_row).to_be_visible()
            automatic_row.get_by_role("button", name="保存副本", exact=True).click()
            copy = page.get_by_role("dialog", name="保存备份副本", exact=True)
            copy.get_by_label("当前密码库主密码", exact=True).fill(MASTER)
            copy.get_by_role("button", name="保存文件", exact=True).click()
            automatic = _saved_download(page, tmp_path)

            settings.get_by_role("button", name="立即备份", exact=True).click()
            dialog = page.get_by_role("dialog", name="立即备份", exact=True)
            _fill_backup_form(dialog)
            dialog.get_by_role("button", name="生成备份", exact=True).click()
            manual = _saved_download(page, tmp_path)

            panel = settings.get_by_role("region", name="密码库备份", exact=True)
            expect(panel.get_by_role("listitem")).to_have_count(2)
            for theme, width in [("light", 1320), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 900})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                interval = panel.get_by_role("combobox", name="自动备份间隔").bounding_box()
                retention = panel.get_by_role("combobox", name="备份保留数量").bounding_box()
                if width == 390:
                    assert retention["y"] > interval["y"]
                else:
                    assert retention["x"] > interval["x"] and retention["y"] == interval["y"]
                assert panel.evaluate("element => element.scrollWidth <= element.clientWidth")
                expect(panel.get_by_text(manual.name, exact=True)).to_have_attribute("title", manual.name)
                panel.screenshot(animations="disabled", path=str(tmp_path / f"password-backups-{theme}-{width}.png"))
            page.set_viewport_size({"width": 1320, "height": 900})

            for selected in (automatic, manual):
                data = json.loads(selected.read_text(encoding="utf-8"))
                assert data["format"] == "dba-vault-backup-v2"
                assert set(data) == {"format", "source_user_id", "salt", "nonce", "wrapped_keys", "items", "mac"}
                assert sample not in selected.read_text(encoding="utf-8")
                row = settings.get_by_role("listitem").filter(has_text=selected.name)
                row.get_by_role("button", name="恢复", exact=True).click()
                verify = page.get_by_role("dialog", name="校验密码库备份", exact=True)
                verify.get_by_label("备份密码", exact=True).fill(BACKUP_PASSWORD)
                verify.get_by_label("当前密码库主密码", exact=True).fill(MASTER)
                verify.get_by_role("button", name="校验备份", exact=True).click()
                review = page.get_by_role("dialog", name="确认恢复密码库", exact=True)
                expect(review).to_contain_text("当前的 1 条凭据")
                review.get_by_role("button", name="确认恢复", exact=True).click()
                expect(settings.get_by_text("已恢复 1 条。覆盖前的安全备份已保存。", exact=True)).to_be_visible()

            # Compare with backups made before v2. These are accepted for the source account.
            settings.get_by_role("button", name="完成", exact=True).click()
            unlock_and_check(page, MASTER)
            from test_vault import desktop_unlock
            import httpx
            with httpx.Client(base_url=live_server) as client:
                client.post("/api/auth/desktop", headers={"X-DBA-Desktop-Token": "isolated-portable-vault"}).raise_for_status()
                session = client.get("/api/auth/status").json()
                client.headers["X-CSRF-Token"] = session["csrf_token"]
                grant = desktop_unlock(client, MASTER).json()["token"]
                v1 = client.get("/api/vault/backup", headers={"X-DBA-Vault-Token": grant}).json()
            legacy = tmp_path / "legacy-v1.json"
            legacy.write_text(json.dumps(v1), encoding="utf-8")
            settings = _backup_settings(page)
            settings.get_by_label("选择密码库备份文件", exact=True).set_input_files(str(legacy))
            verify = page.get_by_role("dialog", name="校验密码库备份", exact=True)
            verify.get_by_label("备份密码", exact=True).fill(MASTER)
            verify.get_by_label("当前密码库主密码", exact=True).fill(MASTER)
            verify.get_by_role("button", name="校验备份", exact=True).click()
            page.get_by_role("dialog", name="确认恢复密码库", exact=True).get_by_role("button", name="确认恢复").click()
            expect(settings.get_by_text("已恢复 1 条。覆盖前的安全备份已保存。", exact=True)).to_be_visible()
            context.close()

            with sqlite3.connect(source_db) as conn:
                source_recovery = conn.execute("SELECT recovery_key_id FROM vault_profiles").fetchone()[0]
            for user_id, selected in enumerate((automatic, manual), 30):
                separate = tmp_path / f"new-workbench-{user_id}" / "workspace.db"
                monkeypatch.setattr(database, "DB_PATH", str(separate))
                database.run_startup_migrations()
                with sqlite3.connect(separate) as conn:
                    conn.execute("INSERT INTO users(id, username, password_hash) VALUES (?, ?, ?)", (user_id, OWNER["username"], auth.hash_password(OWNER["password"])))
                    conn.execute("INSERT INTO memberships(user_id, role_id) SELECT ?, id FROM roles WHERE name='owner'", (user_id,))

                context, page = desktop_page(browser)
                settings = _backup_settings(page)
                settings.get_by_label("选择密码库备份文件", exact=True).set_input_files(str(selected))
                verify = page.get_by_role("dialog", name="校验密码库备份", exact=True)
                verify.get_by_label("备份密码", exact=True).fill(BACKUP_PASSWORD)
                target_master = f"target-master-test-{user_id}"
                verify.get_by_label("设置本机密码库主密码", exact=True).fill(target_master)
                verify.get_by_label("确认本机主密码", exact=True).fill(target_master)
                verify.get_by_label("问题 1", exact=True).fill("目标密保")
                verify.get_by_label("答案 1", exact=True).fill("target-answer-test")
                verify.get_by_role("button", name="校验备份", exact=True).click()
                review = page.get_by_role("dialog", name="确认恢复密码库", exact=True)
                expect(review).to_contain_text("包含 1 条凭据")
                with sqlite3.connect(separate) as conn:
                    assert conn.execute("SELECT COUNT(*) FROM vault_profiles").fetchone()[0] == 0
                review.get_by_role("button", name="确认恢复", exact=True).click()
                expect(settings.get_by_text("已恢复 1 条。", exact=True)).to_be_visible()
                settings.get_by_role("button", name="完成", exact=True).click()
                unlock_and_check(page, target_master)
                with sqlite3.connect(separate) as conn:
                    new_recovery = conn.execute("SELECT recovery_key_id FROM vault_profiles WHERE user_id=?", (user_id,)).fetchone()[0]
                    assert new_recovery != source_recovery
                    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
                context.close()
        finally:
            browser.close()
            monkeypatch.setattr(database, "DB_PATH", source_db)
