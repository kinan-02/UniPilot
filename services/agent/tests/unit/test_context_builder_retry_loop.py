"""Unit tests for `context_builder`'s gap-aware structured-retrieval retry loop.

Regression coverage for: the retry loop used to gate ALL structured sources
(mongodb/structured_catalog/structured_offerings) behind a single
`structured_loaded` flag that only ever ran on attempt 0 — even though
`identify_retrieval_gaps` can detect `missing_structured_course`/
`missing_offering` on later attempts. These tests assert the implicated
structured step actually re-runs when its gap is present, and that `mongodb`
(student profile) never re-runs regardless.
"""

from __future__ import annotations

from typing import Any

import pytest

import app.agent.context_builder as context_builder_module
from app.agent.context_builder import build_agent_context_pack
from app.agent.schemas import IntentClassification, TaskPlan
from app.config import Settings


def _agentic_settings() -> Settings:
    return Settings(**{"AGENT_AGENTIC_RETRIEVAL_ENABLED": True})


async def _fake_graph_context(**_kwargs: Any) -> tuple[list[dict], list[Any], dict[str, Any]]:
    return [], [], {}


async def _fake_mongodb_user_data(database: Any, *, user_id: str, queries: list[str]):
    return {"profile": {"currentSemesterCode": "2024-2"}}, []


async def _fake_list_planner_semester_codes(database: Any, settings: Any = None) -> list[str]:
    return ["2025-1"]


async def _default_fake_offerings(database: Any, *, queries, entities, settings):
    return {}, []


@pytest.fixture(autouse=True)
def _stub_semester_code_lookup(monkeypatch):
    """`structured_offerings` resolves available semester codes directly via
    `catalog_repository` (a real DB call) before ever calling
    `retrieve_offerings_context` — stub it so a plain `object()` database
    stand-in is enough for these tests. Also stub `retrieve_offerings_context`
    itself with an inert default (tests that care about its behavior
    override it explicitly) — `course_question` + a `courseNumber` always
    plans a `structured_offerings` step regardless of what each test is
    actually exercising."""
    monkeypatch.setattr(
        context_builder_module.catalog_repository,
        "list_planner_semester_codes_from_offerings",
        _fake_list_planner_semester_codes,
    )
    monkeypatch.setattr(context_builder_module, "retrieve_offerings_context", _default_fake_offerings)


@pytest.mark.asyncio
async def test_missing_offering_gap_triggers_structured_offerings_retry(monkeypatch):
    calls: list[dict[str, Any]] = []

    async def _fake_offerings(database: Any, *, queries, entities, settings):
        calls.append(dict(entities))
        if len(calls) == 1:
            return {"offering": None}, []
        return {
            "offering": {"courseNumber": entities.get("courseNumber"), "semesterCode": "2025-1"},
            "offerings": [{"courseNumber": entities.get("courseNumber")}],
        }, []

    async def _fake_catalog(database: Any, *, user_id, queries, entities, user_context):
        return {"course": {"courseNumber": entities.get("courseNumber")}}, []

    monkeypatch.setattr(context_builder_module, "retrieve_offerings_context", _fake_offerings)
    monkeypatch.setattr(context_builder_module, "retrieve_catalog_context", _fake_catalog)
    monkeypatch.setattr(context_builder_module, "retrieve_mongodb_user_data", _fake_mongodb_user_data)
    monkeypatch.setattr(context_builder_module, "retrieve_graph_context_with_profile", _fake_graph_context)

    pack = await build_agent_context_pack(
        database=object(),
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="course_question",
        entities={"courseNumber": "00440148", "targetSemesterCode": "2025-1"},
        classification=IntentClassification(intent="course_question", confidence=0.9),
        task_plan=TaskPlan(workflow="course_question_workflow"),
        user_message="is 00440148 offered next semester?",
        settings=_agentic_settings(),
    )

    assert len(calls) >= 2, "expected structured_offerings to be retried after a missing_offering gap"
    assert pack.academic_context.get("offering") is not None


@pytest.mark.asyncio
async def test_mongodb_step_never_retries_even_with_gaps_present(monkeypatch):
    mongo_calls = {"count": 0}

    async def _fake_mongodb(database: Any, *, user_id, queries):
        mongo_calls["count"] += 1
        return {"profile": None}, []  # missing profile -> validation keeps producing warnings

    async def _fake_catalog(database: Any, *, user_id, queries, entities, user_context):
        return {"course": None}, []  # course never found -> gap persists every attempt

    monkeypatch.setattr(context_builder_module, "retrieve_mongodb_user_data", _fake_mongodb)
    monkeypatch.setattr(context_builder_module, "retrieve_catalog_context", _fake_catalog)
    monkeypatch.setattr(context_builder_module, "retrieve_graph_context_with_profile", _fake_graph_context)

    await build_agent_context_pack(
        database=object(),
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="course_question",
        entities={"courseNumber": "00440148"},
        classification=IntentClassification(intent="course_question", confidence=0.9),
        task_plan=TaskPlan(workflow="course_question_workflow"),
        user_message="tell me about 00440148",
        settings=_agentic_settings(),
    )

    # mongodb has no retry-eligible gap kind mapped to it — it must never
    # run more than once, regardless of how many attempts the loop makes.
    assert mongo_calls["count"] == 1


@pytest.mark.asyncio
async def test_structured_catalog_retries_on_missing_structured_course_gap(monkeypatch):
    catalog_calls: list[dict[str, Any]] = []

    async def _fake_catalog(database: Any, *, user_id, queries, entities, user_context):
        catalog_calls.append(dict(entities))
        if len(catalog_calls) == 1:
            return {"course": None}, []
        return {"course": {"courseNumber": entities.get("courseNumber")}}, []

    monkeypatch.setattr(context_builder_module, "retrieve_catalog_context", _fake_catalog)
    monkeypatch.setattr(context_builder_module, "retrieve_mongodb_user_data", _fake_mongodb_user_data)
    monkeypatch.setattr(context_builder_module, "retrieve_graph_context_with_profile", _fake_graph_context)

    pack = await build_agent_context_pack(
        database=object(),
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="course_question",
        entities={"courseNumber": "00440148"},
        classification=IntentClassification(intent="course_question", confidence=0.9),
        task_plan=TaskPlan(workflow="course_question_workflow"),
        user_message="tell me about 00440148",
        settings=_agentic_settings(),
    )

    assert len(catalog_calls) >= 2, "expected structured_catalog to be retried after a missing_structured_course gap"
    assert pack.academic_context.get("course") is not None
