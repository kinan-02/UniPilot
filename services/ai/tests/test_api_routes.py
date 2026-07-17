"""FastAPI route tests for the AI service.

`/advise` is `agent_core`'s live entry point (`app/routes/advise.py`), now
driven by the V2 agent loop. These tests exercise it with `run_agent_loop`
monkeypatched (the loop itself has its own coverage in `tests/agent_core/loop/`);
this file proves the HTTP-layer wiring: auth, request validation, and the
response-shape mapping onto what `services/api`'s `advisor_service.py` parses.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.routes.advise as advise_module
from app.agent_core.loop import AgentLoopResult
from app.agent_core.loop.working_set import Fact
from app.agent_core.planning.state import ToolInvocationRecord
from app.dependencies.internal_auth import require_internal_service_token
from app.main import app
from app.routes.advise import _derive_course_ids, _derive_sources

client = TestClient(app)


@pytest.fixture(autouse=True)
def _bypass_internal_auth_by_default():
    """Most tests exercise business logic, not auth -- override the
    internal-service-token gate to a no-op. The dedicated auth test removes this
    override for its own duration."""
    app.dependency_overrides[require_internal_service_token] = lambda: None
    yield
    app.dependency_overrides.pop(require_internal_service_token, None)


def _course(entity_id: str, ok: bool = True) -> ToolInvocationRecord:
    return ToolInvocationRecord(
        tool_name="get_entity", arguments={"entity_type": "course", "entity_id": entity_id}, output_ok=ok
    )


def _fake_result(
    *,
    outcome: str = "answered",
    answer: str = "An answer.",
    facts: dict[str, Fact] | None = None,
    audit: list[ToolInvocationRecord] | None = None,
) -> AgentLoopResult:
    return AgentLoopResult(
        outcome=outcome,
        answer=answer,
        ungrounded_numbers=[],
        sub_asks=[],
        facts=facts or {},
        audit=audit or [],
        turns=3,
        llm_calls=5,
        wall_clock_s=1.0,
    )


def _patch_loop(monkeypatch, result: AgentLoopResult) -> None:
    async def _fake_run_agent_loop(**_kwargs) -> AgentLoopResult:
        return result

    monkeypatch.setattr(advise_module, "run_agent_loop", _fake_run_agent_loop)


def test_health_returns_service_payload():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "ai"
    assert body["status"] == "ok"
    assert "academic_graph" in body


# -- audit-derived provenance (grounded in real tool calls) -------------------


def test_derive_course_ids_only_counts_successful_course_get_entity_calls():
    audit = [
        _course("234218"),
        # Wrong entity_type -- excluded.
        ToolInvocationRecord(
            tool_name="get_entity", arguments={"entity_type": "program", "entity_id": "program-alonim"}, output_ok=True
        ),
        _course("999999", ok=False),  # failed -- excluded
        ToolInvocationRecord(tool_name="search_knowledge", arguments={"query": "course"}, output_ok=True),
        _course("114234"),
        _course("234218"),  # duplicate -- deduplicated
    ]
    assert _derive_course_ids(audit) == ["114234", "234218"]


def test_derive_course_ids_returns_empty_for_no_tool_calls():
    assert _derive_course_ids([]) == []


def test_derive_sources_surfaces_wiki_fetches_and_search_queries():
    audit = [
        ToolInvocationRecord(
            tool_name="get_entity", arguments={"entity_type": "track", "entity_id": "track-ise"}, output_ok=True
        ),
        ToolInvocationRecord(tool_name="search_knowledge", arguments={"query": "grade appeal"}, output_ok=True),
        _course("234218"),  # a course fetch is NOT a source
    ]
    assert _derive_sources(audit) == ["search: grade appeal", "track-ise"]


# -- /advise wiring -----------------------------------------------------------


async def test_advise_route_happy_path(monkeypatch):
    _patch_loop(
        monkeypatch,
        _fake_result(
            answer="Course 234218 is Some Course.",
            facts={"c": Fact("v", "src", "official_record", 0.95)},
            audit=[_course("234218")],
        ),
    )
    response = client.post("/advise", json={"question": "What course is 234218?", "user_id": "u1"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["question"] == "What course is 234218?"
    assert data["response"]["answer"] == "Course 234218 is Some Course."
    assert data["response"]["confidence"] == "high"
    assert data["response"]["course_ids"] == ["234218"]
    assert data["response"]["contacts"] == []
    assert data["retrieval_agent"]["status"] == "succeeded"


async def test_advise_route_clarified_maps_to_blocked_status(monkeypatch):
    _patch_loop(monkeypatch, _fake_result(outcome="clarified", answer="Which semester do you mean?"))
    response = client.post("/advise", json={"question": "What about next semester?", "user_id": "u1"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["response"]["answer"] == "Which semester do you mean?"
    assert data["response"]["confidence"] == "low"
    assert data["retrieval_agent"]["status"] == "blocked_needs_clarification"


async def test_advise_route_budget_exhausted_maps_to_incomplete(monkeypatch):
    _patch_loop(monkeypatch, _fake_result(outcome="budget_exhausted", answer="I wasn't able to fully resolve..."))
    response = client.post("/advise", json={"question": "hard question", "user_id": "u1"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["retrieval_agent"]["status"] == "incomplete"
    assert data["response"]["confidence"] == "low"


# -- /advise/stream typed-event wiring (§11) ----------------------------------


def _final_advisor_from_stream(body: str) -> dict:
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        event = json.loads(line[len("data: ") :])
        if event.get("type") == "final":
            return event["data"]["advisor"]
    raise AssertionError(f"stream produced no `final` event; body was:\n{body}")


async def test_advise_stream_emits_chunk_then_final(monkeypatch):
    _patch_loop(
        monkeypatch,
        _fake_result(answer="Course 234218 is Some Course.", audit=[_course("234218")]),
    )
    response = client.post("/advise/stream", json={"question": "What course is 234218?", "user_id": "u1"})

    assert response.status_code == 200
    lines = [json.loads(l[len("data: ") :]) for l in response.text.splitlines() if l.startswith("data: ")]
    assert any(e.get("type") == "chunk" and e.get("text") == "Course 234218 is Some Course." for e in lines)
    advisor = _final_advisor_from_stream(response.text)
    assert advisor["answer"] == "Course 234218 is Some Course."
    assert advisor["courseIds"] == ["234218"]
    assert advisor["retrievalStatus"] == "succeeded"


# -- auth + validation (unchanged) --------------------------------------------


def test_advise_route_rejects_invalid_internal_service_token(monkeypatch):
    app.dependency_overrides.pop(require_internal_service_token, None)
    monkeypatch.setattr(
        "app.dependencies.internal_auth.get_settings",
        lambda: SimpleNamespace(resolved_internal_service_token=lambda: "expected-token"),
    )

    response = client.post(
        "/advise",
        json={"question": "hi", "user_id": "u1"},
        headers={"X-Internal-Service-Token": "wrong-token"},
    )

    assert response.status_code == 401


def test_advise_route_rejects_missing_or_invalid_request_body():
    response = client.post("/advise", json={"question": ""})
    assert response.status_code == 400
