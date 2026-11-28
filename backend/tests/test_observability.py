from fastapi.testclient import TestClient

from app import main
from app.services import conversation_service, document_service, observability_service, session_service
from app.services.session_service import create_session


def _configure_storage(tmp_path, monkeypatch):
    db_path = tmp_path / "knowledge.db"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(session_service, "_db_path", lambda: db_path)
    monkeypatch.setattr(conversation_service, "_db_path", lambda: db_path)
    monkeypatch.setattr(observability_service, "_db_path", lambda: db_path)
    monkeypatch.setattr(document_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(document_service, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(document_service, "DB_PATH", db_path)
    document_service.initialize_storage()
    session_service.initialize_sessions()
    conversation_service.initialize_conversations()
    observability_service.initialize_traces()


def _headers(session):
    return {"X-Session-Token": session["token"]}


def test_trace_storage_is_session_scoped_and_excludes_content(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    owner = create_session()
    other = create_session()
    trace_id = observability_service.new_trace_id()

    observability_service.record_trace(
        trace_id=trace_id,
        session_id=owner["session_id"],
        endpoint="conversation_stream",
        status="success",
        total_duration_ms=123.4,
        requested_mode="hybrid",
        effective_mode="keyword_fallback",
        fallback_reason="embedding unavailable",
        reranker_status="not_requested",
        retrieved_chunks=[{
            "chunk_id": "chunk-1",
            "document_id": "doc-1",
            "filename": "policy.txt",
            "chunk_index": 2,
            "score": 0.91,
            "content": "PRIVATE CHUNK TEXT MUST NOT BE STORED",
        }],
        input_chars=8,
        output_chars=42,
    )

    trace = observability_service.get_trace(trace_id, owner["session_id"])
    assert trace is not None
    assert trace["effective_mode"] == "keyword_fallback"
    assert trace["retrieved_chunks"][0]["chunk_id"] == "chunk-1"
    assert "content" not in trace["retrieved_chunks"][0]
    assert observability_service.get_trace(trace_id, other["session_id"]) is None
    assert observability_service.list_traces(other["session_id"]) == []


def test_trace_api_enforces_session_ownership(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    owner = create_session()
    visitor = create_session()
    trace_id = observability_service.new_trace_id()
    observability_service.record_trace(
        trace_id=trace_id,
        session_id=owner["session_id"],
        endpoint="chat",
        status="no_answer",
        total_duration_ms=18,
        input_chars=12,
    )

    with TestClient(main.app) as client:
        own_list = client.get("/traces", headers=_headers(owner))
        assert own_list.status_code == 200
        assert own_list.json()[0]["trace_id"] == trace_id
        assert client.get(f"/traces/{trace_id}", headers=_headers(owner)).status_code == 200
        assert client.get(f"/traces/{trace_id}", headers=_headers(visitor)).status_code == 404
        assert client.get("/traces", headers=_headers(visitor)).json() == []


def test_trace_cleanup_removes_expired_session_records(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    owner = create_session()
    observability_service.record_trace(
        trace_id=observability_service.new_trace_id(),
        session_id=owner["session_id"],
        endpoint="chat",
        status="success",
        total_duration_ms=10,
    )

    assert observability_service.cleanup_session_traces([owner["session_id"]]) == 1
    assert observability_service.list_traces(owner["session_id"]) == []
