import hashlib
import json
import os
import time
import urllib.parse
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login


def _search_articles(page, title):
    # A matching row can already be visible before the debounced search starts.
    # Wait for its new response so a placeholder refresh cannot disable it mid-click.
    with page.expect_response(lambda response: response.request.method == "GET"
                              and urllib.parse.urlsplit(response.url).path == "/api/articles/"
                              and urllib.parse.parse_qs(urllib.parse.urlsplit(response.url).query).get("keyword") == [title]):
        page.get_by_placeholder("按标题搜索知识库").fill(title)
    expect(page.locator(".data-panel")).to_have_attribute("aria-busy", "false")


@pytest.mark.browser
def test_markdown_images_and_tables_render_in_production_build(live_server, tmp_path, monkeypatch):
    from backend import local_capabilities
    from backend.config import Settings

    images = tmp_path / "img"
    images.mkdir()
    Image.new("RGB", (320, 180), "#4f6bed").save(images / "中文 图片.png")
    Image.new("RGB", (320, 180), "#f59e0b").save(images / "中文 图片.jfif", format="JPEG")
    sample = tmp_path / "图片与表格.md"
    sample.write_text("""[TOC]

# Markdown 原文件验收

![安装截图](img/中文%20图片.png)

![未编码空格路径](img/中文 图片.png)

![JPEG 截图](img/中文%20图片.jfif)

| 数据库 | 版本 | 用途 |
| :--- | ---: | --- |
| Oracle | 11g | 安装验证 |

<img src="img/中文 图片.png" width="180" onerror="window.hacked=1">
<table><tr><th>HTML 表格</th></tr><tr><td>保留原始表格</td></tr></table>
<script>window.hacked=1</script>
""", encoding="utf-8")
    cases = [("fixture", sample)]
    if os.environ.get("DBA_TEST_MARKDOWN_FILE"):
        cases.append(("real", Path(os.environ["DBA_TEST_MARKDOWN_FILE"])))
    if os.environ.get("DBA_TEST_MARKDOWN_TABLE_FILE"):
        cases.append(("real-table", Path(os.environ["DBA_TEST_MARKDOWN_TABLE_FILE"])))
    monkeypatch.setattr(local_capabilities, "_enrolled_roots", set())
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true", "DBA_ALLOWED_ROOTS": os.pathsep.join({str(path.parent) for _, path in cases}),
        "DBA_ALLOWED_LOCAL_ACTIONS": "open,edit,folder",
    }))
    hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for _, path in cases}
    client, csrf = _api_client(live_server)
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1680, "height": 1050})
            _login(page, live_server)
            for case, path in cases:
                title = f"Markdown原文件验收-{case}"
                client.post("/api/articles/", json={"title": title, "file_path": str(path)}, headers={"X-CSRF-Token": csrf}).raise_for_status()
                page.get_by_role("navigation", name="主导航").get_by_role("link", name="知识库", exact=True).click()
                _search_articles(page, title)
                trigger = page.get_by_role("button", name=f"预览：{title}", exact=True)
                trigger.click()
                expect(trigger).to_have_attribute("aria-pressed", "true")
                preview = page.get_by_role("region", name=f"原文件预览：{path.name}", exact=True)
                expect(preview).to_be_visible()
                assert not preview.locator("p").evaluate_all("items => items.some(item => /^\\[toc\\]$/i.test(item.textContent.trim()))")
                if case == "fixture":
                    expect(preview.get_by_role("table")).to_have_count(2)
                    expect(preview.get_by_role("cell", name="Oracle", exact=True)).to_be_visible()
                    assert preview.locator("td[align=right]").evaluate("element => getComputedStyle(element).textAlign") == "right"
                elif case == "real-table":
                    assert preview.get_by_role("table").count() > 0
                    if os.environ.get("DBA_TEST_MARKDOWN_EXPECTED_TABLE"):
                        expected_table = json.loads(os.environ["DBA_TEST_MARKDOWN_EXPECTED_TABLE"])
                        actual_table = preview.get_by_role("table").first.locator("tr").evaluate_all("rows => rows.map(row => [...row.cells].map(cell => cell.textContent.trim()))")
                        assert actual_table == expected_table
                if case != "real-table":
                    expect(preview.locator("img").first).to_be_visible()
                    if case == "real" and os.environ.get("DBA_TEST_MARKDOWN_IMAGE_COUNT"):
                        expect(preview.locator("img")).to_have_count(int(os.environ["DBA_TEST_MARKDOWN_IMAGE_COUNT"]))
                    deadline = time.monotonic() + 60
                    while time.monotonic() < deadline:
                        if preview.locator("img").evaluate_all("images => images.length > 0 && images.every(image => image.complete && image.naturalWidth > 0)"):
                            break
                        page.wait_for_timeout(200)
                    assert preview.locator("img").evaluate_all("images => images.every(image => image.complete && image.naturalWidth > 0)"), preview.locator("img").evaluate_all("images => images.filter(image => !image.naturalWidth).map(image => image.src)")
                assert page.evaluate("window.hacked === undefined")
                expect(preview.locator("script, [onerror]")).to_have_count(0)
                for theme, width in [("light", 1680), ("dark", 390)]:
                    page.set_viewport_size({"width": width, "height": 1050})
                    page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                    expect(preview).to_be_visible()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    assert preview.evaluate("element => element.scrollWidth <= element.clientWidth + 1")
                    page.screenshot(path=str(tmp_path / f"markdown-{case}-{theme}-{width}.png"), full_page=True)
                page.get_by_role("button", name="关闭预览", exact=True).click()
                page.set_viewport_size({"width": 1680, "height": 1050})
                page.evaluate("document.documentElement.dataset.theme = 'light'")
            for path, original_hash in hashes.items():
                assert hashlib.sha256(path.read_bytes()).hexdigest() == original_hash
        finally:
            browser.close()
            client.close()


@pytest.mark.browser
def test_audited_typora_documents_render_available_images_and_consume_toc(live_server, tmp_path, monkeypatch):
    audit_path = os.environ.get("DBA_TEST_MARKDOWN_AUDIT")
    if not audit_path:
        pytest.skip("Set DBA_TEST_MARKDOWN_AUDIT to a read-only source-document audit")
    audit_all = os.environ.get("DBA_TEST_MARKDOWN_ALL_IMAGES") == "1"
    cases = [entry for entry in json.loads(Path(audit_path).read_text(encoding="utf-8"))["files"] if entry["toc"] or entry.get("spaceImages") or (audit_all and entry["images"])]
    assert cases
    from backend import local_capabilities
    from backend.config import Settings
    monkeypatch.setattr(local_capabilities, "_enrolled_roots", set())
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true",
        "DBA_ALLOWED_ROOTS": os.pathsep.join({str(Path(entry["file"]).parent) for entry in cases}),
        "DBA_ALLOWED_LOCAL_ACTIONS": "open,edit,folder",
    }))
    client, csrf = _api_client(live_server)
    results = []
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1680, "height": 1050})
            # Local-document validation must not contact third-party image hosts.
            page.route("https://**/*", lambda route: route.abort())
            page.route("http://**/*", lambda route: route.continue_() if urllib.parse.urlsplit(route.request.url).hostname in {"127.0.0.1", "localhost"} else route.abort())
            _login(page, live_server)
            for index, entry in enumerate(cases):
                source = Path(entry["file"])
                assert hashlib.sha256(source.read_bytes()).hexdigest() == entry["sha256"]
                title = f"Typora同类验收-{index}"
                client.post("/api/articles/", json={"title": title, "file_path": str(source)}, headers={"X-CSRF-Token": csrf}).raise_for_status()
                page.get_by_role("navigation", name="主导航").get_by_role("link", name="知识库", exact=True).click()
                _search_articles(page, title)
                trigger = page.get_by_role("button", name=f"预览：{title}", exact=True)
                trigger.click()
                expect(trigger).to_have_attribute("aria-pressed", "true")
                preview = page.get_by_role("region", name=f"原文件预览：{source.name}", exact=True)
                expect(preview).to_be_visible()
                assert not preview.locator("p").evaluate_all("items => items.some(item => /^\\[toc\\]$/i.test(item.textContent.trim()))")
                expect(preview.locator("img")).to_have_count(len(entry["images"]))
                available = [item for item in entry["images"] if item["status"] in {"supported", "unsupported-extension"}]
                missing = [item for item in entry["images"] if item["status"] in {"missing", "missing-absolute"}]
                external = [item for item in entry["images"] if item["status"] == "external"]
                assert len(available) + len(missing) + len(external) == len(entry["images"])
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if preview.locator("img").evaluate_all("images => images.every(image => image.complete)"):
                        break
                    page.wait_for_timeout(100)
                loaded = preview.locator("img").evaluate_all("images => images.filter(image => image.complete && image.naturalWidth > 0).map(image => image.getAttribute('src'))")
                assert len(loaded) == len(available), {"file": str(source), "loaded": loaded, "expected": available}
                loaded_references = {urllib.parse.unquote(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["path"][0]) for url in loaded}
                for item in available:
                    assert urllib.parse.unquote(item["reference"]) in loaded_references
                results.append({"file": str(source), "loaded_images": len(loaded), "missing_source_images": len(missing), "external_images_not_requested": len(external), "toc_marker_visible": False})
                if entry.get("spaceImages") or entry["toc"]:
                    page.screenshot(path=str(tmp_path / f"typora-audit-{index}.png"), full_page=True)
                page.get_by_role("button", name="关闭预览", exact=True).click()
                assert hashlib.sha256(source.read_bytes()).hexdigest() == entry["sha256"]
            (tmp_path / "browser-audit-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            browser.close()
            client.close()
