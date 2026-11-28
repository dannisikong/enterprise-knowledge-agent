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
                question TEXT,
                answer TEXT,
                sources_json TEXT NOT NULL DEFAULT '[]',
                diagnostic_chunks_json TEXT NOT NULL DEFAULT '[]',
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
        # Additive migration for databases created by earlier PR #13 versions.
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(request_traces)")}
        for name, definition in (
            ("question", "TEXT"),
            ("answer", "TEXT"),
            ("sources_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("diagnostic_chunks_json", "TEXT NOT NULL DEFAULT '[]'"),
        ):
            if name not in columns:
                connection.execute(f"ALTER TABLE request_traces ADD COLUMN {name} {definition}")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS trace_feedback (
                id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                rating TEXT NOT NULL CHECK(rating IN ('correct', 'incorrect', 'retrieval_issue', 'citation_issue')),
                comment TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(trace_id, session_id)
            )
        """)


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
        if os.getenv("TRACE_CAPTURE_CHUNK_TEXT", "false").lower() in {"1", "true", "yes", "on"}:
            safe[-1]["content"] = str(item.get("content", ""))[:4000]
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
    question: str | None = None,
    answer: str | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> None:
    """Persist bounded diagnostic data; credentials and model prompts are never stored."""
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
                    prompt_tokens, completion_tokens, error_type, question, answer,
                    sources_json, diagnostic_chunks_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?)
            """, (
                trace_id, session_id, conversation_id, endpoint, status,
                requested_mode, effective_mode, fallback_reason, reranker_status,
                len(chunks), json.dumps(chunks, ensure_ascii=False),
                (model_name or "")[:128] or None,
                retrieval_duration_ms, model_duration_ms, first_token_ms,
                max(0.0, float(total_duration_ms)), max(0, int(input_chars)),
                max(0, int(output_chars)), (error_type or "")[:128] or None,
                (question or "")[:2000] or None, (answer or "")[:20000] or None,
                json.dumps((sources or [])[:20], ensure_ascii=False),
                json.dumps(chunks if os.getenv("TRACE_CAPTURE_CHUNK_TEXT", "false").lower() in {"1", "true", "yes", "on"} else [], ensure_ascii=False),
                _now(),
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
    if not row:
        return None
    item = _trace_from_row(row)
    try:
        item["sources"] = json.loads(item.pop("sources_json") or "[]")
    except (TypeError, ValueError):
        item["sources"] = []
    try:
        item["diagnostic_chunks"] = json.loads(item.pop("diagnostic_chunks_json") or "[]")
    except (TypeError, ValueError):
        item["diagnostic_chunks"] = []
    return item


def submit_feedback(trace_id: str, session_id: str, rating: str, comment: str | None = None) -> dict | None:
    if rating not in {"correct", "incorrect", "retrieval_issue", "citation_issue"}:
        raise ValueError("Unsupported feedback rating.")
    initialize_traces()
    feedback_id = str(uuid4())
    created_at = _now()
    with _connect() as connection:
        exists = connection.execute(
            "SELECT 1 FROM request_traces WHERE trace_id = ? AND session_id = ?",
            (trace_id, session_id),
        ).fetchone()
        if not exists:
            return None
        connection.execute("""
            INSERT INTO trace_feedback (id, trace_id, session_id, rating, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(trace_id, session_id) DO UPDATE SET
                rating = excluded.rating, comment = excluded.comment, created_at = excluded.created_at
        """, (feedback_id, trace_id, session_id, rating, (comment or "")[:1000] or None, created_at))
    return {"trace_id": trace_id, "rating": rating, "comment": (comment or "")[:1000] or None, "created_at": created_at}


def cleanup_expired_traces(retention_days: int | None = None) -> int:
    if retention_days is None:
        try:
            retention_days = int(os.getenv("TRACE_RETENTION_DAYS", "30"))
        except ValueError:
            retention_days = 30
    retention_days = max(1, min(retention_days, 3650))
    cutoff = datetime.now(timezone.utc).timestamp() - retention_days * 86400
    cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
    initialize_traces()
    with _connect() as connection:
        connection.execute("DELETE FROM trace_feedback WHERE trace_id IN (SELECT trace_id FROM request_traces WHERE created_at < ?)", (cutoff_iso,))
        cursor = connection.execute("DELETE FROM request_traces WHERE created_at < ?", (cutoff_iso,))
    return cursor.rowcount


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
