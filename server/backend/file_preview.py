"""Bounded, read-only previews of record-linked files inside authorized roots."""
import codecs
import io
import zlib
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from backend.database import get_db_ctx
from backend.local_capabilities import audit_local_action, require_local_action, resolve_allowed_path

MAX_TEXT_BYTES = 512 * 1024
MAX_DOCX_BYTES = 16 * 1024 * 1024
MAX_DOCUMENT_XML = 2 * 1024 * 1024
TEXT_EXTENSIONS = {
    ".sql", ".sh", ".py", ".ps1", ".bat", ".cmd", ".txt", ".md", ".markdown",
    ".log", ".json", ".yaml", ".yml", ".xml", ".csv", ".ini", ".conf", ".cfg",
    ".html", ".htm",
}


def _decode_text(data: bytes, truncated: bool) -> str:
    # Incremental decoding keeps a truncated multibyte character out of the preview.
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        encodings = ("utf-16",)
    elif data.startswith(codecs.BOM_UTF8):
        encodings = ("utf-8-sig",)
    else:
        if b"\x00" in data:
            raise HTTPException(415, "文件不是可预览的文本，请使用快捷打开")
        encodings = ("utf-8", "gb18030")
    for encoding in encodings:
        try:
            return codecs.getincrementaldecoder(encoding)().decode(data, final=not truncated)
        except UnicodeError:
            continue
    raise HTTPException(415, "无法识别文件编码，请使用快捷打开")


def _docx_text(data: bytes) -> str:
    with ZipFile(io.BytesIO(data)) as archive:
        info = archive.getinfo("word/document.xml")
        if info.file_size > MAX_DOCUMENT_XML:
            raise HTTPException(413, "文档正文过大，请使用快捷打开")
        with archive.open(info) as document:
            xml = document.read(MAX_DOCUMENT_XML + 1)
    if len(xml) > MAX_DOCUMENT_XML:
        raise HTTPException(413, "文档正文过大，请使用快捷打开")
    # DOCX needs neither DTDs nor entities. Reject these before XML parsing,
    # including UTF-16 declarations, rather than expanding untrusted entities.
    declaration = xml.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in declaration or b"<!ENTITY" in declaration:
        raise HTTPException(415, "文档包含不支持的 XML 声明，请使用快捷打开")
    root = ElementTree.fromstring(xml)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    parts = []
    for node in root.iter():
        if node.tag == namespace + "t":
            parts.append(node.text or "")
        elif node.tag == namespace + "tab":
            parts.append("\t")
        elif node.tag in {namespace + "br", namespace + "cr", namespace + "p"}:
            parts.append("\n")
    return "".join(parts).strip("\n")


def preview_linked_file(module: str, record_id: int) -> JSONResponse:
    # Table names come exclusively from the two router call sites, never input.
    if module not in {"articles", "scripts"}:
        raise HTTPException(404, "记录不存在")
    with get_db_ctx() as conn:
        row = conn.execute(f"SELECT file_path FROM {module} WHERE id = ?", (record_id,)).fetchone()
    if not row:
        raise HTTPException(404, "记录不存在")
    if not row["file_path"]:
        raise HTTPException(404, "未关联本地文件")
    require_local_action("open")
    target = None
    try:
        target = resolve_allowed_path(row["file_path"], expect="file")
        suffix = target.suffix.lower()
        if suffix not in TEXT_EXTENSIONS and suffix != ".docx":
            raise HTTPException(415, "此格式暂不支持在线预览，请使用快捷打开")
        limit = MAX_DOCX_BYTES if suffix == ".docx" else MAX_TEXT_BYTES
        with target.open("rb") as source:
            data = source.read(limit + 1)
        truncated = len(data) > limit
        if suffix == ".docx":
            if truncated:
                raise HTTPException(413, "文档文件过大，请使用快捷打开")
            text = _docx_text(data)
            truncated = len(text) > MAX_TEXT_BYTES
            text = text[:MAX_TEXT_BYTES]
        else:
            text = _decode_text(data[:limit], truncated)
        audit_local_action("preview", "allowed", target)
        return JSONResponse({"filename": target.name, "content": text, "truncated": truncated}, headers={"Cache-Control": "no-store"})
    except HTTPException:
        audit_local_action("preview", "denied", target)
        raise
    except PermissionError:
        audit_local_action("preview", "denied", target)
        raise HTTPException(403, "无法读取文件，请检查文件权限")
    except (BadZipFile, KeyError, ElementTree.ParseError, RuntimeError, NotImplementedError, zlib.error):
        audit_local_action("preview", "invalid_document", target)
        raise HTTPException(415, "文档格式损坏或不受支持，请使用快捷打开")
    except OSError:
        audit_local_action("preview", "unavailable", target)
        raise HTTPException(404, "文件不存在或暂时无法读取")
