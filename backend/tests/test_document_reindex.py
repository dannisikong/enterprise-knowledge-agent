import asyncio
import json

from app.services import document_service as service


def seed_document(connection, document_id, session_id, filename, chunks):
    connection.execute(
        "INSERT INTO documents (id, filename, content_type, size, status, extracted_text, created_at, session_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (document_id, filename, "text/plain", sum(map(len, chunks)), "ready", " ".join(chunks), "2026-01-01T00:00:00+00:00", session_id),
    )
    connection.executemany(
        "INSERT INTO document_chunks (id, document_id, chunk_index, content, embedding, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        [(f"{document_id}-{index}", document_id, index, chunk, None, "2026-01-01T00:00:00+00:00") for index, chunk in enumerate(chunks)],
    )


def setup_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(service, "DB_PATH", tmp_path / "knowledge.db")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    service.initialize_storage()


def test_reindex_only_updates_documents_in_current_session(tmp_path, monkeypatch):
    setup_storage(tmp_path, monkeypatch)
    with service._connect() as connection:
        seed_document(connection, "doc-a", "session-a", "a.txt", ["alpha", "beta"])
        seed_document(connection, "doc-b", "session-b", "b.txt", ["private"])

    async def fake_embeddings(texts):
        return [[float(len(text)), 1.0] for text in texts]

    monkeypatch.setattr(service, "create_embeddings", fake_embeddings)
    result = asyncio.run(service.reindex_documents("session-a"))

    assert result["indexed_documents"] == 1
    assert result["failed_documents"] == 0
    assert result["indexed"][0]["embedded_chunk_count"] == 2
    with service._connect() as connection:
        own = connection.execute("SELECT embedding FROM document_chunks WHERE document_id = 'doc-a'").fetchall()
        other = connection.execute("SELECT embedding FROM document_chunks WHERE document_id = 'doc-b'").fetchone()
    assert all(row["embedding"] for row in own)
    assert other["embedding"] is None


def test_reindex_failure_preserves_existing_vectors(tmp_path, monkeypatch):
    setup_storage(tmp_path, monkeypatch)
    with service._connect() as connection:
        seed_document(connection, "doc-a", "session-a", "a.txt", ["alpha"])
        connection.execute(
            "UPDATE document_chunks SET embedding = ? WHERE document_id = ?",
            (json.dumps([0.1, 0.2]), "doc-a"),
        )

    async def failed_embeddings(texts):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(service, "create_embeddings", failed_embeddings)
    result = asyncio.run(service.reindex_documents("session-a"))

    assert result["failed_documents"] == 1
    with service._connect() as connection:
        row = connection.execute("SELECT embedding FROM document_chunks WHERE document_id = 'doc-a'").fetchone()
    assert json.loads(row["embedding"]) == [0.1, 0.2]



def test_single_document_reindex_updates_only_requested_document(tmp_path, monkeypatch):
    setup_storage(tmp_path, monkeypatch)
    with service._connect() as connection:
        seed_document(connection, "doc-a", "session-a", "a.txt", ["alpha", "beta"])
        seed_document(connection, "doc-b", "session-a", "b.txt", ["gamma"])
        connection.execute(
            "UPDATE document_chunks SET embedding = ? WHERE document_id = ?",
            (json.dumps([0.3, 0.4]), "doc-b"),
        )

    async def fake_embeddings(texts):
        return [[0.5, 0.6] for _ in texts]

    monkeypatch.setattr(service, "create_embeddings", fake_embeddings)
    result = asyncio.run(service.reindex_document("doc-a", "session-a"))
    assert result["status"] == "indexed"
    assert result["embedded_chunk_count"] == 2
    with service._connect() as connection:
        target = connection.execute("SELECT embedding FROM document_chunks WHERE document_id = 'doc-a'").fetchall()
        untouched = connection.execute("SELECT embedding FROM document_chunks WHERE document_id = 'doc-b'").fetchone()
    assert all(json.loads(row["embedding"]) == [0.5, 0.6] for row in target)
    assert json.loads(untouched["embedding"]) == [0.3, 0.4]


def test_single_document_reindex_failure_preserves_existing_vectors(tmp_path, monkeypatch):
    setup_storage(tmp_path, monkeypatch)
    with service._connect() as connection:
        seed_document(connection, "doc-a", "session-a", "a.txt", ["alpha"])
        connection.execute("UPDATE document_chunks SET embedding = ? WHERE document_id = ?", (json.dumps([0.1, 0.2]), "doc-a"))

    async def failed_embeddings(texts):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(service, "create_embeddings", failed_embeddings)
    result = asyncio.run(service.reindex_document("doc-a", "session-a"))
    assert result["status"] == "failed"
    with service._connect() as connection:
        row = connection.execute("SELECT embedding FROM document_chunks WHERE document_id = 'doc-a'").fetchone()
    assert json.loads(row["embedding"]) == [0.1, 0.2]


def test_delete_document_removes_chunks_and_source_file(tmp_path, monkeypatch):
    setup_storage(tmp_path, monkeypatch)
    service.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    source = service.UPLOAD_DIR / "doc-a.txt"
    source.write_text("source", encoding="utf-8")
    with service._connect() as connection:
        seed_document(connection, "doc-a", "session-a", "a.txt", ["alpha"])
    assert service.delete_document("doc-a", "session-a") is True
    assert not source.exists()
    with service._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM documents WHERE id = 'doc-a'").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM document_chunks WHERE document_id = 'doc-a'").fetchone()[0] == 0


def test_delete_document_rejects_other_session(tmp_path, monkeypatch):
    setup_storage(tmp_path, monkeypatch)
    with service._connect() as connection:
        seed_document(connection, "doc-a", "session-owner", "a.txt", ["alpha"])
    assert service.delete_document("doc-a", "session-other") is False
    with service._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM documents WHERE id = 'doc-a'").fetchone()[0] == 1
