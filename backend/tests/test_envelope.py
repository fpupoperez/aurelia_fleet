"""Envelope shape that does not need a database."""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_validation_error_uses_the_envelope() -> None:
    application = create_app(Settings(seed_corpus=False, auth_required=False))
    with TestClient(application) as client:
        response = client.post(f"{application.state.settings.api_prefix}/answers", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["errors"][0]["code"] == 422
    assert "detail" not in body


def test_status_without_a_token() -> None:
    application = create_app(Settings(seed_corpus=False, auth_required=False))
    with TestClient(application) as client:
        response = client.get(f"{application.state.settings.api_prefix}/status")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"
