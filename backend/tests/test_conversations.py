from fastapi.testclient import TestClient

from app import main
from app.services import conversation_service, document_service, session_service
from app.services.session_service import create_session


def _configure_storage(tmp_path, monkeypatch):
    db_path = tmp_path / "knowledge.db"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(session_service, "_db_path", lambda: db_path)
    monkeypatch.setattr(document_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(document_service, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(document_service, "DB_PATH", db_path)
    monkeypatch.setattr(conversation_service, "_db_path", lambda: db_path)
    document_service.initialize_storage()
    session_service.initialize_sessions()
    conversation_service.initialize_conversations()


def _headers(session):
    return {"X-Session-Token": session["token"]}


def test_conversation_crud_and_session_isolation(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    owner = create_session()
    visitor = create_session()

    with TestClient(main.app) as client:
        created = client.post("/conversations", headers=_headers(owner), json={})
        assert created.status_code == 201
        conversation_id = created.json()["id"]

        listed = client.get("/conversations", headers=_headers(owner))
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == conversation_id

        assert client.get(
            f"/conversations/{conversation_id}/messages", headers=_headers(visitor)
        ).status_code == 404
        assert client.delete(
            f"/conversations/{conversation_id}", headers=_headers(visitor)
        ).status_code == 404

        deleted = client.delete(
            f"/conversations/{conversation_id}", headers=_headers(owner)
        )
        assert deleted.status_code == 200
        assert deleted.json() == {"deleted": True}
        assert client.get(
            f"/conversations/{conversation_id}/messages", headers=_headers(owner)
        ).status_code == 404


def test_streaming_chat_persists_messages_and_sources(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    owner = create_session()
    source = {
        "id": 1, "chunk_id": "chunk-1", "document_id": "doc-1",
        "filename": "policy.txt", "chunk_index": 0, "content": "年假为五天。", "score": 0.9,
    }

    async def fake_retrieve(request, session_id, history=None):
        return ([{"role": "system", "content": "test"}], [source])

    async def fake_stream(messages, config=None):
        yield "根据员工手册，"
        yield "年假为五天。[1]"

    monkeypatch.setattr(main, "_retrieve_for_chat", fake_retrieve)
    monkeypatch.setattr(main, "stream_answer", fake_stream)

    with TestClient(main.app) as client:
        created = client.post("/conversations", headers=_headers(owner), json={})
        conversation_id = created.json()["id"]
        response = client.post(
            f"/conversations/{conversation_id}/messages/stream",
            headers=_headers(owner),
            json={"query": "年假有几天？"},
        )
        assert response.status_code == 200
        assert "event: token" in response.text
        assert "assistant_message_id" in response.text
        history = client.get(
            f"/conversations/{conversation_id}/messages", headers=_headers(owner)
        ).json()["messages"]

    assert [item["role"] for item in history] == ["user", "assistant"]
    assert history[0]["content"] == "年假有几天？"
    assert history[1]["content"] == "根据员工手册，年假为五天。[1]"
    assert history[1]["sources"] == [source]


def test_expired_session_cleanup_removes_conversations(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    owner = create_session()
    conversation = conversation_service.create_conversation(owner["session_id"])
    conversation_service.save_message(conversation["id"], "user", "test question")

    removed = conversation_service.cleanup_session_conversations([owner["session_id"]])
    assert removed == 1
    assert conversation_service.get_conversation(conversation["id"], owner["session_id"]) is None
    assert conversation_service.list_messages(conversation["id"]) == []
