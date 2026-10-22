import os
from zipfile import ZipFile

import pytest

from backend import file_preview, local_capabilities
from backend.config import Settings


def enable(monkeypatch, root, actions="open"):
    monkeypatch.setattr(local_capabilities, "_enrolled_roots", set())
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({
        "DBA_LOCAL_CAPABILITIES": "true", "DBA_ALLOWED_ROOTS": str(root),
        "DBA_ALLOWED_LOCAL_ACTIONS": actions,
    }))


def record(client, path, module="scripts"):
    result = client.post(f"/api/{module}/", json={"title": "仅路径记录", "file_path": str(path)})
    assert result.status_code == 200
    return result.json()


@pytest.mark.parametrize("module", ["scripts", "articles"])
@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16", "gb18030"])
def test_linked_file_preview_reads_old_records_without_persisting(client, tmp_path, monkeypatch, module, encoding):
    enable(monkeypatch, tmp_path)
    text = "-- 中文巡检\nselect '<img src=x onerror=alert(1)>';"
    target = tmp_path / "巡检.SQL"
    original = text.encode(encoding)
    target.write_bytes(original)
    row = record(client, target, module)
    result = client.get(f"/api/{module}/{row['id']}/file-preview")
    assert result.status_code == 200, result.text
    assert result.headers["Cache-Control"] == "no-store"
    assert result.json() == {"filename": target.name, "content": text, "truncated": False}
    saved = client.get(f"/api/{module}/{row['id']}").json()
    assert saved["content"] == ""
    assert saved["revision"] == row["revision"]
    assert saved["updated_at"] == row["updated_at"]
    assert target.read_bytes() == original


def test_preview_keeps_local_capability_and_path_boundaries(client, tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "secret.sql"
    outside.write_text("secret", encoding="utf-8")
    inside = allowed / "ok.sql"
    inside.write_text("select 1;", encoding="utf-8")
    row = record(client, inside)
    monkeypatch.setattr(local_capabilities, "_enrolled_roots", set())
    monkeypatch.setattr(local_capabilities, "settings", Settings.from_env({}))
    assert client.get(f"/api/scripts/{row['id']}/file-preview").status_code == 403
    enable(monkeypatch, allowed, actions="folder")
    assert client.get(f"/api/scripts/{row['id']}/file-preview").status_code == 403
    enable(monkeypatch, allowed)
    for path in [outside, allowed / ".." / "secret.sql", r"\\server\share\secret.sql", "relative.sql"]:
        row = record(client, path)
        assert client.get(f"/api/scripts/{row['id']}/file-preview").status_code == 403
    # A junction is available without Windows Developer Mode/admin symlink rights.
    import subprocess
    link = allowed / "linked"
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(tmp_path)], check=True, capture_output=True)
    else:
        link.symlink_to(tmp_path, target_is_directory=True)
    try:
        row = record(client, link / "secret.sql")
        assert client.get(f"/api/scripts/{row['id']}/file-preview").status_code == 403
    finally:
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()


@pytest.mark.parametrize("suffix,data,status", [
    (".sql", b"a\x00b", 415), (".sql", b"\xff", 415),
    (".exe", b"not a text preview", 415), (".pdf", b"%PDF-1.7", 415),
    (".docx", b"broken zip", 415),
])
def test_invalid_formats_fail_clearly(client, tmp_path, monkeypatch, suffix, data, status):
    enable(monkeypatch, tmp_path)
    target = tmp_path / ("file" + suffix)
    target.write_bytes(data)
    row = record(client, target)
    response = client.get(f"/api/scripts/{row['id']}/file-preview")
    assert response.status_code == status, response.text


def test_empty_missing_and_truncated_files(client, tmp_path, monkeypatch):
    enable(monkeypatch, tmp_path)
    assert client.get("/api/articles/999/file-preview").status_code == 404
    empty = tmp_path / "empty.md"
    empty.write_bytes(b"")
    row = record(client, empty, "articles")
    assert client.get(f"/api/articles/{row['id']}/file-preview").json()["content"] == ""
    empty.unlink()
    assert client.get(f"/api/articles/{row['id']}/file-preview").status_code == 404
    # Cut a UTF-8 multibyte character at the size boundary without corrupting it.
    large = tmp_path / "large.sql"
    large.write_bytes(b"a" * (file_preview.MAX_TEXT_BYTES - 1) + "中文".encode())
    row = record(client, large)
    preview = client.get(f"/api/scripts/{row['id']}/file-preview").json()
    assert preview["truncated"] is True
    assert preview["content"] == "a" * (file_preview.MAX_TEXT_BYTES - 1)


def test_docx_text_and_untrusted_xml_limits(client, tmp_path, monkeypatch):
    enable(monkeypatch, tmp_path)
    target = tmp_path / "说明.docx"
    row = record(client, target, "articles")
    url = f"/api/articles/{row['id']}/file-preview"
    xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>操作说明</w:t><w:br/><w:t>下一行</w:t></w:r></w:p><w:p><w:r><w:t>下一段</w:t></w:r></w:p></w:body></w:document>'
    with ZipFile(target, "w") as archive:
        archive.writestr("word/document.xml", xml)
    assert client.get(url).json()["content"] == "操作说明\n下一行\n下一段"
    for encoding in ["utf-8", "utf-16"]:
        malicious = '<!DOCTYPE x [<!ENTITY test "expanded">]><x>&test;</x>'
        with ZipFile(target, "w") as archive:
            archive.writestr("word/document.xml", malicious.encode(encoding))
        assert client.get(url).status_code == 415
    with ZipFile(target, "w") as archive:
        archive.writestr("word/document.xml", b"x" * (file_preview.MAX_DOCUMENT_XML + 1))
    assert client.get(url).status_code == 413


def test_preview_requires_authenticated_session(raw_client):
    assert raw_client.get("/api/scripts/1/file-preview").status_code == 401
