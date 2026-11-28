from fastapi.testclient import TestClient

from app import main
from app.services import admin_auth_service, admin_observability_service, observability_service


def _configure_db(tmp_path, monkeypatch):
    db_path = tmp_path / "knowledge.db"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-password-strong")
    monkeypatch.setenv("ADMIN_COOKIE_SECURE", "false")
    monkeypatch.setattr(admin_auth_service, "_db_path", lambda: db_path)
    monkeypatch.setattr(observability_service, "_db_path", lambda: db_path)
    observability_service.initialize_traces()
    admin_auth_service.initialize_admin_auth()


def _login(client):
    response = client.post("/admin/auth/login", json={"password": "test-admin-password-strong"})
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_admin_routes_require_authentication_and_csrf(tmp_path, monkeypatch):
    _configure_db(tmp_path, monkeypatch)
    with TestClient(main.app) as client:
        assert client.get("/admin/observability/dashboard").status_code == 401
        csrf = _login(client)
        assert client.get("/admin/auth/me").status_code == 401
        assert client.get(
            "/admin/auth/me", headers={"X-Admin-CSRF": csrf}
        ).json() == {"authenticated": True}
        assert client.post(
            "/admin/auth/logout", headers={"X-Admin-CSRF": "wrong"}
        ).status_code == 401
        assert client.post(
            "/admin/auth/logout", headers={"X-Admin-CSRF": csrf}
        ).json() == {"logged_out": True}
        assert client.get(
            "/admin/observability/dashboard",
            headers={"X-Admin-CSRF": csrf},
        ).status_code == 401


def test_admin_dashboard_and_global_trace_queries(tmp_path, monkeypatch):
    _configure_db(tmp_path, monkeypatch)
    trace_id = observability_service.new_trace_id()
    observability_service.record_trace(
        trace_id=trace_id,
        session_id="session-a",
        endpoint="conversation_stream",
        status="success",
        total_duration_ms=120,
        retrieval_duration_ms=20,
        model_duration_ms=90,
        question="How many vacation days?",
        answer="The policy provides 15 days.",
        sources=[{"filename": "leave-policy.pdf", "chunk_index": 1}],
    )
    observability_service.submit_feedback(trace_id, "session-a", "correct", "verified")

    with TestClient(main.app) as client:
        csrf = _login(client)
        headers = {"X-Admin-CSRF": csrf}
        dashboard = client.get("/admin/observability/dashboard?days=7", headers=headers)
        assert dashboard.status_code == 200
        metrics = dashboard.json()
        assert metrics["total_requests"] == 1
        assert metrics["success_rate"] == 1
        assert metrics["avg_total_ms"] == 120
        assert metrics["feedback_breakdown"] == [{"rating": "correct", "count": 1}]

        listing = client.get(
            "/admin/observability/traces?status=success&query=vacation",
            headers=headers,
        )
        assert listing.status_code == 200
        assert listing.json()["total"] == 1
        assert listing.json()["items"][0]["trace_id"] == trace_id
        assert listing.json()["items"][0]["feedback_rating"] == "correct"

        detail = client.get(f"/admin/observability/traces/{trace_id}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["question"] == "How many vacation days?"
        assert detail.json()["answer"] == "The policy provides 15 days."
        assert detail.json()["feedback"][0]["rating"] == "correct"
        assert client.get(
            "/admin/observability/traces/not-found", headers=headers
        ).status_code == 404


def test_admin_login_fails_when_password_is_not_configured(tmp_path, monkeypatch):
    _configure_db(tmp_path, monkeypatch)
    monkeypatch.delenv("ADMIN_PASSWORD")
    with TestClient(main.app) as client:
        response = client.post("/admin/auth/login", json={"password": "anything"})
        assert response.status_code == 401
