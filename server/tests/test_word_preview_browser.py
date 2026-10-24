"""Optional fidelity acceptance against a PDF exported directly by Word."""
import base64
from dataclasses import replace
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import zipfile

from PIL import Image, ImageChops
import pytest
from playwright.sync_api import expect, sync_playwright

from test_browser_smoke import _api_client, _edge, _login
from test_visual_preview_browser import real_viewer  # noqa: F401


def _pdf_pages(page):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        for frame in page.frames[1:]:
            if frame.evaluate("Boolean(window.PDFViewerApplication?.pdfDocument)"):
                return frame.evaluate("""async () => {
                    const document = window.PDFViewerApplication.pdfDocument;
                    const pages = [];
                    for (let n = 1; n <= document.numPages; n++) {
                        const page = await document.getPage(n);
                        const viewport = page.getViewport({scale: 1});
                        const canvas = window.document.createElement('canvas');
                        canvas.width = Math.ceil(viewport.width);
                        canvas.height = Math.ceil(viewport.height);
                        await page.render({canvasContext: canvas.getContext('2d'), viewport}).promise;
                        pages.push({image: canvas.toDataURL('image/png'),
                            text: (await page.getTextContent()).items.map(item => item.str).join('')});
                    }
                    return pages;
                }""")
        page.wait_for_timeout(200)
    pytest.fail("PDF.js did not load the Word preview")


@pytest.mark.browser
def test_word_pages_match_native_reference(live_server, real_viewer, tmp_path, monkeypatch):
    source_name = os.environ.get("DBA_TEST_WORD_FILE")
    reference_name = os.environ.get("DBA_TEST_WORD_REFERENCE")
    if not source_name or not reference_name or not os.environ.get("DBA_TEST_NATIVE_WORD"):
        pytest.skip("Set native Word source and reference PDF for fidelity acceptance")
    from backend import file_visual_preview, local_capabilities, word_preview
    from backend.config import Settings

    source, reference = Path(source_name), Path(reference_name)
    assert word_preview.is_available()
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    monkeypatch.setattr(local_capabilities, "_enrolled_roots", set())
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true",
        "DBA_ALLOWED_ROOTS": os.pathsep.join({str(source.parent), str(reference.parent)}),
        "DBA_ALLOWED_LOCAL_ACTIONS": "open",
    }))
    monkeypatch.setattr(file_visual_preview, "settings", replace(file_visual_preview.settings, port=urlsplit(live_server).port))
    client, csrf = _api_client(live_server)
    try:
        with sync_playwright() as playwright:
            browser = _edge(playwright)
            try:
                page = browser.new_page(viewport={"width": 1680, "height": 1050})
                page.set_default_timeout(60_000)
                _login(page, live_server)
                rendered = {}
                for label, path in (("Word原文件", source), ("Word参考PDF", reference)):
                    client.post("/api/articles/", json={"title": label, "file_path": str(path)}, headers={"X-CSRF-Token": csrf}).raise_for_status()
                    page.get_by_role("navigation", name="主导航").get_by_role("link", name="知识库", exact=True).click()
                    page.get_by_placeholder("按标题搜索知识库").fill(label)
                    with page.expect_response(lambda response: response.url.endswith("/visual-preview")) as response:
                        page.get_by_role("button", name=f"预览：{label}", exact=True).click()
                    if path == source:
                        assert response.value.json()["converter"] == "Microsoft Word"
                    rendered[label] = _pdf_pages(page)
                    if path == source:
                        expect(page.frame_locator(".library-visual-frame").frame_locator("iframe").locator(".page canvas").first).to_be_visible()
                        page.screenshot(path=str(tmp_path / "word-preview-light.png"), full_page=True)
                        page.set_viewport_size({"width": 390, "height": 900})
                        page.evaluate("document.documentElement.dataset.theme = 'dark'")
                        expect(page.get_by_role("dialog")).to_be_visible()
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                        narrow_pages = _pdf_pages(page)
                        assert len(narrow_pages) == len(rendered[label])
                        expect(page.frame_locator(".library-visual-frame").frame_locator("iframe").locator(".page canvas").first).to_be_visible()
                        page.screenshot(path=str(tmp_path / "word-preview-dark-390.png"), full_page=True)
                        page.set_viewport_size({"width": 1680, "height": 1050})
                        page.evaluate("document.documentElement.dataset.theme = 'light'")
                    page.get_by_role("button", name="关闭预览", exact=True).click()
                actual, expected = rendered["Word原文件"], rendered["Word参考PDF"]
                assert len(actual) == len(expected)
                for index, (left, right) in enumerate(zip(actual, expected)):
                    a = Image.open(BytesIO(base64.b64decode(left["image"].split(",", 1)[1]))).convert("RGB")
                    b = Image.open(BytesIO(base64.b64decode(right["image"].split(",", 1)[1]))).convert("RGB")
                    a.save(tmp_path / f"word-preview-page-{index+1}.png")
                    assert a.size == b.size
                    assert ImageChops.difference(a, b).getbbox() is None, f"Word page {index+1} differs from native reference"
                with zipfile.ZipFile(source) as archive:
                    document = ET.fromstring(archive.read("word/document.xml"))
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                table_text = ["".join(cell.itertext()) for cell in document.findall(".//w:tbl/w:tr/w:tc", ns)]
                actual_text = "".join(item["text"] for item in actual)
                normalized = "".join(actual_text.split())
                for cell in table_text:
                    assert "".join(cell.split()) in normalized
                assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
                (tmp_path / "word-fidelity-result.json").write_text(json.dumps({
                    "pages": len(actual), "all_pages_pixel_identical": True,
                    "table_cells_checked": sum(bool(cell) for cell in table_text),
                    "original_unchanged": True,
                }, ensure_ascii=False, indent=2), encoding="utf-8")
            finally:
                browser.close()
    finally:
        client.close()
