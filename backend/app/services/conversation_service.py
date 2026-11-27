from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _db_path() -> Path:
    data_dir = Path(os.getenv("DATA_DIR", str(Path(__file__).resolve().parents[2] / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "knowledge.db"


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_db_path(), timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_conversations() -> None:
    with _connect() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '新对话',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                sources_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            )
        """)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_conversations_session_updated ON conversations(session_id, updated_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON messages(conversation_id, created_at)")


def create_conversation(session_id: str, title: str | None = None) -> dict:
    initialize_conversations()
    now = _now()
    item = {
        "id": str(uuid4()), "session_id": session_id,
        "title": (title or "").strip()[:120] or "新对话",
        "created_at": now, "updated_at": now,
    }
    with _connect() as connection:
        connection.execute(
            "INSERT INTO conversations (id, session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (item["id"], session_id, item["title"], now, now),
        )
    return item


def get_conversation(conversation_id: str, session_id: str) -> dict | None:
    initialize_conversations()
    with _connect() as connection:
        row = connection.execute(
            "SELECT id, session_id, title, created_at, updated_at FROM conversations WHERE id = ? AND session_id = ?",
            (conversation_id, session_id),
        ).fetchone()
    return dict(row) if row else None


def list_conversations(session_id: str) -> list[dict]:
    initialize_conversations()
    with _connect() as connection:
        rows = connection.execute("""
            SELECT c.id, c.title, c.created_at, c.updated_at, COUNT(m.id) AS message_count
            FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id
            WHERE c.session_id = ? GROUP BY c.id ORDER BY c.updated_at DESC
        """, (session_id,)).fetchall()
    return [dict(row) for row in rows]


def save_message(conversation_id: str, role: str, content: str, sources: list[dict] | None = None) -> dict:
    if role not in {"user", "assistant"}:
        raise ValueError("Message role must be user or assistant.")
    if len(content) > 20000:
        raise ValueError("Message content exceeds the 20000-character limit.")
    initialize_conversations()
    item = {
        "id": str(uuid4()), "conversation_id": conversation_id, "role": role,
        "content": content, "sources": sources or [], "created_at": _now(),
    }
    with _connect() as connection:
        row = connection.execute("SELECT title FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if row is None:
            raise ValueError("Conversation not found.")
        connection.execute(
            "INSERT INTO messages (id, conversation_id, role, content, sources_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (item["id"], conversation_id, role, content, json.dumps(item["sources"], ensure_ascii=False), item["created_at"]),
        )
        if role == "user" and row["title"] == "新对话":
            title = content.strip().replace("\n", " ")[:60] or "新对话"
            connection.execute("UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?", (title, item["created_at"], conversation_id))
        else:
            connection.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (item["created_at"], conversation_id))
    return item


def list_messages(conversation_id: str) -> list[dict]:
    initialize_conversations()
    with _connect() as connection:
        rows = connection.execute(
            "SELECT id, conversation_id, role, content, sources_json, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at, rowid",
            (conversation_id,),
        ).fetchall()
    messages = []
    for row in rows:
        item = dict(row)
        try:
            item["sources"] = json.loads(item.pop("sources_json") or "[]")
        except (TypeError, ValueError):
            item.pop("sources_json", None)
            item["sources"] = []
        messages.append(item)
    return messages


def recent_history(conversation_id: str, limit: int = 8) -> list[dict]:
    initialize_conversations()
    limit = max(0, min(limit, 20))
    if limit == 0:
        return []
    with _connect() as connection:
        rows = connection.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def delete_conversation(conversation_id: str, session_id: str) -> bool:
    initialize_conversations()
    with _connect() as connection:
        row = connection.execute(
            "SELECT id FROM conversations WHERE id = ? AND session_id = ?",
            (conversation_id, session_id),
        ).fetchone()
        if row is None:
            return False
        connection.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        connection.execute("DELETE FROM conversations WHERE id = ? AND session_id = ?", (conversation_id, session_id))
    return True


def cleanup_session_conversations(session_ids: list[str]) -> int:
    if not session_ids:
        return 0
    initialize_conversations()
    placeholders = ",".join("?" for _ in session_ids)
    with _connect() as connection:
        connection.execute(
            f"DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE session_id IN ({placeholders}))",
            session_ids,
        )
        cursor = connection.execute(
            f"DELETE FROM conversations WHERE session_id IN ({placeholders})", session_ids
        )
    return cursor.rowcount
