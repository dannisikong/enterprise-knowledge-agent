import asyncio
import io
import zipfile

import pytest
from fastapi import UploadFile

from app.services import document_service as service


def _upload(name, content):
    return UploadFile(filename=name, file=io.BytesIO(content))


def _configure_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(service, "DB_PATH", tmp_path / "knowledge.db")
    monkeypatch.setattr(service, "embeddings_configured", lambda: False)
    service.initialize_storage()


def _zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files:
            archive.writestr(name, content)
    return buffer.getvalue()


def test_zip_upload_imports_multiple_documents_independently(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    payload = _zip([
        ("policies/access.txt", b"Access policy content"),
        ("handbook/employee.md", b"Employee handbook content"),
    ])
    result = asyncio.run(service.upload_zip_documents(_upload("policies.zip", payload), "session-a"))
    assert result["uploaded_count"] == 2
    assert result["failed_count"] == 0
    assert {item["filename"] for item in service.list_documents("session-a")} == {"access.txt", "employee.md"}
    assert len({item["id"] for item in result["documents"]}) == 2


def test_zip_upload_skips_unsupported_and_nested_archives(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    payload = _zip([
        ("guide.txt", b"Readable content"),
        ("image.png", b"not an image"),
        ("nested.zip", b"not extracted"),
    ])
    result = asyncio.run(service.upload_zip_documents(_upload("bundle.zip", payload), "session-a"))
    assert result["uploaded_count"] == 1
    assert result["skipped_count"] == 2
    assert len(service.list_documents("session-a")) == 1


def test_zip_upload_rejects_path_traversal_before_import(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    payload = _zip([("../outside.txt", b"malicious"), ("safe.txt", b"safe content")])
    with pytest.raises(ValueError, match="unsafe file path"):
        asyncio.run(service.upload_zip_documents(_upload("unsafe.zip", payload), "session-a"))
    assert service.list_documents("session-a") == []


def test_zip_upload_rejects_corrupt_archive(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="Invalid ZIP"):
        asyncio.run(service.upload_zip_documents(_upload("broken.zip", b"not a zip"), "session-a"))


def test_zip_upload_rejects_archive_over_upload_limit(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(service, "MAX_ZIP_FILE_SIZE", 4)
    with pytest.raises(ValueError, match="too large"):
        asyncio.run(service.upload_zip_documents(_upload("large.zip", b"12345"), "session-a"))


def test_zip_upload_rejects_too_many_entries(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    monkeypatch.setattr(service, "MAX_ZIP_ENTRIES", 1)
    payload = _zip([("a.txt", b"a"), ("b.txt", b"b")])
    with pytest.raises(ValueError, match="too many entries"):
        asyncio.run(service.upload_zip_documents(_upload("many.zip", payload), "session-a"))


def test_zip_upload_reports_partial_document_failures(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    payload = _zip([
        ("good.txt", b"valid readable text"),
        ("empty.txt", b""),
    ])
    result = asyncio.run(service.upload_zip_documents(_upload("partial.zip", payload), "session-a"))
    assert result["uploaded_count"] == 1
    assert result["failed_count"] == 1
    assert result["failed"][0]["filename"] == "empty.txt"
