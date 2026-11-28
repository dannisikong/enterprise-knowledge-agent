from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


def _db_path() -> Path:
    data_dir = Path(os.getenv("DATA_DIR", str(Path(__file__).resolve().parents[2] / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "knowledge.db"


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_db_path(), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_trace_id() -> str:
    return str(uuid4())


def initialize_traces() -> None:
    with _connect() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS request_traces (
                trace_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                conversation_id TEXT,
                endpoint TEXT NOT NULL,
                status TEXT NOT NULL,
                requested_mode TEXT,
                effective_mode TEXT,
                fallback_reason TEXT,
                reranker_status TEXT,
                result_count INTEGER NOT NULL DEFAULT 0,
                retrieved_chunks_json TEXT NOT NULL DEFAULT '[]',
                model_name TEXT,
                retrieval_duration_ms REAL,
                model_duration_ms REAL,
                first_token_ms REAL,
                total_duration_ms REAL NOT NULL DEFAULT 0,
                input_chars INTEGER NOT NULL DEFAULT 0,
                output_chars INTEGER NOT NULL DEFAULT 0,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                error_type TEXT,
                created_at TEXT NOT NULL
            )
        """)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_request_traces_session_created "
            "ON request_traces(session_id, created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_request_traces_session_status "
            "ON request_traces(session_id, status, created_at DESC)"
        )


def _safe_chunks(chunks: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    for item in (chunks or [])[:20]:
        safe.append({
            "chunk_id": str(item.get("chunk_id", ""))[:80],
            "document_id": str(item.get("document_id", ""))[:80],
            "filename": str(item.get("filename", ""))[:255],
            "chunk_index": item.get("chunk_index"),
            "score": item.get("score"),
            "rerank_score": item.get("rerank_score"),
        })
    return safe


def record_trace(
    *,
    trace_id: str,
    session_id: str,
    endpoint: str,
    status: str,
    total_duration_ms: float,
    conversation_id: str | None = None,
    requested_mode: str | None = None,
    effective_mode: str | None = None,
    fallback_reason: str | None = None,
    reranker_status: str | None = None,
    retrieved_chunks: list[dict[str, Any]] | None = None,
    model_name: str | None = None,
    retrieval_duration_ms: float | None = None,
    model_duration_ms: float | None = None,
    first_token_ms: float | None = None,
    input_chars: int = 0,
    output_chars: int = 0,
    error_type: str | None = None,
) -> None:
    """Persist operational metadata only; never store prompts, answers, chunk text or credentials."""
    try:
        initialize_traces()
        chunks = _safe_chunks(retrieved_chunks)
        with _connect() as connection:
            connection.execute("""
                INSERT OR REPLACE INTO request_traces (
                    trace_id, session_id, conversation_id, endpoint, status,
                    requested_mode, effective_mode, fallback_reason, reranker_status,
                    result_count, retrieved_chunks_json, model_name,
                    retrieval_duration_ms, model_duration_ms, first_token_ms,
                    total_duration_ms, input_chars, output_chars,
                    prompt_tokens, completion_tokens, error_type, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            """, (
                trace_id, session_id, conversation_id, endpoint, status,
                requested_mode, effective_mode, fallback_reason, reranker_status,
                len(chunks), json.dumps(chunks, ensure_ascii=False),
                (model_name or "")[:128] or None,
                retrieval_duration_ms, model_duration_ms, first_token_ms,
                max(0.0, float(total_duration_ms)), max(0, int(input_chars)),
                max(0, int(output_chars)), (error_type or "")[:128] or None, _now(),
            ))
    except Exception:
        # Observability must never break the user's chat request.
        logger.exception("Failed to persist request trace")


def _trace_from_row(row: sqlite3.Row) -> dict:
    item = dict(row)
    try:
        item["retrieved_chunks"] = json.loads(item.pop("retrieved_chunks_json") or "[]")
    except (TypeError, ValueError):
        item.pop("retrieved_chunks_json", None)
        item["retrieved_chunks"] = []
    return item


def list_traces(session_id: str, *, limit: int = 50, offset: int = 0, status: str | None = None) -> list[dict]:
    initialize_traces()
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    with _connect() as connection:
        if status:
            rows = connection.execute("""
                SELECT trace_id, session_id, conversation_id, endpoint, status,
                       effective_mode, result_count, model_name, retrieval_duration_ms,
                       model_duration_ms, first_token_ms, total_duration_ms,
                       input_chars, output_chars, error_type, created_at
                FROM request_traces
                WHERE session_id = ? AND status = ?
                ORDER BY created_at DESC LIMIT ? OFFSET ?
            """, (session_id, status, limit, offset)).fetchall()
        else:
            rows = connection.execute("""
                SELECT trace_id, session_id, conversation_id, endpoint, status,
                       effective_mode, result_count, model_name, retrieval_duration_ms,
                       model_duration_ms, first_token_ms, total_duration_ms,
                       input_chars, output_chars, error_type, created_at
                FROM request_traces
                WHERE session_id = ?
                ORDER BY created_at DESC LIMIT ? OFFSET ?
            """, (session_id, limit, offset)).fetchall()
    return [dict(row) for row in rows]


def get_trace(trace_id: str, session_id: str) -> dict | None:
    initialize_traces()
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM request_traces WHERE trace_id = ? AND session_id = ?",
            (trace_id, session_id),
        ).fetchone()
    return _trace_from_row(row) if row else None


def cleanup_session_traces(session_ids: list[str]) -> int:
    if not session_ids:
        return 0
    initialize_traces()
    placeholders = ",".join("?" for _ in session_ids)
    with _connect() as connection:
        cursor = connection.execute(
            f"DELETE FROM request_traces WHERE session_id IN ({placeholders})",
            session_ids,
        )
    return cursor.rowcount
