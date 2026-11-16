from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from docx import Document as DocxDocument
from fastapi import UploadFile
from pypdf import PdfReader

from app.services.chunking import split_text
from app.services.embedding_service import create_embeddings, embeddings_configured

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
        connection.execute("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                embedding TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
            )
        """)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON document_chunks(document_id)"
        )


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

        chunks = split_text(extracted_text)
        vectors: list[list[float]] | None = None
        if embeddings_configured():
            try:
                vectors = await create_embeddings(chunks)
            except Exception:
                # Keep ingestion available; keyword retrieval remains usable.
                vectors = None

        created_at = datetime.now(timezone.utc).isoformat()
        content_type = file.content_type or "application/octet-stream"
        with _connect() as connection:
            connection.execute(
                "INSERT INTO documents (id, filename, content_type, size, status, extracted_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (document_id, original_name, content_type, len(content), "ready", extracted_text, created_at),
            )
            connection.executemany(
                "INSERT INTO document_chunks (id, document_id, chunk_index, content, embedding, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        str(uuid4()),
                        document_id,
                        index,
                        chunk,
                        json.dumps(vectors[index]) if vectors and index < len(vectors) else None,
                        created_at,
                    )
                    for index, chunk in enumerate(chunks)
                ],
            )
        return {
            "id": document_id,
            "filename": original_name,
            "content_type": content_type,
            "size": len(content),
            "status": "ready",
            "character_count": len(extracted_text),
            "chunk_count": len(chunks),
            "embedding_status": "indexed" if vectors else "pending",
            "created_at": created_at,
        }
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise


def list_documents() -> list[dict]:
    initialize_storage()
    with _connect() as connection:
        rows = connection.execute("""
            SELECT d.id, d.filename, d.content_type, d.size, d.status, d.created_at,
                   length(d.extracted_text) AS character_count,
                   COUNT(c.id) AS chunk_count,
                   SUM(CASE WHEN c.embedding IS NOT NULL THEN 1 ELSE 0 END) AS embedded_chunk_count
            FROM documents d
            LEFT JOIN document_chunks c ON c.document_id = d.id
            GROUP BY d.id
            ORDER BY d.created_at DESC
        """).fetchall()
    return [dict(row) for row in rows]


def get_document_text(document_id: str) -> dict | None:
    initialize_storage()
    with _connect() as connection:
        row = connection.execute(
            "SELECT id, filename, extracted_text FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
    return dict(row) if row else None


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _keyword_score(query: str, content: str) -> float:
    terms = {term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]+", query) if len(term) > 1}
    if not terms:
        return 0.0
    target = content.lower()
    matched = sum(1 for term in terms if term in target)
    return matched / len(terms)


async def search_chunks(query: str, limit: int = 5) -> dict:
    initialize_storage()
    query = query.strip()
    if not query:
        raise ValueError("Query must not be empty.")
    limit = max(1, min(limit, 20))

    query_vector = None
    if embeddings_configured():
        try:
            vectors = await create_embeddings([query])
            query_vector = vectors[0] if vectors else None
        except Exception:
            query_vector = None

    with _connect() as connection:
        rows = connection.execute("""
            SELECT c.id, c.document_id, c.chunk_index, c.content, c.embedding,
                   d.filename
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
        """).fetchall()

    has_vectors = any(row["embedding"] for row in rows)
    use_vector_search = bool(query_vector and has_vectors)
    results = []
    search_mode = "vector" if use_vector_search else "keyword"
    for row in rows:
        if use_vector_search:
            if not row["embedding"]:
                continue
            score = _cosine_similarity(query_vector, json.loads(row["embedding"]))
        else:
            score = _keyword_score(query, row["content"])
        if score > 0:
            results.append({
                "chunk_id": row["id"],
                "document_id": row["document_id"],
                "filename": row["filename"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "score": round(float(score), 4),
            })

    results.sort(key=lambda item: item["score"], reverse=True)
    return {"query": query, "mode": search_mode, "results": results[:limit]}
