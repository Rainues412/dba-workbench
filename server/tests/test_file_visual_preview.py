import base64
import time
import pytest
from urllib.parse import parse_qs, unquote, urlsplit

from backend import file_visual_preview, local_capabilities
from backend.config import Settings
from backend import word_preview


def enable(monkeypatch, root, actions="open"):
    monkeypatch.setattr(local_capabilities, "_enrolled_roots", set())
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true",
        "DBA_ALLOWED_ROOTS": str(root),
        "DBA_ALLOWED_LOCAL_ACTIONS": actions,
    }))


def record(client, path, module="articles"):
    response = client.post(f"/api/{module}/", json={"title": "原文件预览", "file_path": str(path)})
    assert response.status_code == 200
    return response.json()


def source_path(viewer_url: str) -> str:
    encoded = parse_qs(urlsplit(viewer_url).query)["url"][0]
    return urlsplit(base64.b64decode(unquote(encoded)).decode("utf-8")).path


def test_visual_preview_hands_authorized_file_to_bundled_viewer(client, raw_client, tmp_path, monkeypatch):
    enable(monkeypatch, tmp_path)
    monkeypatch.setattr(file_visual_preview, "_viewer_available", lambda: True)
    target = tmp_path / "原始版式.pdf"
    original = b"%PDF-1.7\nlayout-bytes"
    target.write_bytes(original)
    row = record(client, target)

    response = client.get(f"/api/articles/{row['id']}/visual-preview")
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    payload = response.json()
    assert payload["filename"] == target.name
    assert payload["viewer"] == "kkFileView"
    assert payload["viewer_version"] == "5.0.3"
    assert str(target) not in payload["viewer_url"]
    assert parse_qs(urlsplit(payload["viewer_url"]).query)["key"] == [file_visual_preview.VIEWER_KEY]

    path = source_path(payload["viewer_url"])
    streamed = raw_client.get(path)
    assert streamed.status_code == 200
    assert streamed.content == original
    assert streamed.headers["Cache-Control"] == "private, no-store"
    assert streamed.headers["Content-Type"].startswith("application/pdf")
    assert raw_client.head(path).status_code == 200

    enable(monkeypatch, tmp_path, actions="folder")
    assert raw_client.get(path).status_code == 403


def test_visual_preview_keeps_session_capability_and_path_boundaries(client, raw_client, tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "guide.docx"
    target.write_bytes(b"docx")
    row = record(client, target, "scripts")
    monkeypatch.setattr(file_visual_preview, "_viewer_available", lambda: True)

    monkeypatch.setattr(local_capabilities, "_enrolled_roots", set())
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({}))
    assert client.get(f"/api/scripts/{row['id']}/visual-preview").status_code == 403

    enable(monkeypatch, allowed)
    issued = client.get(f"/api/scripts/{row['id']}/visual-preview")
    assert issued.status_code == 200
    path = source_path(issued.json()["viewer_url"])
    target.unlink()
    assert raw_client.get(path).status_code == 404
    assert raw_client.get(path.replace("guide.docx", "other.docx")).status_code == 404


def test_visual_preview_reports_viewer_startup_and_expired_grants(client, raw_client, tmp_path, monkeypatch):
    enable(monkeypatch, tmp_path)
    target = tmp_path / "slides.pptx"
    target.write_bytes(b"pptx")
    row = record(client, target)

    monkeypatch.setattr(file_visual_preview, "_viewer_available", lambda: False)
    response = client.get(f"/api/articles/{row['id']}/visual-preview")
    assert response.status_code == 503
    assert "正在启动或不可用" in response.json()["error"]["message"]

    monkeypatch.setattr(file_visual_preview, "_viewer_available", lambda: True)
    issued = client.get(f"/api/articles/{row['id']}/visual-preview")
    path = source_path(issued.json()["viewer_url"])
    token = path.split("/")[2]
    grant = file_visual_preview._grants[token]
    file_visual_preview._grants[token] = file_visual_preview.PreviewGrant(grant.target, time.time() - 1)
    assert raw_client.get(path).status_code == 404


def test_visual_preview_issue_endpoint_requires_login(raw_client):
    assert raw_client.get("/api/articles/1/visual-preview").status_code == 401


def test_word_native_preview_retains_grants_revocation_and_version_checks(client, raw_client, tmp_path, monkeypatch):
    enable(monkeypatch, tmp_path)
    monkeypatch.setattr(file_visual_preview, "_viewer_available", lambda: True)
    monkeypatch.setattr(word_preview, "is_available", lambda: True)
    target = tmp_path / "中文原件.docx"
    target.write_bytes(b"source")
    rendered = tmp_path / word_preview.pdf_name(target)
    rendered.write_bytes(b"%PDF-1.7\nlayout")
    monkeypatch.setattr(word_preview, "convert", lambda source: rendered)
    row = record(client, target)
    issued = client.get(f"/api/articles/{row['id']}/visual-preview")
    assert issued.status_code == 200
    assert issued.json()["converter"] == "Microsoft Word"
    path = source_path(issued.json()["viewer_url"])
    assert "/preview-file/word/" in path
    assert raw_client.get(path).content == rendered.read_bytes()
    assert raw_client.head(path).headers["content-type"].startswith("application/pdf")
    assert raw_client.get(path.replace(rendered.name, "other.pdf")).status_code == 404
    enable(monkeypatch, tmp_path, actions="folder")
    assert raw_client.get(path).status_code == 403
    enable(monkeypatch, tmp_path)
    target.write_bytes(b"source changed")
    assert raw_client.get(path).status_code == 404
    target.unlink()
    assert raw_client.get(path).status_code == 404


def test_word_conversion_failure_returns_actionable_error(client, tmp_path, monkeypatch):
    enable(monkeypatch, tmp_path)
    monkeypatch.setattr(file_visual_preview, "_viewer_available", lambda: True)
    monkeypatch.setattr(word_preview, "is_available", lambda: True)
    target = tmp_path / "original.docx"
    target.write_bytes(b"source")
    row = record(client, target)

    def fail(source):
        raise word_preview.WordPreviewError("Word 转换失败")

    monkeypatch.setattr(word_preview, "convert", fail)
    response = client.get(f"/api/articles/{row['id']}/visual-preview")
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Word 转换失败"


@pytest.mark.parametrize(("extension", "content_type"), [("png", "image/png"), ("jfif", "image/jpeg"), ("JFIF", "image/jpeg")])
def test_markdown_preview_serves_original_source_and_relative_images_without_sidecar(client, raw_client, tmp_path, monkeypatch, extension, content_type):
    enable(monkeypatch, tmp_path)
    monkeypatch.setattr(file_visual_preview, "_viewer_available", lambda: False)
    target = tmp_path / "安装.md"
    source = f"![原图](img/中文%20图片.{extension})\n\n| 数据库 | 版本 |\n| --- | --- |\n| Oracle | 11g |"
    target.write_text(source, encoding="utf-8")
    image = tmp_path / "img" / f"中文 图片.{extension}"
    image.parent.mkdir()
    image.write_bytes(b"original-image-bytes")
    row = record(client, target)
    response = client.get(f"/api/articles/{row['id']}/visual-preview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["viewer"] == "markdown"
    assert raw_client.get(payload["viewer_url"]).content == target.read_bytes()
    loaded = raw_client.get(payload["asset_url"], params={"path": f"img/中文%20图片.{extension}"})
    assert loaded.status_code == 200
    assert loaded.content == image.read_bytes()
    assert loaded.headers["Content-Type"] == content_type
    assert loaded.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"
    assert raw_client.head(payload["asset_url"], params={"path": f"img\\中文 图片.{extension}"}).status_code == 200
    enable(monkeypatch, tmp_path, actions="folder")
    assert raw_client.get(payload["asset_url"], params={"path": f"img/中文 图片.{extension}"}).status_code == 403


@pytest.mark.parametrize("reference", ["../outside.png", "..\\outside.png", "%2e%2e/outside.png", "/outside.png", "C:/outside.png", "//server/share.png", "https://example.test/image.png", "notes.txt"])
def test_markdown_image_grants_cannot_read_other_directories_or_file_types(client, raw_client, tmp_path, monkeypatch, reference):
    enable(monkeypatch, tmp_path)
    document_dir = tmp_path / "document"
    document_dir.mkdir()
    target = document_dir / "guide.md"
    target.write_text("# Test", encoding="utf-8")
    (tmp_path / "outside.png").write_bytes(b"outside")
    (document_dir / "notes.txt").write_text("private data", encoding="utf-8")
    row = record(client, target)
    payload = client.get(f"/api/articles/{row['id']}/visual-preview").json()
    assert raw_client.get(payload["asset_url"], params={"path": reference}).status_code == 403


def test_markdown_image_grant_expires_and_checks_current_paths(client, raw_client, tmp_path, monkeypatch):
    enable(monkeypatch, tmp_path)
    target = tmp_path / "guide.markdown"
    target.write_text("![image](image.svg)", encoding="utf-8")
    image = tmp_path / "image.svg"
    image.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    row = record(client, target)
    payload = client.get(f"/api/articles/{row['id']}/visual-preview").json()
    assert raw_client.get(payload["asset_url"], params={"path": "image.svg"}).status_code == 200
    assert raw_client.get(payload["asset_url"], params={"path": "missing.png"}).status_code == 404
    token = payload["asset_url"].split("/")[-1]
    grant = file_visual_preview._grants[token]
    file_visual_preview._grants[token] = file_visual_preview.PreviewGrant(grant.target, time.time() - 1)
    assert raw_client.get(payload["asset_url"], params={"path": "image.svg"}).status_code == 404
