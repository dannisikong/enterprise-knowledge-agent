import asyncio

from fastapi.testclient import TestClient

from app import main
from app.services import document_service
from app.services import session_service
from app.services.session_service import create_session


def _seed_document(document_id, session_id, content):
    with document_service._connect() as connection:
        connection.execute(
            "INSERT INTO documents (id, filename, content_type, size, status, extracted_text, created_at, session_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (document_id, f"{document_id}.txt", "text/plain", len(content), "ready", content, "2026-01-01T00:00:00+00:00", session_id),
        )
        connection.execute(
            "INSERT INTO document_chunks (id, document_id, chunk_index, content, embedding, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (f"chunk-{document_id}", document_id, 0, content, None, "2026-01-01T00:00:00+00:00"),
        )


def _configure_test_storage(tmp_path, monkeypatch):
    db_path = tmp_path / "knowledge.db"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(session_service, "_db_path", lambda: db_path)
    monkeypatch.setattr(document_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(document_service, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(document_service, "DB_PATH", db_path)
    document_service.initialize_storage()
    session_service.initialize_sessions()


def test_api_requires_valid_session_token(tmp_path, monkeypatch):
    _configure_test_storage(tmp_path, monkeypatch)
    with TestClient(main.app) as client:
        assert client.get("/documents").status_code == 401
        assert client.get("/documents", headers={"X-Session-Token": "invalid-token"}).status_code == 401


def test_api_cannot_read_another_sessions_document(tmp_path, monkeypatch):
    _configure_test_storage(tmp_path, monkeypatch)
    owner = create_session()
    visitor = create_session()
    _seed_document("private-doc", owner["session_id"], "private company policy")

    with TestClient(main.app) as client:
        response = client.get(
            "/documents/private-doc/text",
            headers={"X-Session-Token": visitor["token"]},
        )
        own_response = client.get(
            "/documents/private-doc/text",
            headers={"X-Session-Token": owner["token"]},
        )

    assert response.status_code == 404
    assert own_response.status_code == 200
    assert own_response.json()["extracted_text"] == "private company policy"


def test_api_reindex_only_updates_current_sessions_documents(tmp_path, monkeypatch):
    _configure_test_storage(tmp_path, monkeypatch)
    owner = create_session()
    other = create_session()
    _seed_document("owner-doc", owner["session_id"], "owner content")
    _seed_document("other-doc", other["session_id"], "other content")
    monkeypatch.setattr(document_service, "embeddings_configured", lambda: True)

    async def fake_embeddings(texts):
        return [[0.1, 0.2] for _ in texts]

    monkeypatch.setattr(document_service, "create_embeddings", fake_embeddings)
    with TestClient(main.app) as client:
        response = client.post(
            "/documents/reindex",
            headers={"X-Session-Token": owner["token"]},
        )

    assert response.status_code == 200
    assert response.json()["total_documents"] == 1
    with document_service._connect() as connection:
        owner_vector = connection.execute(
            "SELECT embedding FROM document_chunks WHERE document_id = 'owner-doc'"
        ).fetchone()["embedding"]
        other_vector = connection.execute(
            "SELECT embedding FROM document_chunks WHERE document_id = 'other-doc'"
        ).fetchone()["embedding"]
    assert owner_vector is not None
    assert other_vector is None



def test_api_deletes_only_owned_document_and_cleans_storage(tmp_path, monkeypatch):
    _configure_test_storage(tmp_path, monkeypatch)
    owner = create_session()
    visitor = create_session()
    _seed_document("owned-doc", owner["session_id"], "owned content")
    document_service.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_file = document_service.UPLOAD_DIR / "owned-doc.txt"
    stored_file.write_text("source", encoding="utf-8")
    with TestClient(main.app) as client:
        denied = client.delete("/documents/owned-doc", headers={"X-Session-Token": visitor["token"]})
        deleted = client.delete("/documents/owned-doc", headers={"X-Session-Token": owner["token"]})
    assert denied.status_code == 404
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert not stored_file.exists()
    with document_service._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM documents WHERE id = 'owned-doc'").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM document_chunks WHERE document_id = 'owned-doc'").fetchone()[0] == 0


def test_api_reindexes_only_owned_document(tmp_path, monkeypatch):
    _configure_test_storage(tmp_path, monkeypatch)
    owner = create_session()
    visitor = create_session()
    _seed_document("owned-doc", owner["session_id"], "owned content")
    monkeypatch.setattr(document_service, "embeddings_configured", lambda: True)

    async def fake_embeddings(texts):
        return [[0.1, 0.2] for _ in texts]

    monkeypatch.setattr(document_service, "create_embeddings", fake_embeddings)
    with TestClient(main.app) as client:
        denied = client.post("/documents/owned-doc/reindex", headers={"X-Session-Token": visitor["token"]})
        indexed = client.post("/documents/owned-doc/reindex", headers={"X-Session-Token": owner["token"]})
    assert denied.status_code == 404
    assert indexed.status_code == 200
    assert indexed.json()["status"] == "indexed"
    assert indexed.json()["embedded_chunk_count"] == 1
