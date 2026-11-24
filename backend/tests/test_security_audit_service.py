import json
import logging

from app.services.security_audit_service import audit_security_event


def test_audit_event_is_structured_and_redacts_control_characters(caplog):
    with caplog.at_level(logging.WARNING, logger="security.audit"):
        audit_security_event(
            "document_access_denied",
            session_id="session-1",
            client_ip="127.0.0.1",
            resource_id="doc-1" + chr(10) + "forged_event",
            reason="not_found" + chr(13) + chr(10) + "forged",
        )

    records = [record for record in caplog.records if "security_audit " in record.message]
    assert len(records) == 1
    payload = json.loads(records[0].message.split("security_audit ", 1)[1])
    assert payload["event"] == "document_access_denied"
    assert chr(10) not in payload["resource_id"]
    assert chr(13) not in payload["reason"]
    assert "forged_event" in payload["resource_id"]


def test_audit_event_does_not_accept_or_log_credentials(caplog):
    secret_token = "very-secret-session-token"
    secret_key = "provider-api-key"
    with caplog.at_level(logging.WARNING, logger="security.audit"):
        audit_security_event("session_created", session_id="safe-session")

    rendered = " ".join(record.message for record in caplog.records)
    assert secret_token not in rendered
    assert secret_key not in rendered
    assert "safe-session" in rendered


def test_audit_failure_does_not_raise(monkeypatch):
    from app.services import security_audit_service

    def fail(*args, **kwargs):
        raise RuntimeError("logger unavailable")

    monkeypatch.setattr(security_audit_service.logger, "warning", fail)
    audit_security_event("authentication_failed", reason="invalid")
