import os
import json
import secrets
import socket
import time
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login


@pytest.fixture
def real_viewer(tmp_path, monkeypatch):
    if not os.environ.get("DBA_TEST_PREVIEW_SAMPLES"):
        pytest.skip("Set DBA_TEST_PREVIEW_SAMPLES to run real kkFileView format acceptance")

    import main
    import file_viewer_runtime
    from backend import file_visual_preview

    sockets = [socket.socket() for _ in range(3)]
    try:
        for channel in sockets:
            channel.bind(("127.0.0.1", 0))
        ports = [channel.getsockname()[1] for channel in sockets]
    finally:
        for channel in sockets:
            channel.close()
    origin = f"http://127.0.0.1:{ports[0]}"
    key = secrets.token_urlsafe(32)
    monkeypatch.setattr(file_viewer_runtime, "VIEWER_PORT", ports[0])
    monkeypatch.setattr(file_viewer_runtime, "VIEWER_ORIGIN", origin)
    monkeypatch.setattr(file_visual_preview, "VIEWER_ORIGIN", origin)
    monkeypatch.setattr(file_visual_preview, "VIEWER_KEY", key)
    monkeypatch.setattr(main, "VIEWER_ORIGIN", origin)
    monkeypatch.setenv("DBA_FILE_VIEWER_KEY", key)
    viewer_data = Path(os.environ["DBA_TEST_PREVIEW_SAMPLES"]).resolve().parent / ".viewer-browser"
    monkeypatch.setenv("DBA_FILE_VIEWER_DATA_DIR", str(viewer_data))
    popen = file_viewer_runtime.subprocess.Popen
    with monkeypatch.context() as startup:
        startup.setattr(file_viewer_runtime.subprocess, "Popen", lambda command, **kwargs: popen(command + [f"--office.plugin.server.ports={ports[1]},{ports[2]}"], **kwargs))
        process = file_viewer_runtime.start_file_viewer(tmp_path / "data", tmp_path / "viewer-logs")
    assert process is not None, "Install the real viewer runtime or configure DBA_FILE_VIEWER_HOME"
    try:
        deadline = time.monotonic() + 40
        while not file_visual_preview._viewer_available() and time.monotonic() < deadline:
            assert process.poll() is None, "kkFileView exited; inspect viewer-logs/file-viewer.log"
            time.sleep(0.25)
        yield
    finally:
        file_viewer_runtime.stop_file_viewer(process)


@pytest.mark.browser
def test_original_file_rendering_through_real_viewer(live_server, real_viewer, tmp_path, monkeypatch):
    samples_value = os.environ["DBA_TEST_PREVIEW_SAMPLES"]

    from backend import file_visual_preview, local_capabilities
    from backend.config import Settings

    samples = Path(samples_value).resolve()
    cases = [(suffix, samples / f"sample.{suffix}") for suffix in ("pdf", "docx", "pptx", "txt", "md", "sql")]
    real_cases = os.environ.get("DBA_TEST_PREVIEW_CASES", "")
    if real_cases:
        cases.extend((f"real-{item['extension']}", Path(item["path"])) for item in json.loads(Path(real_cases).read_text(encoding="utf-8")))
    allowed_roots = os.pathsep.join({str(sample.parent) for _, sample in cases})
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true",
        "DBA_ALLOWED_ROOTS": allowed_roots,
        "DBA_ALLOWED_LOCAL_ACTIONS": "open,edit,folder",
    }))
    monkeypatch.setattr(file_visual_preview, "settings", replace(file_visual_preview.settings, port=urlsplit(live_server).port))
    assert file_visual_preview._viewer_available(), "Real kkFileView health check must succeed"
    client, csrf = _api_client(live_server)
    with sync_playwright() as playwright:
        browser = _edge(playwright)
        try:
            page = browser.new_page(viewport={"width": 1680, "height": 1050})
            page.set_default_timeout(60_000)
            _login(page, live_server)
            for case, sample in cases:
                module = "scripts" if sample.suffix.lower() == ".sql" else "articles"
                label = "脚本库" if module == "scripts" else "知识库"
                title = f"真实格式验收-{case}"
                assert sample.is_file()
                payload = {"title": title, "file_path": str(sample)}
                if module == "articles":
                    payload.update({"content": "不再展示的文章正文", "summary": f"来自 {sample.name}"})
                created = client.post(f"/api/{module}/", json=payload, headers={"X-CSRF-Token": csrf})
                created.raise_for_status()
                page.get_by_role("navigation", name="主导航").get_by_role("link", name=label, exact=True).click()
                page.get_by_placeholder(f"按标题搜索{label}").fill(title)
                page.get_by_role("button", name=f"预览：{title}", exact=True).click()
                is_markdown = sample.suffix.lower() in {".md", ".markdown"}
                frame = page.frame_locator(".library-visual-frame")
                expect(page.locator(".library-record.selected .library-record-path")).to_have_text(str(sample))
                if module == "articles":
                    expect(page.locator(".library-preview").get_by_role("region", name="正文预览", exact=True)).to_have_count(0)
                    expect(page.locator(".library-preview-summary")).to_have_count(0)
                if not is_markdown:
                    expect(frame.locator("body")).not_to_contain_text("非法访问", timeout=60_000)
                deadline = time.monotonic() + 60
                rendered = False
                while time.monotonic() < deadline:
                    if is_markdown and "DBA Workbench" in page.locator(".library-markdown").inner_text(timeout=5000):
                        rendered = True
                        break
                    for child in page.frames[1:]:
                        text = child.locator("body").inner_text(timeout=5000)
                        if "DBA Workbench" in text or (case == "real-sql" and "select" in text.lower()) or (case == "real-html" and len(text.strip()) > 100 and child.parent_frame != page.main_frame):
                            rendered = True
                            break
                        if child.locator(".page canvas").count() and child.locator(".page canvas").first.evaluate("canvas => canvas.width > 0 && canvas.height > 0"):
                            rendered = True
                            break
                    if rendered:
                        break
                    page.wait_for_timeout(300)
                page.screenshot(path=str(tmp_path / f"original-preview-{case}.png"), full_page=True)
                if not rendered:
                    diagnostics = [{"url": child.url, "text": child.locator("body").inner_text(timeout=5000)[:4000]} for child in page.frames[1:]]
                    (tmp_path / f"failed-preview-{case}.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
                assert rendered, f"No original content rendered for {case}"
                if case in {"pdf", "sql", "real-html"}:
                    page.set_viewport_size({"width": 390, "height": 900})
                    page.evaluate("document.documentElement.dataset.theme = 'dark'")
                    expect(page.get_by_role("dialog")).to_be_visible()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    narrow_frame = page.frame_locator(".library-visual-frame")
                    if case == "pdf":
                        expect(narrow_frame.frame_locator("iframe").locator(".page canvas").first).to_be_visible()
                    elif case == "real-html":
                        expect(narrow_frame.frame_locator("iframe").locator("main")).to_be_visible()
                    else:
                        expect(narrow_frame.locator("body")).to_contain_text("DBA Workbench")
                    page.screenshot(path=str(tmp_path / f"original-preview-{case}-dark-390.png"), full_page=True)
                    page.set_viewport_size({"width": 1680, "height": 1050})
                    page.evaluate("document.documentElement.dataset.theme = 'light'")
                page.get_by_role("button", name="关闭预览", exact=True).click()
        finally:
            browser.close()
            client.close()
