from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.main import create_app
from backend.scripts.bootstrap_internal_alpha import bootstrap_internal_alpha


def test_production_configuration_fails_closed() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        model_api_key=None,
        database_url="sqlite:///temporary.db",
        allowed_hosts="*",
        rate_limit_enabled=False,
        trust_proxy_headers=False,
        log_format="text",
        app_version="local",
    )

    errors = settings.production_configuration_errors()

    assert "MODEL_API_KEY must be configured" in errors
    assert "DATABASE_URL must use persistent PostgreSQL" in errors
    assert "ALLOWED_HOSTS must be explicit" in errors
    assert "RATE_LIMIT_ENABLED must be true" in errors
    assert "TRUST_PROXY_HEADERS must be true behind the frontend proxy" in errors
    assert "LOG_FORMAT must be json" in errors
    assert "APP_VERSION must identify an immutable release" in errors


def test_valid_production_configuration_passes_without_connecting() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        app_version="release-2026-09-04.1",
        model_api_key="test-secret",
        database_url="postgresql+psycopg://user:pass@database/skyoffer",
        allowed_hosts="backend,skyoffer.example",
        rate_limit_enabled=True,
        trust_proxy_headers=True,
        log_format="json",
    )

    assert settings.production_configuration_errors() == []


def test_api_security_headers_and_request_size_limit() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            model_api_key="test",
            request_max_body_bytes=1024,
        )
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/profile-analysis",
            content="x" * 1025,
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"


def test_model_endpoint_rate_limit_returns_retry_after() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            model_api_key="test",
            rate_limit_enabled=True,
            rate_limit_requests=10,
            rate_limit_window_seconds=60,
        )
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        allowed = [
            client.post("/api/v1/profile-analysis", json={})
            for _ in range(10)
        ]
        limited = client.post("/api/v1/profile-analysis", json={})

    assert all(response.status_code == 422 for response in allowed)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert limited.headers["Retry-After"] == "60"
    assert limited.headers["X-Request-ID"].startswith("req_")


def test_internal_alpha_bootstrap_is_idempotent_and_ready(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        app_version="test-release",
        model_api_key="test",
        database_url=f"sqlite:///{tmp_path / 'production-like.sqlite3'}",
    )

    first = bootstrap_internal_alpha(settings)
    second = bootstrap_internal_alpha(settings)

    assert first["program_count"] == 20
    assert first["imported"] == 20
    assert second["imported"] == 0
    assert second["reused"] == 20

    engine = create_database_engine(settings.database_url)
    sessions = create_session_factory(engine)
    try:
        app = create_app(settings=settings, phase3_session_factory=sessions)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/v1/ready")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ready",
            "version": "test-release",
            "dataset_id": "dataset.internal_alpha.2027.v3",
            "program_count": 20,
        }
    finally:
        engine.dispose()
