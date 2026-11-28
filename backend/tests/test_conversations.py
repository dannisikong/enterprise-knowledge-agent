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

    async def fake_retrieve(request, session_id, history=None, summary=None, trace_context=None):
        if trace_context is not None:
            trace_context.update({
                "requested_mode": "hybrid",
                "effective_mode": "hybrid",
                "reranker_status": "not_requested",
                "retrieved_chunks": [source],
                "retrieval_duration_ms": 2.5,
            })
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
        assert "trace_id" in response.text
        traces = client.get("/traces", headers=_headers(owner)).json()
        assert len(traces) == 1
        trace_detail = client.get(f"/traces/{traces[0]['trace_id']}", headers=_headers(owner)).json()
        assert trace_detail["status"] == "success"
        assert trace_detail["question"] == "年假有几天？"
        assert trace_detail["answer"] == "根据员工手册，年假为五天。[1]"
        assert trace_detail["sources"] == [source]
        assert trace_detail["retrieved_chunks"][0]["chunk_id"] == "chunk-1"
        assert "content" not in trace_detail["retrieved_chunks"][0]
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


def test_summary_queue_preserves_recent_window_and_advances_incrementally(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    owner = create_session()
    conversation = conversation_service.create_conversation(owner["session_id"])
    for index in range(10):
        role = "user" if index % 2 == 0 else "assistant"
        conversation_service.save_message(conversation["id"], role, f"message-{index}")

    pending = conversation_service.messages_to_summarize(conversation["id"], keep_recent=6)
    assert [item["content"] for item in pending] == ["message-0", "message-1", "message-2", "message-3"]

    conversation_service.save_conversation_summary(conversation["id"], "摘要包含早期关键事实", pending[-1]["rowid"])
    assert conversation_service.get_conversation_memory(conversation["id"])["summary"] == "摘要包含早期关键事实"
    assert conversation_service.messages_to_summarize(conversation["id"], keep_recent=6) == []

    for index in range(10, 14):
        role = "user" if index % 2 == 0 else "assistant"
        conversation_service.save_message(conversation["id"], role, f"message-{index}")
    next_batch = conversation_service.messages_to_summarize(conversation["id"], keep_recent=6)
    assert [item["content"] for item in next_batch] == ["message-4", "message-5", "message-6", "message-7"]


def test_streaming_chat_builds_summary_and_keeps_recent_history(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    owner = create_session()
    source = {
        "id": 1, "chunk_id": "chunk-1", "document_id": "doc-1",
        "filename": "policy.txt", "chunk_index": 0, "content": "年假为五天。", "score": 0.9,
    }
    captured = {}

    async def fake_summarize(previous_summary, older_messages, config=None):
        captured["older"] = [item["content"] for item in older_messages]
        return "早期摘要：用户提到正式员工年假为15天。"

    async def fake_retrieve(request, session_id, history=None, summary=None, trace_context=None):
        captured["history"] = history
        captured["summary"] = summary
        return ([{"role": "system", "content": "test"}], [source])

    async def fake_stream(messages, config=None):
        yield "回答。"

    monkeypatch.setattr(main, "summarize_conversation", fake_summarize)
    monkeypatch.setattr(main, "llm_configured", lambda config=None: True)
    monkeypatch.setattr(main, "_retrieve_for_chat", fake_retrieve)
    monkeypatch.setattr(main, "stream_answer", fake_stream)

    with TestClient(main.app) as client:
        created = client.post("/conversations", headers=_headers(owner), json={})
        conversation_id = created.json()["id"]
        for index in range(8):
            role = "user" if index % 2 == 0 else "assistant"
            conversation_service.save_message(conversation_id, role, f"历史消息-{index}")
        response = client.post(
            f"/conversations/{conversation_id}/messages/stream",
            headers=_headers(owner),
            json={"query": "那第一种员工呢？"},
        )
        assert response.status_code == 200

    assert captured["older"] == ["历史消息-0", "历史消息-1"]
    assert len(captured["history"]) == 6
    assert captured["summary"] == "早期摘要：用户提到正式员工年假为15天。"
    assert conversation_service.get_conversation_memory(conversation_id)["summary"] == captured["summary"]


def test_summary_failure_does_not_block_chat(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    owner = create_session()
    source = {
        "id": 1, "chunk_id": "chunk-1", "document_id": "doc-1",
        "filename": "policy.txt", "chunk_index": 0, "content": "年假为五天。", "score": 0.9,
    }
    captured = {}

    async def fail_summary(previous_summary, older_messages, config=None):
        raise RuntimeError("summary provider unavailable")

    async def fake_retrieve(request, session_id, history=None, summary=None, trace_context=None):
        captured["summary"] = summary
        return ([{"role": "system", "content": "test"}], [source])

    async def fake_stream(messages, config=None):
        yield "正常回答。"

    monkeypatch.setattr(main, "summarize_conversation", fail_summary)
    monkeypatch.setattr(main, "llm_configured", lambda config=None: True)
    monkeypatch.setattr(main, "_retrieve_for_chat", fake_retrieve)
    monkeypatch.setattr(main, "stream_answer", fake_stream)

    with TestClient(main.app) as client:
        created = client.post("/conversations", headers=_headers(owner), json={})
        conversation_id = created.json()["id"]
        for index in range(8):
            role = "user" if index % 2 == 0 else "assistant"
            conversation_service.save_message(conversation_id, role, f"历史消息-{index}")
        response = client.post(
            f"/conversations/{conversation_id}/messages/stream",
            headers=_headers(owner),
            json={"query": "继续"},
        )

    assert response.status_code == 200
    assert "正常回答。" in response.text
    assert captured["summary"] == ""
