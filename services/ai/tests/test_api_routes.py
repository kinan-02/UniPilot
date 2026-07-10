"""FastAPI route tests for the AI service.

`/retrieve`, `/advise`, `/infer` were removed with the retired advisor HTTP
surface (see docs/agent/TOOL_PRIMITIVES_PROGRESS.md) -- `agent_core` will get
its own routes once it's wired up to replace it.
"""

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
