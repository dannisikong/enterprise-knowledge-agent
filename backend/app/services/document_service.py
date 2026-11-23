from __future__ import annotations

import json
import math
import os
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
from app.services.retrieval import keyword_score, reciprocal_rank_fusion
from app.services.reranker_service import rerank_documents, reranker_configured

DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).resolve().parents[2] / "data")))
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
                created_at TEXT NOT NULL,
                session_id TEXT
            )
        """)
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(documents)").fetchall()}
        if "session_id" not in columns:
            connection.execute("ALTER TABLE documents ADD COLUMN session_id TEXT")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_documents_session_id ON documents(session_id)")
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


async def upload_document(file: UploadFile, session_id: str) -> dict:
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
                if vectors is None or len(vectors) != len(chunks):
                    raise RuntimeError("Embedding provider returned an incomplete vector set.")
            except Exception as error:
                raise ValueError(f"Embedding generation failed: {error}") from error

        created_at = datetime.now(timezone.utc).isoformat()
        content_type = file.content_type or "application/octet-stream"
        with _connect() as connection:
            connection.execute(
                "INSERT INTO documents (id, filename, content_type, size, status, extracted_text, created_at, session_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (document_id, original_name, content_type, len(content), "ready", extracted_text, created_at, session_id),
            )
            connection.executemany(
                "INSERT INTO document_chunks (id, document_id, chunk_index, content, embedding, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        str(uuid4()), document_id, index, chunk,
                        json.dumps(vectors[index]) if vectors and index < len(vectors) else None,
                        created_at,
                    )
                    for index, chunk in enumerate(chunks)
                ],
            )
        return {
            "id": document_id, "filename": original_name, "content_type": content_type,
            "size": len(content), "status": "ready", "character_count": len(extracted_text),
            "chunk_count": len(chunks),
            "embedding_status": "indexed" if vectors else "pending",
            "created_at": created_at,
        }
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise


def list_documents(session_id: str) -> list[dict]:
    initialize_storage()
    with _connect() as connection:
        rows = connection.execute("""
            SELECT d.id, d.filename, d.content_type, d.size, d.status, d.created_at,
                   length(d.extracted_text) AS character_count,
                   COUNT(c.id) AS chunk_count,
                   SUM(CASE WHEN c.embedding IS NOT NULL THEN 1 ELSE 0 END) AS embedded_chunk_count
            FROM documents d
            LEFT JOIN document_chunks c ON c.document_id = d.id
            WHERE d.session_id = ?
            GROUP BY d.id
            ORDER BY d.created_at DESC
        """, (session_id,)).fetchall()
    return [dict(row) for row in rows]


async def reindex_documents(session_id: str) -> dict:
    """Regenerate every chunk vector for documents owned by the current session."""
    if not embeddings_configured():
        raise ValueError("Embedding API is not configured on the backend.")

    initialize_storage()
    with _connect() as connection:
        documents = connection.execute(
            "SELECT id, filename FROM documents WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()

    indexed = []
    failed = []
    for document in documents:
        document_id = document["id"]
        with _connect() as connection:
            chunks = connection.execute(
                "SELECT id, content FROM document_chunks WHERE document_id = ? ORDER BY chunk_index",
                (document_id,),
            ).fetchall()

        if not chunks:
            failed.append({"document_id": document_id, "filename": document["filename"], "error": "Document has no text chunks."})
            continue

        try:
            vectors = await create_embeddings([row["content"] for row in chunks])
            if vectors is None or len(vectors) != len(chunks):
                raise RuntimeError("Embedding provider returned an incomplete vector set.")
            dimensions = {len(vector) for vector in vectors}
            if len(dimensions) != 1 or any(not vector for vector in vectors):
                raise RuntimeError("Embedding provider returned inconsistent vector dimensions.")

            with _connect() as connection:
                connection.executemany(
                    "UPDATE document_chunks SET embedding = ? WHERE id = ?",
                    [(json.dumps(vector), row["id"]) for row, vector in zip(chunks, vectors)],
                )
            indexed.append({
                "document_id": document_id,
                "filename": document["filename"],
                "chunk_count": len(chunks),
                "embedded_chunk_count": len(vectors),
            })
        except Exception as error:
            failed.append({
                "document_id": document_id,
                "filename": document["filename"],
                "error": str(error)[:500],
            })

    return {
        "total_documents": len(documents),
        "indexed_documents": len(indexed),
        "failed_documents": len(failed),
        "indexed": indexed,
        "failed": failed,
    }


def get_document_text(document_id: str, session_id: str) -> dict | None:
    initialize_storage()
    with _connect() as connection:
        row = connection.execute(
            "SELECT id, filename, extracted_text FROM documents WHERE id = ? AND session_id = ?", (document_id, session_id)
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


def _rank_keyword(rows, query: str) -> list[dict]:
    results = []
    for row in rows:
        score = keyword_score(query, row["content"])
        if score > 0:
            results.append(_result_from_row(row, score))
    return sorted(results, key=lambda item: item["score"], reverse=True)


def _result_from_row(row, score: float) -> dict:
    return {
        "chunk_id": row["id"],
        "document_id": row["document_id"],
        "filename": row["filename"],
        "chunk_index": row["chunk_index"],
        "content": row["content"],
        "score": round(float(score), 4),
    }


async def search_chunks(query: str, limit: int = 5, mode: str = "auto", rerank: bool = False, session_id: str | None = None) -> dict:
    initialize_storage()
    query = query.strip()
    if not query:
        raise ValueError("Query must not be empty.")
    limit = max(1, min(limit, 20))
    if mode not in {"auto", "keyword", "vector", "hybrid"}:
        raise ValueError("Mode must be auto, keyword, vector or hybrid.")

    with _connect() as connection:
        rows = connection.execute("""
            SELECT c.id, c.document_id, c.chunk_index, c.content, c.embedding, d.filename
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.session_id = ?
        """, (session_id,)).fetchall()

    keyword_results = _rank_keyword(rows, query) if mode in {"keyword", "hybrid", "auto"} else []
    wants_vector = mode in {"vector", "hybrid", "auto"}
    query_vector = None
    if wants_vector and embeddings_configured():
        try:
            vectors = await create_embeddings([query])
            query_vector = vectors[0] if vectors else None
        except Exception:
            query_vector = None

    vector_results = []
    if query_vector:
        for row in rows:
            if not row["embedding"]:
                continue
            score = _cosine_similarity(query_vector, json.loads(row["embedding"]))
            if score > 0:
                vector_results.append(_result_from_row(row, score))
        vector_results.sort(key=lambda item: item["score"], reverse=True)

    has_stored_vectors = any(row["embedding"] for row in rows)
    vector_available = bool(query_vector and has_stored_vectors)
    if mode == "vector" and not vector_available:
        raise ValueError(
            "Vector search is unavailable. Configure embeddings and upload documents with vectors first."
        )

    if mode == "keyword":
        effective_mode, results = "keyword", keyword_results[:limit]
    elif mode == "vector":
        effective_mode, results = "vector", vector_results[:limit]
    elif vector_available:
        effective_mode = "hybrid"
        candidates = reciprocal_rank_fusion(
            [keyword_results[:50], vector_results[:50]], limit=min(20, max(limit * 4, limit))
        )
        results = candidates[:limit]
    else:
        effective_mode, results = "keyword_fallback", keyword_results[:limit]

    reranker_status = "not_requested"
    reranker_error = None
    if rerank:
        if effective_mode != "hybrid":
            reranker_status = "skipped_no_hybrid_candidates"
        elif not reranker_configured():
            reranker_status = "unavailable"
            reranker_error = "Configure RERANK_API_KEY to enable reranking."
        else:
            try:
                results = await rerank_documents(query, candidates, limit)
                reranker_status = "applied"
            except Exception as error:
                reranker_status = "failed_fallback"
                reranker_error = str(error)
                results = candidates[:limit]

    return {
        "query": query,
        "mode": effective_mode,
        "reranker": reranker_status,
        "reranker_error": reranker_error,
        "requested_mode": mode,
        "fallback_reason": (
            None if effective_mode != "keyword_fallback"
            else "Embedding API or indexed document vectors are unavailable; returned keyword results."
        ),
        "fusion": "reciprocal_rank_fusion" if effective_mode == "hybrid" else None,
        "results": results,
    }


def cleanup_session_documents(session_ids: list[str]) -> int:
    """Delete expired sessions' document rows, chunks and stored upload files."""
    if not session_ids:
        return 0
    initialize_storage()
    deleted = 0
    with _connect() as connection:
        for session_id in session_ids:
            rows = connection.execute(
                "SELECT id FROM documents WHERE session_id = ?", (session_id,)
            ).fetchall()
            for row in rows:
                document_id = row["id"]
                for stored_path in UPLOAD_DIR.glob(f"{document_id}.*"):
                    stored_path.unlink(missing_ok=True)
                connection.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
                connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
                deleted += 1
    return deleted
