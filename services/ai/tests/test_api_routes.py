"""FastAPI route tests for the AI service.

`/retrieve`, `/advise`, `/infer` were removed with the retired advisor HTTP
surface. `/advise` is now `agent_core`'s own live entry point
(`app/routes/advise.py`) -- these tests exercise it with `run_agent_turn`
monkeypatched (the underlying chain has its own extensive coverage in
`tests/agent_core/`; this file proves the HTTP-layer wiring: auth, request
validation, and response-shape mapping onto what `services/api`'s
`advisor_service.py` already parses).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.routes.advise as advise_module
from app.agent_core.planning.state import CertaintyTag, PlanExecutionState, StateEntry, ToolInvocationRecord
from app.dependencies.internal_auth import require_internal_service_token
from app.main import app
from app.routes.advise import _derive_course_ids

client = TestClient(app)


@pytest.fixture(autouse=True)
def _bypass_internal_auth_by_default():
    """Most tests below exercise business logic, not auth -- override the
    internal-service-token gate to a no-op so they aren't coupled to whether
    a real INTERNAL_SERVICE_TOKEN happens to be resolvable from the ambient
    environment. test_advise_route_rejects_invalid_internal_service_token
    removes this override for its own duration to test the real gate."""
    app.dependency_overrides[require_internal_service_token] = lambda: None
    yield
    app.dependency_overrides.pop(require_internal_service_token, None)


def test_health_returns_service_payload():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "ai"
    assert body["status"] == "ok"
    assert "academic_graph" in body


def _entry_with_tool_calls(*records: ToolInvocationRecord) -> StateEntry:
    return StateEntry(
        entry_id="s1-0",
        step_id="s1",
        role="retrieval",
        status="succeeded",
        output_schema_name="generic_step_output_v1",
        data={},
        certainty=CertaintyTag(basis="official_record", confidence=0.9),
        tool_audit_trail=list(records),
        produced_at=datetime.now(timezone.utc),
    )


def test_derive_course_ids_only_counts_successful_course_get_entity_calls():
    state = PlanExecutionState(plan_id="p1")
    state.append(
        _entry_with_tool_calls(
            ToolInvocationRecord(
                tool_name="get_entity", arguments={"entity_type": "course", "entity_id": "234218"}, output_ok=True
            ),
            # Wrong entity_type -- excluded.
            ToolInvocationRecord(
                tool_name="get_entity", arguments={"entity_type": "program", "entity_id": "program-alonim"}, output_ok=True
            ),
            # Failed call -- excluded even though entity_type matches.
            ToolInvocationRecord(
                tool_name="get_entity", arguments={"entity_type": "course", "entity_id": "999999"}, output_ok=False
            ),
            # Not get_entity at all -- excluded.
            ToolInvocationRecord(tool_name="search_knowledge", arguments={"query": "course"}, output_ok=True),
        )
    )
    state.append(
        _entry_with_tool_calls(
            ToolInvocationRecord(
                tool_name="get_entity", arguments={"entity_type": "course", "entity_id": "114234"}, output_ok=True
            ),
            # Duplicate of the first entry's course -- deduplicated.
            ToolInvocationRecord(
                tool_name="get_entity", arguments={"entity_type": "course", "entity_id": "234218"}, output_ok=True
            ),
        )
    )

    assert _derive_course_ids(state) == ["114234", "234218"]


def test_derive_course_ids_returns_empty_for_no_tool_calls():
    state = PlanExecutionState(plan_id="p1")
    state.append(_entry_with_tool_calls())
    assert _derive_course_ids(state) == []


def _fake_final_entry(*, answer_text: str, confidence: float = 0.9, status: str = "succeeded") -> SimpleNamespace:
    return SimpleNamespace(
        data={"answer_text": answer_text},
        certainty=SimpleNamespace(confidence=confidence),
        status=status,
        tool_audit_trail=[],
    )


async def test_advise_route_happy_path(monkeypatch):
    state = PlanExecutionState(plan_id="p1")
    state.append(
        _entry_with_tool_calls(
            ToolInvocationRecord(
                tool_name="get_entity", arguments={"entity_type": "course", "entity_id": "234218"}, output_ok=True
            )
        )
    )

    async def fake_run_agent_turn(**_kwargs):
        return (
            SimpleNamespace(in_scope=True, decline_reason=None),
            state,
            _fake_final_entry(answer_text="Course 234218 is Some Course.", confidence=0.85),
            None,
        )

    monkeypatch.setattr(advise_module, "run_agent_turn", fake_run_agent_turn)

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


async def test_advise_route_out_of_scope_decline(monkeypatch):
    async def fake_run_agent_turn(**_kwargs):
        return (
            SimpleNamespace(in_scope=False, decline_reason="I can only help with academic advising questions."),
            PlanExecutionState(plan_id="p1"),
            _fake_final_entry(answer_text="I can only help with academic advising questions.", confidence=0.95),
            None,
        )

    monkeypatch.setattr(advise_module, "run_agent_turn", fake_run_agent_turn)

    response = client.post("/advise", json={"question": "Write me a poem.", "user_id": "u1"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["response"]["answer"] == "I can only help with academic advising questions."
    assert data["response"]["course_ids"] == []
    assert data["retrieval_agent"]["status"] == "out_of_scope"


async def test_advise_route_blocked_needs_clarification(monkeypatch):
    async def fake_run_agent_turn(**_kwargs):
        return (
            SimpleNamespace(in_scope=True, decline_reason=None),
            PlanExecutionState(plan_id="p1"),
            None,
            "Which semester do you mean?",
        )

    monkeypatch.setattr(advise_module, "run_agent_turn", fake_run_agent_turn)

    response = client.post("/advise", json={"question": "What about next semester?", "user_id": "u1"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["response"]["answer"] == "Which semester do you mean?"
    assert data["retrieval_agent"]["status"] == "blocked_needs_clarification"


def _final_advisor_from_stream(body: str) -> dict:
    """The `advisor` payload carried by the stream's terminal `final` event."""
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        event = json.loads(line[len("data: ") :])
        if event.get("type") == "final":
            return event["data"]["advisor"]
    raise AssertionError(f"stream produced no `final` event; body was:\n{body}")


async def test_advise_stream_backfills_a_blank_answer_from_the_streamed_text(monkeypatch):
    """The legitimate half of the stream's recovery block: when composition
    streams plain text but its final entry can't be parsed into one
    (`data={}` -> answer ""), the accumulated chunks become the answer.

    Pinned so the F5 fix (see the next test) can't quietly take the real
    recovery down with the laundering it sits next to."""

    async def fake_run_agent_turn(*, streaming_queue=None, **_kwargs):
        await streaming_queue.put("Course 234218 is Some Course.")
        return (
            SimpleNamespace(in_scope=True, decline_reason=None),
            PlanExecutionState(plan_id="p1"),
            _fake_final_entry(answer_text="", status="succeeded"),
            None,
        )

    monkeypatch.setattr(advise_module, "run_agent_turn", fake_run_agent_turn)

    response = client.post("/advise/stream", json={"question": "What course is 234218?", "user_id": "u1"})

    assert response.status_code == 200
    advisor = _final_advisor_from_stream(response.text)
    assert advisor["answer"] == "Course 234218 is Some Course."


async def test_advise_stream_does_not_launder_a_failed_status_into_succeeded(monkeypatch):
    """Recovering an ANSWER from the streamed text says nothing about whether
    RETRIEVAL succeeded -- the two facts are unrelated, and the stream path must
    not rewrite the second because it managed the first.

    Regression for F5: the recovery block ended with
    `if advisor["retrievalStatus"] == "failed": advisor["retrievalStatus"] = "succeeded"`,
    so a turn whose retrieval genuinely failed was reported to the frontend as a
    clean success -- on the streaming path only. The non-streaming `/advise`
    reported the same turn honestly, which is why the two paths disagreed.
    """

    async def fake_run_agent_turn(*, streaming_queue=None, **_kwargs):
        await streaming_queue.put("Here is my best guess at an answer.")
        return (
            SimpleNamespace(in_scope=True, decline_reason=None),
            PlanExecutionState(plan_id="p1"),
            _fake_final_entry(answer_text="", status="failed"),
            None,
        )

    monkeypatch.setattr(advise_module, "run_agent_turn", fake_run_agent_turn)

    response = client.post("/advise/stream", json={"question": "How many credits do I have left?", "user_id": "u1"})

    assert response.status_code == 200
    advisor = _final_advisor_from_stream(response.text)
    # The answer is still recovered...
    assert advisor["answer"] == "Here is my best guess at an answer."
    # ...but the turn is still reported as what it actually was.
    assert advisor["retrievalStatus"] == "failed", (
        "a failed turn was reported to the frontend as succeeded -- the streamed-text "
        "backfill recovered the answer text and then rewrote an unrelated status"
    )


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
