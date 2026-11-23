"""Exercise vault disclosures and restore only against an isolated synthetic vault."""
import json
import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import OWNER, _api_client, _edge, _login


MASTER = "test-only-ui-master"


def _backup_settings(page):
    page.locator(".sidebar-foot").get_by_role("button", name="设置", exact=True).click()
    settings = page.get_by_role("dialog", name="设置", exact=True)
    settings.get_by_role("button", name="密码库安全", exact=True).click()
    expect(settings.get_by_role("heading", name="密码库备份", exact=True)).to_be_visible()
    return settings


def _verify_import(page, settings, password):
    settings.get_by_role("button", name="导入", exact=True).click()
    dialog = page.get_by_role("dialog", name="导入密码库备份", exact=True)
    expect(dialog.get_by_label("选择备份文件")).to_have_count(0)
    dialog.get_by_label("当前密码库主密码", exact=True).fill(password)
    dialog.get_by_role("button", name="验证", exact=True).click()
    expect(dialog.get_by_role("button", name="浏览备份文件", exact=True)).to_be_visible()
    expected = _backup_directory(settings).inner_text()
    expect(dialog.get_by_label("备份文件", exact=True)).to_have_value(expected)
    expect(dialog.get_by_label("备份恢复密钥", exact=True)).to_have_value(_key_directory(settings).inner_text())
    return dialog


def _select_age_files(dialog, backup, identity):
    dialog.get_by_label("选择备份文件", exact=True).set_input_files(str(backup))
    next_step = dialog.get_by_role("button", name="下一步", exact=True)
    expect(next_step).to_be_disabled()
    dialog.get_by_label("选择备份恢复密钥", exact=True).set_input_files(str(identity))
    expect(next_step).to_be_enabled()
    next_step.click()


def _backup_directory(settings):
    location = settings.get_by_role("group", name="备份存放目录", exact=True)
    expect(location.get_by_role("textbox")).to_have_count(0)
    return location.locator(".vault-backup-directory")


def _key_directory(settings):
    locations = settings.locator(".vault-backup-location")
    location = locations.get_by_role("group", name="密钥存放目录", exact=True)
    expect(location.get_by_role("textbox")).to_have_count(0)
    expect(location.get_by_role("button", name="打开密钥目录", exact=True)).to_be_visible()
    expect(settings.get_by_role("button", name="另存恢复密钥", exact=True)).to_have_count(0)
    return location.locator(".vault-backup-directory")


def _create_manual_backup(page, settings):
    settings.get_by_role("button", name="手动备份", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="备份创建成功")).to_be_visible()
    expect(page.get_by_role("dialog", name="手动备份", exact=True)).to_have_count(0)
    expect(settings.get_by_role("listitem").filter(has_text="手动备份")).to_be_visible()


@pytest.mark.browser
def test_vault_daily_ui_csv_and_restore_confirmation(live_server, tmp_path):
    client, _ = _api_client(live_server)
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        try:
            page = context.new_page()
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
            page.evaluate("document.documentElement.dataset.theme = 'light'")
            _create_manual_backup(page, settings)
            toast = page.locator(".vault-backup-toast")
            bounds = toast.bounding_box()
            assert abs((bounds["x"] + bounds["width"] / 2) - page.viewport_size["width"] / 2) < 2
            assert abs(page.viewport_size["height"] - bounds["y"] - bounds["height"] - 16) < 2
            toast.screenshot(path=str(tmp_path / "vault-backup-success.png"))
            expect(toast).not_to_be_visible(timeout=4000)
            page.evaluate("document.documentElement.dataset.theme = 'dark'")
            directory = Path(_backup_directory(settings).inner_text())
            identity, = Path(_key_directory(settings).inner_text()).glob("*.key")
            backup = next(directory.rglob("backup-*.age"))
            assert backup.read_text(encoding="utf-8").startswith("-----BEGIN AGE ENCRYPTED FILE-----")
            assert "synthetic-secret" not in backup.read_text(encoding="utf-8")

            restore_requests = []
            page.on("request", lambda request: restore_requests.append(request) if "/api/vault/backup/restore" in request.url else None)
            restore = _verify_import(page, settings, MASTER)
            footer = restore.locator(".modal-actions").bounding_box()
            next_button = restore.get_by_role("button", name="下一步", exact=True).bounding_box()
            assert abs((footer["x"] + footer["width"] / 2) - (next_button["x"] + next_button["width"] / 2)) < 2
            page.screenshot(animations="disabled", path=str(tmp_path / "vault-import-file-selection.png"))
            wrong = tmp_path / "wrong-identity.txt"
            from pyrage import x25519
            wrong.write_text(str(x25519.Identity.generate()), encoding="utf-8")
            _select_age_files(restore, backup, wrong)
            expect(restore.get_by_role("alert")).to_contain_text("恢复密钥与备份不匹配")
            restore.get_by_label("选择备份恢复密钥", exact=True).set_input_files(str(identity))
            restore.get_by_role("button", name="下一步", exact=True).click()
            expect(restore).to_contain_text("包含 1 条凭据")
            expect(restore).to_contain_text("覆盖前会自动创建安全备份")
            expect(restore.get_by_role("list", name="将导入的密码条目")).to_contain_text("导入演示条目")
            expect(restore).not_to_contain_text("synthetic-secret")
            assert not restore_requests
            for theme, width in [("light", 1440), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(animations="disabled", path=str(tmp_path / f"vault-restore-{theme}-{width}.png"))
            expect(restore.get_by_role("button", name="取消", exact=True)).to_have_count(0)
            restore.get_by_role("button", name="关闭备份对话框", exact=True).click()
            assert not restore_requests

            row = settings.get_by_role("listitem").filter(has_text=backup.name)
            row.get_by_role("button", name="重命名备份", exact=True).click()
            rename = page.get_by_role("dialog", name="重命名备份", exact=True)
            rename.get_by_label("备份名称", exact=True).fill("恢复测试快照")
            rename.get_by_role("button", name="保存", exact=True).click()
            row = settings.get_by_role("listitem").filter(has_text="恢复测试快照")
            row.get_by_role("button", name="恢复", exact=True).click()
            verify = page.get_by_role("dialog", name="校验密码库备份", exact=True)
            verify.get_by_label("当前密码库主密码", exact=True).fill(MASTER)
            verify.get_by_role("button", name="验证", exact=True).click()
            page.get_by_role("dialog", name="确认恢复密码库", exact=True).get_by_role("button", name="确认恢复", exact=True).click()
            expect(settings.get_by_text("已恢复 1 条。覆盖前的安全备份已保存。", exact=True)).to_be_visible()
            expect(settings.get_by_role("listitem").filter(has_text="恢复前安全备份")).to_be_visible()
            row.get_by_role("button", name="删除备份", exact=True).click()
            delete = page.get_by_role("dialog", name="删除备份", exact=True)
            expect(delete).to_have_accessible_description("此备份将被永久删除，此操作无法撤消。")
            expect(delete.locator(".consequence-warning")).to_have_count(0)
            filename = delete.locator(".backup-file strong")
            expect(filename).to_have_text("恢复测试快照")
            expect(filename).to_have_css("text-align", "center")
            for theme, width in [("light", 1440), ("dark", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                assert delete.evaluate("dialog => dialog.scrollWidth <= dialog.clientWidth")
                page.screenshot(animations="disabled", path=str(tmp_path / f"vault-delete-{theme}-{width}.png"))
            assert backup.is_file()
            delete.get_by_role("button", name="确认删除", exact=True).click()
            expect(row).not_to_be_visible()
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
    from backend.routers import vault as vault_router

    source_db = database.DB_PATH
    monkeypatch.setattr(auth, "_desktop_token", "isolated-portable-vault")
    sample = "隔离密码库条目"

    def desktop_page(browser):
        context = browser.new_context(viewport={"width": 1320, "height": 900}, reduced_motion="no-preference")
        page = context.new_page()
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
            vault_router.run_scheduled_backups()
            settings.get_by_role("button", name="完成", exact=True).click()
            settings = _backup_settings(page)
            directory = Path(_backup_directory(settings).inner_text())
            identity, = Path(_key_directory(settings).inner_text()).glob("*.key")
            automatic = next(directory.rglob("auto-*.age"))

            _create_manual_backup(page, settings)
            expect(settings.get_by_role("listitem").filter(has_text="自动备份")).to_be_visible()
            manual = next(directory.rglob("backup-*.age"))

            panel = settings.get_by_role("region", name="备份与恢复", exact=True)
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
                assert selected.read_text(encoding="utf-8").startswith("-----BEGIN AGE ENCRYPTED FILE-----")
                assert sample not in selected.read_text(encoding="utf-8")
                row = settings.get_by_role("listitem").filter(has_text=selected.name)
                row.get_by_role("button", name="恢复", exact=True).click()
                verify = page.get_by_role("dialog", name="校验密码库备份", exact=True)
                steps = verify.get_by_role("list", name="恢复步骤")
                expect(steps.get_by_role("listitem")).to_have_count(2)
                expect(steps.locator('[aria-current="step"]')).to_have_text("1验证主密码")
                verify.get_by_label("当前密码库主密码", exact=True).fill(MASTER)
                button = verify.get_by_role("button", name="验证", exact=True)
                expect(button.locator(".task-morph-label svg")).to_have_count(0)
                button.click()
                expect(button).to_have_attribute("data-phase", "pending")
                expect(button).to_have_attribute("data-phase", "success")
                review = page.get_by_role("dialog", name="确认恢复密码库", exact=True)
                steps = review.get_by_role("list", name="恢复步骤")
                expect(steps.locator('[data-state="done"]')).to_have_text("验证主密码")
                expect(steps.locator('[aria-current="step"]')).to_have_text("2确认恢复")
                expect(review).to_contain_text("当前的 1 条凭据")
                review.get_by_role("button", name="确认恢复", exact=True).click()
                progress = review.get_by_role("status", name="正在恢复")
                expect(progress.get_by_text(re.compile(r"^[1-9]\d?%$"))).to_be_visible()
                expect(review.get_by_role("status", name="恢复完成")).to_be_visible()
                expect(review).not_to_be_visible()
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
            legacy_dialog = _verify_import(page, settings, MASTER)
            legacy_dialog.get_by_label("选择备份文件", exact=True).set_input_files(str(legacy))
            legacy_dialog.get_by_label("旧版备份密码", exact=True).fill(MASTER)
            legacy_dialog.get_by_role("button", name="下一步", exact=True).click()
            legacy_dialog.get_by_role("button", name="导入", exact=True).click()
            expect(legacy_dialog).not_to_be_visible()
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
                target_master = f"target-master-test-{user_id}"
                settings.get_by_role("button", name="导入", exact=True).click()
                setup_notice = page.get_by_role("dialog", name="导入密码库备份", exact=True)
                setup_notice.get_by_role("button", name="前往保险箱", exact=True).click()
                setup = page.get_by_role("region", name="创建本地保险箱")
                setup.get_by_label("保险箱主密码", exact=True).fill(target_master)
                setup.get_by_label("确认主密码", exact=True).fill(target_master)
                setup.get_by_label("问题 1", exact=True).fill("目标密保")
                setup.get_by_label("答案 1", exact=True).fill("target-answer-test")
                setup.get_by_role("button", name="创建并解锁", exact=True).click()
                expect(page.get_by_role("button", name="立即锁定", exact=True)).to_be_visible()
                settings = _backup_settings(page)
                review = _verify_import(page, settings, target_master)
                _select_age_files(review, selected, identity)
                expect(review).to_contain_text("包含 1 条凭据")
                expect(review.get_by_role("list", name="将导入的密码条目")).to_contain_text(sample)
                with sqlite3.connect(separate) as conn:
                    assert conn.execute("SELECT COUNT(*) FROM vault_items").fetchone()[0] == 0
                review.evaluate("""dialog => {
                    new MutationObserver(() => {
                        if (dialog.querySelector('.vault-import-progress[data-complete]')) {
                            document.body.dataset.importMotionFinished = 'true';
                        }
                    }).observe(dialog, { subtree: true, childList: true, attributes: true });
                }""")
                review.get_by_role("button", name="导入", exact=True).click()
                expect(review.get_by_role("status", name="正在导入")).to_be_visible()
                expect(review).not_to_be_visible()
                expect(page.locator("body")).to_have_attribute("data-import-motion-finished", "true")
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
