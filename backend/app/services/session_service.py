from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

SESSION_TTL_HOURS = 24


def _db_path() -> Path:
    data_dir = Path(os.getenv("DATA_DIR", str(Path(__file__).resolve().parents[2] / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "knowledge.db"


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_db_path(), timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_sessions() -> None:
    with _connect() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)"
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def create_session() -> dict[str, str]:
    initialize_sessions()
    token = secrets.token_urlsafe(32)
    now = _now()
    session_id = str(uuid4())
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = now + timedelta(hours=SESSION_TTL_HOURS)
    with _connect() as connection:
        connection.execute(
            "INSERT INTO sessions (id, token_hash, created_at, last_seen_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, token_hash, _iso(now), _iso(now), _iso(expires_at)),
        )
    return {"session_id": session_id, "token": token, "expires_at": _iso(expires_at)}


def get_session(token: str | None, *, touch: bool = True) -> dict | None:
    if not token or len(token) > 256:
        return None
    initialize_sessions()
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = _now()
    with _connect() as connection:
        row = connection.execute(
            "SELECT id, created_at, last_seen_at, expires_at FROM sessions WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        try:
            expires_at = datetime.fromisoformat(row["expires_at"])
        except (TypeError, ValueError):
            return None
        if expires_at <= now:
            connection.execute("DELETE FROM sessions WHERE id = ?", (row["id"],))
            return None
        if touch:
            new_expiry = now + timedelta(hours=SESSION_TTL_HOURS)
            connection.execute(
                "UPDATE sessions SET last_seen_at = ?, expires_at = ? WHERE id = ?",
                (_iso(now), _iso(new_expiry), row["id"]),
            )
            return {**dict(row), "expires_at": _iso(new_expiry), "id": row["id"]}
        return dict(row)


def cleanup_expired_sessions(batch_size: int = 100) -> list[str]:
    initialize_sessions()
    now = _iso(_now())
    with _connect() as connection:
        rows = connection.execute(
            "SELECT id FROM sessions WHERE expires_at <= ? ORDER BY expires_at LIMIT ?",
            (now, max(1, min(batch_size, 1000))),
        ).fetchall()
        ids = [row["id"] for row in rows]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            connection.execute(f"DELETE FROM sessions WHERE id IN ({placeholders})", ids)
    return ids
