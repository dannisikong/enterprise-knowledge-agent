import asyncio
import io
import zipfile

import pytest
from docx import Document as DocxDocument
from fastapi import UploadFile
from pypdf import PdfWriter

from app.services import document_service as service


def _upload(name, content, content_type="application/octet-stream"):
    return UploadFile(filename=name, file=io.BytesIO(content), headers={"content-type": content_type})


def _configure_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(service, "DB_PATH", tmp_path / "knowledge.db")
    monkeypatch.setattr(service, "embeddings_configured", lambda: False)
    service.initialize_storage()


def test_upload_accepts_valid_text_and_persists_document(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    result = asyncio.run(service.upload_document(_upload("guide.txt", b"hello enterprise knowledge"), "session-a"))
    assert result["status"] == "ready"
    assert result["chunk_count"] == 1
    assert service.list_documents("session-a")[0]["filename"] == "guide.txt"


def test_upload_rejects_file_over_size_limit(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(service, "MAX_FILE_SIZE", 4)
    with pytest.raises(ValueError, match="10 MB|too large"):
        asyncio.run(service.upload_document(_upload("large.txt", b"12345"), "session-a"))
    assert list(service.UPLOAD_DIR.glob("*")) == []


def test_upload_rejects_extracted_text_over_limit_and_cleans_file(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(service, "MAX_EXTRACTED_TEXT_CHARS", 5)
    with pytest.raises(ValueError, match="processing limit"):
        asyncio.run(service.upload_document(_upload("long.txt", b"123456"), "session-a"))
    assert list(service.UPLOAD_DIR.glob("*")) == []


def test_upload_rejects_too_many_chunks_and_cleans_file(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(service, "MAX_CHUNKS_PER_DOCUMENT", 1)
    with pytest.raises(ValueError, match="too many text chunks"):
        asyncio.run(service.upload_document(_upload("long.txt", b"x" * 2000), "session-a"))
    assert list(service.UPLOAD_DIR.glob("*")) == []


def test_upload_rejects_pdf_over_page_limit(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(service, "MAX_PDF_PAGES", 1)
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_blank_page(width=72, height=72)
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(ValueError, match="page processing limit"):
        asyncio.run(service.upload_document(_upload("many-pages.pdf", buffer.getvalue()), "session-a"))
    assert list(service.UPLOAD_DIR.glob("*")) == []


def test_upload_rejects_docx_zip_bomb_by_expanded_size(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(service, "MAX_DOCX_UNCOMPRESSED_SIZE", 1024)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "<document>" + ("A" * 4096) + "</document>")
    with pytest.raises(ValueError, match="expands beyond"):
        asyncio.run(service.upload_document(_upload("oversized.docx", buffer.getvalue()), "session-a"))
    assert list(service.UPLOAD_DIR.glob("*")) == []


def test_upload_rejects_malformed_docx_and_cleans_file(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="Invalid DOCX"):
        asyncio.run(service.upload_document(_upload("broken.docx", b"not a zip archive"), "session-a"))
    assert list(service.UPLOAD_DIR.glob("*")) == []


def test_docx_validation_allows_a_normal_generated_document(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    document = DocxDocument()
    document.add_paragraph("Enterprise knowledge guide")
    buffer = io.BytesIO()
    document.save(buffer)
    result = asyncio.run(service.upload_document(_upload("guide.docx", buffer.getvalue()), "session-a"))
    assert result["status"] == "ready"
    assert result["character_count"] > 0
