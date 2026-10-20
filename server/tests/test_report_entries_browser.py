"""Browser regressions for restored cross-module search and local scan import."""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect, sync_playwright

from backend.config import Settings
from test_browser_smoke import _api_client, _edge, _login


@pytest.mark.browser
def test_global_search_opens_exact_record_in_each_module(live_server):
    records = [
        ("scripts", "title", "名称"),
        ("articles", "title", "标题"),
        ("resources", "name", "名称"),
        ("customers", "name", "客户"),
    ]
    client, csrf = _api_client(live_server)
    ids = {}
    try:
        for module, field, _ in records:
            created = client.post(f"/api/{module}/", json={field: f"跨模块定位-{module}"}, headers={"X-CSRF-Token": csrf})
            created.raise_for_status()
            ids[module] = created.json()["id"]
        with sync_playwright() as playwright:
            browser = _edge(playwright)
            try:
                page = browser.new_page()
                page.set_default_timeout(10_000)
                _login(page, live_server)
                for module, _, label in records:
                    page.keyboard.press("Control+k")
                    search = page.get_by_role("combobox", name="跨模块搜索关键词")
                    expect(search).to_be_focused()
                    search.fill("跨模块定位")
                    results = page.get_by_role("listbox", name="全局搜索结果")
                    results.get_by_role("option", name=re.compile(f"跨模块定位-{module}")).click()
                    page.wait_for_url(f"**/{module}?record={ids[module]}")
                    editor = page.get_by_role("dialog")
                    expect(editor.get_by_label(label, exact=True)).to_have_value(f"跨模块定位-{module}")
                    editor.get_by_role("button", name="关闭", exact=True).click()
                    page.wait_for_url(f"**/{module}")
                page.keyboard.press("Control+k")
                search = page.get_by_role("combobox", name="跨模块搜索关键词")
                search.press("Escape")
                expect(page.get_by_role("listbox", name="全局搜索结果")).not_to_be_visible()
                expect(search).not_to_be_focused()
            finally:
                browser.close()
    finally:
        client.close()


@pytest.mark.browser
def test_scan_disabled_by_default_reports_permission_error_without_writes(live_server, monkeypatch, tmp_path):
    from backend import local_capabilities

    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({}))
    source = tmp_path / "default-closed"
    source.mkdir()
    (source / "must-not-import.sql").write_text("SELECT 1;", encoding="utf-8")
    client, _ = _api_client(live_server)
    try:
        with sync_playwright() as playwright:
            browser = _edge(playwright)
            try:
                page = browser.new_page()
                page.set_default_timeout(10_000)
                _login(page, live_server)
                page.get_by_role("navigation", name="主导航").get_by_role("link", name="脚本库").click()
                page.get_by_role("button", name="目录批量导入").click()
                dialog = page.get_by_role("dialog", name="批量导入脚本", exact=True)
                dialog.get_by_role("textbox", name="扫描目录").fill(str(source))
                with page.expect_response(lambda response: "/api/scan/run" in response.url) as scanned:
                    dialog.get_by_role("button", name="扫描预览").click()
                assert scanned.value.status == 403
                expect(dialog.get_by_role("alert")).to_contain_text("不会自动扩大权限")
                expect(dialog.get_by_role("button", name="导入所选（0）")).to_be_disabled()
                assert client.get("/api/scripts/").json()["total"] == 0
                assert (source / "must-not-import.sql").read_text(encoding="utf-8") == "SELECT 1;"
            finally:
                browser.close()
    finally:
        client.close()


@pytest.mark.browser
@pytest.mark.parametrize("module,nav,kind,extension", [
    ("scripts", "脚本库", "脚本", ".sql"),
    ("articles", "知识库", "文档", ".md"),
    ("resources", "资源中心", "资源", ".zip"),
])
def test_allowed_directory_preview_imports_only_checked_current_module_files(
    live_server, monkeypatch, tmp_path, module, nav, kind, extension,
):
    from backend import local_capabilities

    source = tmp_path / "allowed" / "MySQL"
    source.mkdir(parents=True)
    included = source / f"selected-{module}{extension}"
    excluded = source / f"unchecked-{module}{extension}"
    unrelated = source / ("other-module.md" if module != "articles" else "other-module.sql")
    for path in (included, excluded, unrelated):
        path.write_text("test-only-index-content", encoding="utf-8")
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true",
        "DBA_ALLOWED_ROOTS": str(source),
        "DBA_ALLOWED_LOCAL_ACTIONS": "scan",
    }))
    client, _ = _api_client(live_server)
    try:
        with sync_playwright() as playwright:
            browser = _edge(playwright)
            try:
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.set_default_timeout(10_000)
                _login(page, live_server)
                page.get_by_role("navigation", name="主导航").get_by_role("link", name=nav).click()
                page.get_by_role("button", name="目录批量导入").click()
                dialog = page.get_by_role("dialog", name=f"批量导入{kind}", exact=True)
                dialog.get_by_role("textbox", name="扫描目录").fill(str(source))
                dialog.get_by_role("button", name="扫描预览").click()
                selected = dialog.get_by_role("checkbox", name=f"导入：{included.stem}", exact=True)
                expect(selected).to_be_checked()
                expect(dialog.get_by_role("checkbox", name=re.compile("^导入："))).to_have_count(2)
                expect(dialog.get_by_text(unrelated.stem, exact=True)).to_have_count(0)
                assert client.get(f"/api/{module}/").json()["total"] == 0
                dialog.get_by_role("checkbox", name=f"导入：{excluded.stem}", exact=True).uncheck()
                with page.expect_response(lambda response: "/api/scan/commit" in response.url) as committed:
                    dialog.get_by_role("button", name="导入所选（1）", exact=True).click()
                assert committed.value.status == 200
                expect(dialog.get_by_role("status")).to_have_text("已导入 1 条，跳过重复 0 条。")
                dialog.get_by_role("button", name="关闭", exact=True).click()
                expect(page.locator("tbody")).to_contain_text(included.stem)
                assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
                stored = client.get(f"/api/{module}/").json()
                assert stored["total"] == 1
                assert stored["items"][0]["path" if module == "resources" else "file_path"] == str(included.resolve())
                for other in {"scripts", "articles", "resources"} - {module}:
                    assert client.get(f"/api/{other}/").json()["total"] == 0
                for path in (included, excluded, unrelated):
                    assert path.read_text(encoding="utf-8") == "test-only-index-content"
            finally:
                browser.close()
    finally:
        client.close()
