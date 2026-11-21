import asyncio

from app.services import document_service as service


def seed_document(connection, document_id, session_id, filename, content):
    connection.execute(
        "INSERT INTO documents (id, filename, content_type, size, status, extracted_text, created_at, session_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (document_id, filename, "text/plain", len(content), "ready", content, "2026-01-01T00:00:00+00:00", session_id),
    )
    connection.execute(
        "INSERT INTO document_chunks (id, document_id, chunk_index, content, embedding, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (f"chunk-{document_id}", document_id, 0, content, None, "2026-01-01T00:00:00+00:00"),
    )


def test_documents_and_retrieval_are_isolated_by_session(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(service, "DB_PATH", tmp_path / "knowledge.db")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    service.initialize_storage()
    with service._connect() as connection:
        seed_document(connection, "doc-a", "session-a", "a.txt", "annual leave policy")
        seed_document(connection, "doc-b", "session-b", "b.txt", "annual leave secret")

    assert [item["id"] for item in service.list_documents("session-a")] == ["doc-a"]
    assert service.get_document_text("doc-b", "session-a") is None
    results = asyncio.run(service.search_chunks("annual leave", session_id="session-a"))
    assert results["results"]
    assert {item["document_id"] for item in results["results"]} == {"doc-a"}


def test_legacy_documents_without_session_are_not_visible(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(service, "DB_PATH", tmp_path / "knowledge.db")
    service.initialize_storage()
    with service._connect() as connection:
        seed_document(connection, "legacy", None, "legacy.txt", "old private content")
    assert service.list_documents("new-session") == []
    assert service.get_document_text("legacy", "new-session") is None
