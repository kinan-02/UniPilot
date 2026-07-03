"""MAS health endpoint tests."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_mas_service_name() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "mas"
    assert body["status"] == "ok"
