from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from docx import Document as DocxDocument
from fastapi import UploadFile
from pypdf import PdfReader

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "knowledge.db"
MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_storage() -> None:
    with _connect() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                size INTEGER NOT NULL,
                status TEXT NOT NULL,
                extracted_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)


def _extract_text(path: Path, extension: str) -> str:
    if extension == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if extension == ".docx":
        document = DocxDocument(str(path))
        paragraphs = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                paragraphs.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(paragraphs)
    return path.read_text(encoding="utf-8", errors="replace")


def _clean_text(value: str) -> str:
    value = value.replace("\x00", "")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


async def upload_document(file: UploadFile) -> dict:
    original_name = Path(file.filename or "document").name
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file type. Upload PDF, DOCX, TXT or Markdown.")
    content = await file.read(MAX_FILE_SIZE + 1)
    if not content:
        raise ValueError("The uploaded file is empty.")
    if len(content) > MAX_FILE_SIZE:
        raise ValueError("File is too large. Maximum size is 10 MB.")

    document_id = str(uuid4())
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_path = UPLOAD_DIR / f"{document_id}{extension}"
    stored_path.write_bytes(content)
    try:
        extracted_text = _clean_text(_extract_text(stored_path, extension))
        if not extracted_text:
            raise ValueError("No readable text found in this document.")
        created_at = datetime.now(timezone.utc).isoformat()
        content_type = file.content_type or "application/octet-stream"
        with _connect() as connection:
            connection.execute(
                "INSERT INTO documents (id, filename, content_type, size, status, extracted_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (document_id, original_name, content_type, len(content), "ready", extracted_text, created_at),
            )
        return {"id": document_id, "filename": original_name, "content_type": content_type, "size": len(content), "status": "ready", "character_count": len(extracted_text), "created_at": created_at}
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise


def list_documents() -> list[dict]:
    initialize_storage()
    with _connect() as connection:
        rows = connection.execute("SELECT id, filename, content_type, size, status, created_at, length(extracted_text) AS character_count FROM documents ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def get_document_text(document_id: str) -> dict | None:
    initialize_storage()
    with _connect() as connection:
        row = connection.execute("SELECT id, filename, extracted_text FROM documents WHERE id = ?", (document_id,)).fetchone()
    return dict(row) if row else None
