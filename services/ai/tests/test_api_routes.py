"""FastAPI route tests for the AI service.

`/advise` is the agent's live entry point (`app/routes/advise.py`), driven by the
fact/tool loop (`app.agent_core.facts`). These tests exercise it with the facts
entrypoint `run_advice` monkeypatched -- the loop has its own coverage under
`tests/agent_core/facts/` -- so this file proves the HTTP-layer wiring: auth,
request validation, the outcome->status mapping, course-chip grounding, and the
typed SSE stream, all onto the shape `services/api`'s `advisor_service.py` parses.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.routes.advise as advise_module
from app.agent_core.facts.answer import Answer, HeldFact
from app.agent_core.facts.loop import LoopResult
from app.agent_core.facts.propose import Proposal
from app.agent_core.facts.service import to_advice
from app.agent_core.facts.types import (
    Basis,
    Collection,
    Completeness,
    Record,
    Scalar,
    ScalarKind,
)
from app.dependencies.internal_auth import require_internal_service_token
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _bypass_internal_auth_by_default():
    """Most tests exercise business logic, not auth -- override the
    internal-service-token gate to a no-op. The dedicated auth test removes this
    override for its own duration."""
    app.dependency_overrides[require_internal_service_token] = lambda: None
    yield
    app.dependency_overrides.pop(require_internal_service_token, None)


def _courses(*codes: str) -> HeldFact:
    """A held collection of course records, the shape `find` produces."""
    return HeldFact(
        value=Collection(
            records=tuple(
                Record(fields={"courseNumber": Scalar(ScalarKind.IDENTIFIER, c)}, basis=Basis.OFFICIAL_RECORD)
                for c in codes
            ),
            completeness=Completeness(complete=True, total=len(codes)),
        ),
        basis=Basis.OFFICIAL_RECORD,
    )


def _fake_result(
    *,
    outcome: str = "answered",
    answer_text: str = "An answer.",
    basis: Basis = Basis.OFFICIAL_RECORD,
    facts: dict[str, HeldFact] | None = None,
    proposal: Proposal | None = None,
    reason: str | None = None,
) -> LoopResult:
    facts = facts or {}
    answer = (
        Answer(text=answer_text, basis=basis, used=tuple(facts), citations=())
        if outcome == "answered"
        else None
    )
    return LoopResult(
        outcome=outcome, answer=answer, proposal=proposal, reason=reason, facts=facts, turns=3
    )


def _patch_loop(monkeypatch, result: LoopResult) -> None:
    async def _fake_run_advice(**_kwargs) -> LoopResult:
        return result

    monkeypatch.setattr(advise_module, "run_advice", _fake_run_advice)


def test_health_returns_service_payload():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "ai"
    assert body["status"] == "ok"
    assert "academic_graph" in body


# -- course grounding (the mapping is model-independent) -----------------------


def test_course_ids_intersect_the_answer_with_grounded_facts():
    """Courses usually arrive in ONE fetched collection, not one call each. The
    answer's codes are kept only when a held fact also carries them, so an
    invented 8-digit number in the prose is filtered back out."""
    result = _fake_result(
        answer_text="Above 90: 00960336 and 00960262. Also 12345678 (invented).",
        facts={"completed": _courses("00960336", "00960262")},
    )
    advice = to_advice(result)
    assert advice.course_ids == ["00960262", "00960336"]


def test_course_ids_are_empty_when_no_fact_grounds_them():
    result = _fake_result(answer_text="You have completed 158.0 credits.", facts={})
    assert to_advice(result).course_ids == []


# -- /advise wiring -----------------------------------------------------------


async def test_advise_route_happy_path(monkeypatch):
    _patch_loop(
        monkeypatch,
        _fake_result(answer_text="Course 00960211 is E-Commerce.", facts={"c": _courses("00960211")}),
    )
    response = client.post("/advise", json={"question": "What is 00960211?", "user_id": "u1"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["question"] == "What is 00960211?"
    assert data["response"]["answer"] == "Course 00960211 is E-Commerce."
    assert data["response"]["confidence"] == "high"
    assert data["response"]["course_ids"] == ["00960211"]
    assert data["response"]["courses"] == [{"id": "00960211", "name": "E-Commerce Models"}] or (
        # display name falls back to the bare code when the catalog is not loaded
        data["response"]["courses"] == [{"id": "00960211", "name": "00960211"}]
    )
    assert data["response"]["contacts"] == []
    assert data["retrieval_agent"]["status"] == "succeeded"


async def test_a_predicted_answer_is_banded_medium_or_low_not_high(monkeypatch):
    """Confidence follows the weakest grounded basis: a forecast is never high."""
    _patch_loop(monkeypatch, _fake_result(answer_text="It usually runs in spring.", basis=Basis.PREDICTED_PATTERN))
    data = client.post("/advise", json={"question": "spring?", "user_id": "u1"}).json()["data"]
    assert data["response"]["confidence"] == "low"
    assert data["retrieval_agent"]["status"] == "succeeded"


async def test_a_decline_is_a_successful_conclusion(monkeypatch):
    """An out-of-scope question answered by declining is a valid response, not an
    error state -- it maps to 'succeeded'."""
    _patch_loop(monkeypatch, _fake_result(outcome="declined", reason="I can only help with your studies."))
    data = client.post("/advise", json={"question": "weather?", "user_id": "u1"}).json()["data"]
    assert data["response"]["answer"] == "I can only help with your studies."
    assert data["response"]["confidence"] == "low"
    assert data["retrieval_agent"]["status"] == "succeeded"


async def test_a_proposal_is_described_for_confirmation(monkeypatch):
    proposal = Proposal(
        action="register", target="00960211", payload={}, grounds=("g",), basis=Basis.OFFICIAL_RECORD
    )
    _patch_loop(monkeypatch, _fake_result(outcome="proposed", proposal=proposal))
    data = client.post("/advise", json={"question": "register me", "user_id": "u1"}).json()["data"]
    assert "confirmation" in data["response"]["answer"].lower()
    assert data["retrieval_agent"]["status"] == "succeeded"


async def test_an_exhausted_run_maps_to_incomplete_with_a_student_message(monkeypatch):
    _patch_loop(monkeypatch, _fake_result(outcome="exhausted", reason="the turn budget was spent"))
    data = client.post("/advise", json={"question": "hard", "user_id": "u1"}).json()["data"]
    assert data["retrieval_agent"]["status"] == "incomplete"
    assert data["response"]["confidence"] == "low"
    # The student sees a graceful message, never the diagnostic reason.
    assert "turn budget" not in data["response"]["answer"]


async def test_advise_route_ships_chips_for_courses_named_from_a_bulk_payload(monkeypatch):
    """End to end: the route's course_ids feed the UI's "Referenced Courses" chips."""
    _patch_loop(
        monkeypatch,
        _fake_result(
            answer_text="Above 90: 00960336 and 00960262.",
            facts={"completed": _courses("00960336", "00960262")},
        ),
    )
    response = client.post("/advise", json={"question": "grades above 90?", "user_id": "u1"})
    assert response.json()["data"]["response"]["course_ids"] == ["00960262", "00960336"]


# -- progress events during the silent wait ------------------------------------


def _patch_loop_reporting(monkeypatch, phrases: list[str], result: LoopResult) -> None:
    """A loop that reports progress before returning, like the real one."""

    async def _fake_run_advice(*, on_progress=None, **_kwargs) -> LoopResult:
        for phrase in phrases:
            if on_progress is not None:
                on_progress(phrase)
        return result

    monkeypatch.setattr(advise_module, "run_advice", _fake_run_advice)


async def test_advise_stream_forwards_progress_before_the_answer(monkeypatch):
    """Without this the connection is silent for the entire request."""
    _patch_loop_reporting(
        monkeypatch,
        ["Looking up your records…", "Working through the details…"],
        _fake_result(answer_text="You are eligible."),
    )
    response = client.post("/advise/stream", json={"question": "am i eligible?", "user_id": "u1"})

    assert response.status_code == 200
    kinds = [json.loads(line[6:])["type"] for line in response.text.splitlines() if line.startswith("data: ")]
    assert kinds == ["progress", "progress", "chunk", "final"], kinds
    texts = [
        json.loads(line[6:])["text"]
        for line in response.text.splitlines()
        if line.startswith("data: ") and json.loads(line[6:])["type"] == "progress"
    ]
    assert texts == ["Looking up your records…", "Working through the details…"]


async def test_advise_stream_still_answers_when_the_loop_reports_nothing(monkeypatch):
    """Progress is advisory. A loop that never reports must stream exactly the
    `chunk` + `final` pair clients handled before progress existed."""
    _patch_loop_reporting(monkeypatch, [], _fake_result(answer_text="42 credits."))
    response = client.post("/advise/stream", json={"question": "how many?", "user_id": "u1"})

    kinds = [json.loads(line[6:])["type"] for line in response.text.splitlines() if line.startswith("data: ")]
    assert kinds == ["chunk", "final"]
    assert _final_advisor_from_stream(response.text)["answer"] == "42 credits."


# -- timeout ladder ------------------------------------------------------------


def test_advise_timeout_ceiling_stays_below_the_upstream_callers():
    """The route ceiling is a backstop for a hung provider. Above it sit
    `ai_advisor_timeout_seconds` (services/api) and nginx's `proxy_read_timeout`,
    both 300s -- the ceiling must stay under them so the AI service, not the edge,
    is the one that times out and returns the graceful message."""
    from app.config import get_settings

    ceiling = get_settings().agent_turn_timeout_seconds
    assert 0 < ceiling <= 300, f"route ceiling {ceiling}s must be a positive backstop under the 300s callers"


# -- /advise/stream typed-event wiring ----------------------------------------


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
        _fake_result(answer_text="Course 00960211 is E-Commerce.", facts={"c": _courses("00960211")}),
    )
    response = client.post("/advise/stream", json={"question": "What is 00960211?", "user_id": "u1"})

    assert response.status_code == 200
    lines = [json.loads(l[len("data: ") :]) for l in response.text.splitlines() if l.startswith("data: ")]
    assert any(e.get("type") == "chunk" and e.get("text") == "Course 00960211 is E-Commerce." for e in lines)
    advisor = _final_advisor_from_stream(response.text)
    assert advisor["answer"] == "Course 00960211 is E-Commerce."
    assert advisor["courseIds"] == ["00960211"]
    assert advisor["retrievalStatus"] == "succeeded"


# -- auth + validation --------------------------------------------------------


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
    # The app wraps validation errors in its own error envelope (400), and
    # `user_id` is required too, so a blank question with no user_id is rejected.
    response = client.post("/advise", json={"question": ""})
    assert response.status_code in (400, 422)
    assert client.post("/advise", json={"question": "hi"}).status_code in (400, 422)


async def test_conversation_id_is_threaded_to_run_advice(monkeypatch):
    """A follow-up carries its thread id so 'continue' can resolve. The route's
    job is to pass it through; the loading/appending is the service's."""
    seen = {}

    async def _fake_run_advice(**kwargs):
        seen.update(kwargs)
        return _fake_result(answer_text="Continuing where we left off.")

    monkeypatch.setattr(advise_module, "run_advice", _fake_run_advice)
    response = client.post(
        "/advise",
        json={"question": "yes, continue", "user_id": "u1", "conversation_id": "thread-7"},
    )
    assert response.status_code == 200
    assert seen["conversation_id"] == "thread-7"


async def test_conversation_id_is_optional(monkeypatch):
    """A one-off question omits it, and the route must still work."""
    seen = {}

    async def _fake_run_advice(**kwargs):
        seen.update(kwargs)
        return _fake_result(answer_text="One-off answer.")

    monkeypatch.setattr(advise_module, "run_advice", _fake_run_advice)
    response = client.post("/advise", json={"question": "how many credits?", "user_id": "u1"})
    assert response.status_code == 200
    assert seen.get("conversation_id") is None
