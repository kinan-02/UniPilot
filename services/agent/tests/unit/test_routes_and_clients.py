"""Unit tests for the agent service's routes and HTTP clients."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.clients.internal_api_client import (
    InternalApiClientError,
    fetch_course_requirement_contribution,
    fetch_graduation_audit,
    fetch_semester_plan_options,
    fetch_student_user_context,
)
from app.config import Settings, get_settings
from app.dependencies.internal_auth import require_internal_service_token
from app.main import create_app
from fastapi import HTTPException


def _settings_with_token(**overrides) -> Settings:
    base = {"internal_service_token": "shared-secret", "api_service_url": "http://api-test:8000"}
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------------------
# Health route
# ---------------------------------------------------------------------------


def test_health_route_returns_ok_when_mongo_not_configured(monkeypatch):
    monkeypatch.setenv("MONGO_URI", "")
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "agent"
    assert body["dependencies"]["mongo"] == "not_configured"


# ---------------------------------------------------------------------------
# Internal auth dependency
# ---------------------------------------------------------------------------


async def test_require_internal_service_token_rejects_missing_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "expected-token")
    get_settings.cache_clear()

    with pytest.raises(HTTPException) as exc_info:
        await require_internal_service_token(x_internal_service_token=None)
    assert exc_info.value.status_code == 401


async def test_require_internal_service_token_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "expected-token")
    get_settings.cache_clear()

    with pytest.raises(HTTPException) as exc_info:
        await require_internal_service_token(x_internal_service_token="wrong-token")
    assert exc_info.value.status_code == 401


async def test_require_internal_service_token_accepts_correct_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "expected-token")
    get_settings.cache_clear()

    await require_internal_service_token(x_internal_service_token="expected-token")


async def test_require_internal_service_token_fails_closed_when_unconfigured(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "")
    get_settings.cache_clear()

    with pytest.raises(HTTPException) as exc_info:
        await require_internal_service_token(x_internal_service_token="anything")
    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# /turn route — auth guard only (full behavior covered by orchestrator tests)
# ---------------------------------------------------------------------------


def test_turn_route_requires_internal_service_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "expected-token")
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.post(
        "/turn",
        json={
            "userId": "000000000000000000000000",
            "conversationId": "000000000000000000000000",
            "userMessage": "hi",
            "triggerMessageId": "000000000000000000000000",
        },
    )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# internal_api_client — mocked HTTP via respx
# ---------------------------------------------------------------------------


@respx.mock
async def test_fetch_graduation_audit_returns_data_on_success():
    settings = _settings_with_token()
    respx.get("http://api-test:8000/internal/agent/graduation-audit/users/u1").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"graduationAudit": {"status": "ok"}}})
    )

    result = await fetch_graduation_audit(user_id="u1", settings=settings)

    assert result == {"status": "ok"}


@respx.mock
async def test_fetch_graduation_audit_raises_on_error_status():
    settings = _settings_with_token()
    respx.get("http://api-test:8000/internal/agent/graduation-audit/users/u1").mock(
        return_value=httpx.Response(404, json={"success": False, "detail": "not found"})
    )

    with pytest.raises(InternalApiClientError) as exc_info:
        await fetch_graduation_audit(user_id="u1", settings=settings)
    assert exc_info.value.status_code == 404


@respx.mock
async def test_fetch_graduation_audit_raises_on_malformed_success_payload():
    settings = _settings_with_token()
    respx.get("http://api-test:8000/internal/agent/graduation-audit/users/u1").mock(
        return_value=httpx.Response(200, json={"success": True, "data": "not-a-dict"})
    )

    with pytest.raises(InternalApiClientError) as exc_info:
        await fetch_graduation_audit(user_id="u1", settings=settings)
    assert exc_info.value.status_code == 502


@respx.mock
async def test_fetch_semester_plan_options_posts_context_snapshot():
    settings = _settings_with_token()
    route = respx.post("http://api-test:8000/internal/agent/semester-plan-options/users/u1").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"semesterPlanning": {"status": "ok"}}})
    )

    result = await fetch_semester_plan_options(
        user_id="u1", context_snapshot={"intent": "semester_plan_generation"}, settings=settings
    )

    assert result == {"status": "ok"}
    assert route.called
    sent_body = route.calls.last.request.content
    assert b"semester_plan_generation" in sent_body


@respx.mock
async def test_fetch_course_requirement_contribution_sends_query_params():
    settings = _settings_with_token()
    route = respx.get("http://api-test:8000/internal/agent/course-requirement-contribution").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"contribution": {"status": "matched"}}})
    )

    result = await fetch_course_requirement_contribution(
        program_code="009216-1-000", course_number="00940345", settings=settings
    )

    assert result == {"contribution": {"status": "matched"}}
    assert route.called
    assert route.calls.last.request.url.params["programCode"] == "009216-1-000"
    assert route.calls.last.request.url.params["courseNumber"] == "00940345"


@respx.mock
async def test_fetch_student_user_context_returns_data():
    settings = _settings_with_token()
    respx.get("http://api-test:8000/internal/user-context/users/u1").mock(
        return_value=httpx.Response(
            200, json={"success": True, "data": {"userContext": {"completed_courses": ["00940345"]}}}
        )
    )

    result = await fetch_student_user_context(user_id="u1", settings=settings)

    assert result == {"completed_courses": ["00940345"]}


@respx.mock
async def test_internal_api_client_sends_service_token_header():
    settings = _settings_with_token()
    route = respx.get("http://api-test:8000/internal/agent/graduation-audit/users/u1").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"graduationAudit": {}}})
    )

    await fetch_graduation_audit(user_id="u1", settings=settings)

    assert route.calls.last.request.headers["x-internal-service-token"] == "shared-secret"
