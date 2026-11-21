from datetime import datetime, timedelta, timezone

from app.services import document_service
from app.services.session_service import (
    _connect as session_connect,
    create_session,
    cleanup_expired_sessions,
    delete_sessions,
    get_session,
)


def test_expired_session_cleanup_removes_database_rows_and_upload_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(document_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(document_service, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(document_service, "DB_PATH", tmp_path / "knowledge.db")
    document_service.initialize_storage()
    session = create_session()
    document_id = "expired-document"
    document_service.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    upload = document_service.UPLOAD_DIR / f"{document_id}.txt"
    upload.write_text("expired content", encoding="utf-8")

    with document_service._connect() as connection:
        connection.execute(
            "INSERT INTO documents (id, filename, content_type, size, status, extracted_text, created_at, session_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (document_id, "expired.txt", "text/plain", 15, "ready", "expired content", "2026-01-01T00:00:00+00:00", session["session_id"]),
        )
        connection.execute(
            "INSERT INTO document_chunks (id, document_id, chunk_index, content, embedding, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("expired-chunk", document_id, 0, "expired content", None, "2026-01-01T00:00:00+00:00"),
        )
    with session_connect() as connection:
        connection.execute(
            "UPDATE sessions SET expires_at = ? WHERE id = ?",
            ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), session["session_id"]),
        )

    expired_ids = cleanup_expired_sessions()
    assert expired_ids == [session["session_id"]]
    assert document_service.cleanup_session_documents(expired_ids) == 1
    delete_sessions(expired_ids)

    assert not upload.exists()
    assert document_service.list_documents(session["session_id"]) == []
    assert get_session(session["token"]) is None
    assert document_service.cleanup_session_documents(expired_ids) == 0
