from datetime import datetime, timedelta, timezone
import asyncio

import pytest
from fastapi import HTTPException, Request

from app import main
from app.services.session_service import create_session, get_session, cleanup_expired_sessions, _connect
from app.services.rate_limit_service import InMemoryRateLimiter


def test_session_token_is_hashed_and_validated(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    created = create_session()
    assert created["token"]
    assert get_session(created["token"])["id"] == created["session_id"]
    with _connect() as connection:
        stored = connection.execute("SELECT token_hash FROM sessions").fetchone()["token_hash"]
    assert stored != created["token"]


def test_session_expiry_slides_forward_only_for_authenticated_access(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    created = create_session()
    with _connect() as connection:
        original_expiry = connection.execute(
            "SELECT expires_at FROM sessions WHERE id = ?", (created["session_id"],)
        ).fetchone()["expires_at"]

    session = get_session(created["token"], touch=False)
    assert session["expires_at"] == original_expiry
    refreshed = get_session(created["token"], touch=True)
    assert datetime.fromisoformat(refreshed["expires_at"]) > datetime.fromisoformat(original_expiry)


def test_expired_session_is_rejected_and_cleaned(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    created = create_session()
    with _connect() as connection:
        connection.execute(
            "UPDATE sessions SET expires_at = ? WHERE id = ?",
            ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), created["session_id"]),
        )
    assert get_session(created["token"]) is None
    assert cleanup_expired_sessions() == [created["session_id"]]


def _request_from(host: str) -> Request:
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/session",
        "raw_path": b"/session",
        "query_string": b"",
        "headers": [],
        "client": (host, 12345),
        "server": ("testserver", 80),
    })


def test_session_creation_is_rate_limited_per_client(monkeypatch):
    limiter = InMemoryRateLimiter(limit=1, window_seconds=60)
    monkeypatch.setattr(main, "session_creation_limiter", limiter)
    monkeypatch.setattr(
        main,
        "create_session",
        lambda: {"session_id": "session-test", "token": "token-test", "expires_at": "2030-01-01T00:00:00+00:00"},
    )

    first = asyncio.run(main.new_session(_request_from("198.51.100.10")))
    assert first["session_id"] == "session-test"

    with pytest.raises(HTTPException) as error:
        asyncio.run(main.new_session(_request_from("198.51.100.10")))
    assert error.value.status_code == 429

    other_client = asyncio.run(main.new_session(_request_from("198.51.100.11")))
    assert other_client["session_id"] == "session-test"


def test_session_creation_does_not_trust_forwarded_for(monkeypatch):
    limiter = InMemoryRateLimiter(limit=1, window_seconds=60)
    monkeypatch.setattr(main, "session_creation_limiter", limiter)
    monkeypatch.setattr(
        main,
        "create_session",
        lambda: {"session_id": "session-test", "token": "token-test", "expires_at": "2030-01-01T00:00:00+00:00"},
    )

    request = _request_from("198.51.100.10")
    request.scope["headers"] = [(b"x-forwarded-for", b"203.0.113.99")]
    asyncio.run(main.new_session(request))

    with pytest.raises(HTTPException) as error:
        asyncio.run(main.new_session(_request_from("198.51.100.10")))
    assert error.value.status_code == 429
