"""FastAPI route tests for the AI service."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_service_payload():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "ai"
    assert body["status"] == "ok"
    assert "academic_graph" in body


def test_retrieve_requires_intent():
    response = client.post("/retrieve", json={})
    assert response.status_code == 400
    assert response.json()["success"] is False


def test_advise_requires_question():
    response = client.post("/advise", json={})
    assert response.status_code == 400
    assert response.json()["success"] is False


def test_infer_returns_202_stub():
    response = client.post("/infer", json={})
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
