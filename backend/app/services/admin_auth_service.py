from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.rate_limit_service import InMemoryRateLimiter

SESSION_HOURS = 8
_login_limiter = InMemoryRateLimiter(limit=5, window_seconds=900, max_keys=5000)


def _db_path() -> Path:
    data_dir = Path(os.getenv("DATA_DIR", str(Path(__file__).resolve().parents[2] / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "knowledge.db"


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_db_path(), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def initialize_admin_auth() -> None:
    with _connect() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS admin_sessions (
                token_hash TEXT PRIMARY KEY,
                csrf_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS admin_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                client_ip TEXT,
                created_at TEXT NOT NULL
            )
        """)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit_logs(created_at DESC)")


def _audit(action: str, client_ip: str | None) -> None:
    initialize_admin_auth()
    safe_ip = (client_ip or "unknown")[:64]
    with _connect() as connection:
        connection.execute(
            "INSERT INTO admin_audit_logs(action, client_ip, created_at) VALUES (?, ?, ?)",
            (action[:64], safe_ip, _now().isoformat()),
        )


def authenticate_admin(password: str, client_ip: str | None) -> dict | None:
    initialize_admin_auth()
    key = client_ip or "unknown"
    if not _login_limiter.allow(key):
        _audit("login_rate_limited", client_ip)
        return None
    configured = os.getenv("ADMIN_PASSWORD", "")
    if len(configured) < 16 or not secrets.compare_digest(_hash(password), _hash(configured)):
        _audit("login_failed", client_ip)
        return None
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    now = _now()
    expires = now + timedelta(hours=SESSION_HOURS)
    with _connect() as connection:
        connection.execute(
            "INSERT INTO admin_sessions(token_hash, csrf_hash, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (_hash(token), _hash(csrf), now.isoformat(), expires.isoformat()),
        )
    _audit("login_succeeded", client_ip)
    return {"token": token, "csrf_token": csrf, "expires_at": expires.isoformat()}


def validate_admin_session(token: str | None, csrf_token: str | None = None) -> bool:
    if not token or len(token) > 256:
        return False
    initialize_admin_auth()
    now = _now().isoformat()
    with _connect() as connection:
        row = connection.execute(
            "SELECT csrf_hash, expires_at FROM admin_sessions WHERE token_hash = ?",
            (_hash(token),),
        ).fetchone()
    if row is None or row["expires_at"] <= now:
        return False
    if csrf_token is None:
        return False
    return secrets.compare_digest(row["csrf_hash"], _hash(csrf_token))


def revoke_admin_session(token: str | None, client_ip: str | None) -> None:
    if token:
        initialize_admin_auth()
        with _connect() as connection:
            connection.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (_hash(token),))
    _audit("logout", client_ip)


def record_admin_access(action: str, client_ip: str | None) -> None:
    _audit(action, client_ip)
