import pytest

from app.services import rate_limit_service


def test_limiter_enforces_window_and_expires_events(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(rate_limit_service.time, "monotonic", lambda: now[0])
    limiter = rate_limit_service.InMemoryRateLimiter(limit=2, window_seconds=10)

    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is False

    now[0] = 111.0
    assert limiter.allow("client-a") is True


def test_limiter_keeps_client_keys_independent(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(rate_limit_service.time, "monotonic", lambda: now[0])
    limiter = rate_limit_service.InMemoryRateLimiter(limit=1, window_seconds=60)

    assert limiter.allow("client-a") is True
    assert limiter.allow("client-b") is True
    assert limiter.allow("client-a") is False


def test_limiter_bounds_key_storage(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(rate_limit_service.time, "monotonic", lambda: now[0])
    limiter = rate_limit_service.InMemoryRateLimiter(limit=5, window_seconds=60, max_keys=2)

    assert limiter.allow("client-a") is True
    assert limiter.allow("client-b") is True
    assert limiter.allow("client-c") is True
    assert len(limiter._events) == 2
    assert "client-a" not in limiter._events


def test_limiter_periodically_removes_expired_keys(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(rate_limit_service.time, "monotonic", lambda: now[0])
    limiter = rate_limit_service.InMemoryRateLimiter(limit=2, window_seconds=10, max_keys=5)

    assert limiter.allow("client-a") is True
    assert limiter.allow("client-b") is True
    now[0] = 111.0

    assert limiter.allow("client-c") is True
    assert set(limiter._events) == {"client-c"}


@pytest.mark.parametrize("key", ["", None, "x" * 257])
def test_limiter_rejects_invalid_or_oversized_keys(key):
    limiter = rate_limit_service.InMemoryRateLimiter()
    assert limiter.allow(key) is False


def test_limiter_rejects_non_positive_configuration():
    with pytest.raises(ValueError):
        rate_limit_service.InMemoryRateLimiter(limit=0)
