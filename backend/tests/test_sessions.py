from datetime import datetime, timedelta, timezone

from app.services.session_service import create_session, get_session, cleanup_expired_sessions, _connect


def test_session_token_is_hashed_and_validated(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    created = create_session()
    assert created["token"]
    assert get_session(created["token"])["id"] == created["session_id"]
    with _connect() as connection:
        stored = connection.execute("SELECT token_hash FROM sessions").fetchone()["token_hash"]
    assert stored != created["token"]


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
